"""
Capture layer.

Streamlit is request driven, so packets cannot be pulled from an interface
inside a script rerun. A background thread owns the capture and pushes finished
flows into a bounded queue. The dashboard drains that queue on each refresh.

Two sources are supported behind one interface:

  * SimulatedSource - generates flows, needs no drivers or privileges, and is
    what the interface runs on until the model and Npcap are in place.
  * NfstreamSource  - real capture through nfstream, which needs Npcap on
    Windows and an administrator shell.

The queue is bounded on purpose. If the interface stalls, dropping the oldest
flows is preferable to growing memory without limit, and the drop counter is
surfaced on the live page so the loss is visible rather than silent.
"""

import queue
import threading
import time
from typing import Dict, List, Optional

from .schema import FEATURE_COLUMNS

QUEUE_SIZE = 4000


class CaptureError(Exception):
    """Raised when a capture source cannot start."""


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


class SimulatedSource:
    """Emits synthetic flows at a configurable rate."""

    name = "Simulated"
    requires_privileges = False

    def __init__(self, flows_per_second: float = 6.0, attack_bias: float = 1.0):
        self.flows_per_second = max(0.2, float(flows_per_second))
        self.attack_bias = attack_bias

    def flows(self, stop_event: threading.Event):
        from .simulator import generate_flow

        interval = 1.0 / self.flows_per_second
        while not stop_event.is_set():
            yield generate_flow(attack_bias=self.attack_bias)
            stop_event.wait(interval)


class NfstreamSource:
    """
    Real capture through nfstream.

    nfstream computes bidirectional flow statistics itself, so the mapping below
    is a rename onto the CICIDS2017 feature names rather than a reimplementation.
    A few CICIDS features have no direct nfstream equivalent and are derived from
    what is available; those are marked in the mapping.
    """

    name = "nfstream"
    requires_privileges = True

    def __init__(self, interface: str, idle_timeout: int = 15, active_timeout: int = 60):
        self.interface = interface
        self.idle_timeout = idle_timeout
        self.active_timeout = active_timeout

    @staticmethod
    def available() -> bool:
        try:
            import nfstream  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def list_interfaces() -> List[str]:
        """Return capture interfaces visible to the packet driver."""
        names = []
        try:
            from scapy.arch import get_windows_if_list  # type: ignore

            for item in get_windows_if_list():
                if item.get("name"):
                    names.append(item["name"])
        except Exception:  # noqa: BLE001
            pass

        if not names:
            try:
                import psutil

                names = list(psutil.net_if_addrs().keys())
            except Exception:  # noqa: BLE001
                pass

        return names

    @staticmethod
    def to_features(flow) -> Dict:
        """Map one nfstream flow onto the schema feature names plus metadata."""
        duration_ms = max(flow.bidirectional_duration_ms, 1)
        duration_us = duration_ms * 1000.0
        seconds = duration_ms / 1000.0

        fwd_packets = float(flow.src2dst_packets)
        bwd_packets = float(flow.dst2src_packets)
        fwd_bytes = float(flow.src2dst_bytes)
        bwd_bytes = float(flow.dst2src_bytes)
        total_packets = max(fwd_packets + bwd_packets, 1.0)
        total_bytes = fwd_bytes + bwd_bytes

        protocol_name = {6: "TCP", 17: "UDP", 1: "ICMP"}.get(flow.protocol, str(flow.protocol))

        record = {
            "ts": time.time(),
            "src_ip": flow.src_ip,
            "src_port": int(flow.src_port),
            "dst_ip": flow.dst_ip,
            "dst_port": int(flow.dst_port),
            "protocol": protocol_name,
            # Feature columns
            "Flow Duration": duration_us,
            "Total Fwd Packets": fwd_packets,
            "Total Backward Packets": bwd_packets,
            "Total Length of Fwd Packets": fwd_bytes,
            "Total Length of Bwd Packets": bwd_bytes,
            "Fwd Packet Length Max": float(flow.src2dst_max_ps),
            "Fwd Packet Length Mean": float(flow.src2dst_mean_ps),
            "Bwd Packet Length Max": float(flow.dst2src_max_ps),
            "Bwd Packet Length Mean": float(flow.dst2src_mean_ps),
            "Flow Bytes/s": total_bytes / max(seconds, 1e-6),
            "Flow Packets/s": total_packets / max(seconds, 1e-6),
            # nfstream reports inter-arrival times in milliseconds, CICIDS uses
            # microseconds, hence the factor of 1000 on every IAT column.
            "Flow IAT Mean": float(flow.bidirectional_mean_piat_ms) * 1000.0,
            "Flow IAT Std": float(flow.bidirectional_stddev_piat_ms) * 1000.0,
            "Flow IAT Max": float(flow.bidirectional_max_piat_ms) * 1000.0,
            "Fwd IAT Mean": float(flow.src2dst_mean_piat_ms) * 1000.0,
            "Bwd IAT Mean": float(flow.dst2src_mean_piat_ms) * 1000.0,
            "Min Packet Length": float(flow.bidirectional_min_ps),
            "Max Packet Length": float(flow.bidirectional_max_ps),
            "Packet Length Mean": float(flow.bidirectional_mean_ps),
            "SYN Flag Count": float(getattr(flow, "bidirectional_syn_packets", 0)),
        }

        for column in FEATURE_COLUMNS:
            if column not in record:
                record[column] = 0.0

        return record

    def flows(self, stop_event: threading.Event):
        try:
            from nfstream import NFStreamer
        except ImportError as error:
            raise CaptureError(
                "nfstream is not installed. Run: pip install nfstream"
            ) from error

        try:
            streamer = NFStreamer(
                source=self.interface,
                statistical_analysis=True,
                idle_timeout=self.idle_timeout,
                active_timeout=self.active_timeout,
            )
        except Exception as error:  # noqa: BLE001
            raise CaptureError(
                f"Could not open interface '{self.interface}'. "
                "On Windows this usually means Npcap is missing, or the app was "
                "not started from an Administrator terminal. "
                f"Underlying error: {error}"
            ) from error

        for flow in streamer:
            if stop_event.is_set():
                break
            yield self.to_features(flow)


class PcapSource(NfstreamSource):
    """Replays a saved capture file. Needs no privileges, useful for a demo."""

    name = "PCAP replay"
    requires_privileges = False

    def __init__(self, path: str, speed: float = 1.0):
        super().__init__(interface=path)
        self.path = path
        self.speed = speed

    def flows(self, stop_event: threading.Event):
        for record in super().flows(stop_event):
            yield record
            # Slow the replay down so the radar is watchable rather than
            # finishing the whole file in one refresh.
            if self.speed > 0:
                stop_event.wait(0.05 / self.speed)


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------


class CaptureController:
    """Owns the background thread and the flow queue."""

    def __init__(self):
        self.queue: "queue.Queue[Dict]" = queue.Queue(maxsize=QUEUE_SIZE)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.error: Optional[str] = None
        self.source_name: str = "None"
        self.started_at: Optional[float] = None
        self.dropped: int = 0
        self.captured: int = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, source) -> None:
        """Start capture. Restarts cleanly if a source is already running."""
        if self.running:
            self.stop()

        self.error = None
        self.dropped = 0
        self.captured = 0
        self._stop = threading.Event()
        self.source_name = source.name
        self.started_at = time.time()

        def worker():
            try:
                for record in source.flows(self._stop):
                    if self._stop.is_set():
                        break
                    try:
                        self.queue.put_nowait(record)
                        self.captured += 1
                    except queue.Full:
                        # Drop the oldest flow to make room for the newest.
                        try:
                            self.queue.get_nowait()
                            self.queue.put_nowait(record)
                            self.dropped += 1
                        except queue.Empty:
                            pass
            except CaptureError as error:
                self.error = str(error)
            except Exception as error:  # noqa: BLE001
                self.error = f"Capture stopped unexpectedly: {error}"

        self._thread = threading.Thread(target=worker, name="nids-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to finish and wait briefly for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self.started_at = None

    def drain(self, limit: int = 400) -> List[Dict]:
        """Take everything currently queued, up to a limit."""
        rows = []
        while len(rows) < limit:
            try:
                rows.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return rows

    def uptime(self) -> float:
        return 0.0 if self.started_at is None else time.time() - self.started_at
