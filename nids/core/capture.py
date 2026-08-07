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

    def __init__(self, interface: str, idle_timeout: int = 2, active_timeout: int = 10):
        # Short timeouts on purpose. nfstream only emits a flow once it expires,
        # either after idle_timeout seconds of silence or active_timeout seconds
        # of life. The library defaults (15s / 60s) are meant for offline
        # analysis; on a live dashboard they mean a flow is held for up to a
        # minute before it ever reaches the screen, which looks like capture is
        # producing nothing. Two and ten seconds keep the table and the counters
        # updating at a pace that reads as live, at the cost of splitting a few
        # long connections into several flows, which does not matter here.
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
        """
        Return friendly interface names to show in the dropdown.

        On Windows these are names like "Wi-Fi" or "Ethernet". They are only for
        display; resolve_source() turns the chosen name into the device path
        nfstream actually needs.
        """
        return list(NfstreamSource.interface_map().keys())

    @staticmethod
    def interface_map() -> "dict[str, str]":
        """
        Map each friendly interface name to the identifier nfstream opens.

        This is the crux of live capture on Windows. The dropdown shows friendly
        names ("Wi-Fi"), but nfstream, which sits on Npcap, needs the Npcap
        device path (\\\\Device\\\\NPF_{GUID}), not the friendly name. Passing the
        friendly name is what produces "please specify a valid interface".

        scapy exposes both on Windows: the friendly "name" and the "guid" that
        the device path is built from. We pair them so the user picks a readable
        name and nfstream still receives a path it can open. Off Windows, or if
        scapy cannot enumerate, the names map to themselves, which is what
        nfstream expects on Linux anyway.
        """
        mapping: "dict[str, str]" = {}

        # Windows: friendly name -> \\Device\\NPF_{GUID}
        try:
            from scapy.arch.windows import get_windows_if_list  # type: ignore

            for item in get_windows_if_list():
                name = item.get("name")
                guid = item.get("guid")
                if not name:
                    continue
                # Keep adapters someone would actually capture on, and drop the
                # filter drivers and pseudo-interfaces that clutter the Windows
                # list. Matching is on specific tokens rather than a blanket
                # "has a dash" rule, which previously dropped real adapters like
                # "Wi-Fi" on some machines.
                low = name.lower()
                noise = (
                    "wfp", "qos packet scheduler", "lightweight filter",
                    "native wifi filter", "virtual wifi filter",
                    "npcap packet driver", "mac layer",
                    "pseudo", "loopback", "teredo", "6to4", "ip-https",
                    "bluetooth", "kernel debugger",
                )
                if low.startswith("local area connection*") or any(n in low for n in noise):
                    continue
                if guid:
                    # nfstream needs \Device\NPF_{GUID} with single backslashes.
                    # A raw string keeps them literal; f"\\Device..." would work
                    # too but the earlier version over-escaped to \\\\Device\\\\,
                    # which nfstream rejects as an invalid interface name.
                    mapping[name] = r"\Device\NPF_" + guid
                else:
                    mapping[name] = name
        except Exception:  # noqa: BLE001
            pass

        if mapping:
            return mapping

        # Non-Windows, or scapy unavailable: nfstream takes the plain name.
        try:
            import psutil

            for name in psutil.net_if_addrs().keys():
                mapping[name] = name
        except Exception:  # noqa: BLE001
            pass

        return mapping

    @staticmethod
    def resolve_source(chosen: str) -> str:
        """Turn a chosen dropdown value into what nfstream should open."""
        return NfstreamSource.interface_map().get(chosen, chosen)

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
            # Resolve the friendly name to the device path nfstream needs. On
            # Windows this is \\Device\\NPF_{GUID}; elsewhere it is unchanged.
            source = self.resolve_source(self.interface)
            streamer = NFStreamer(
                source=source,
                statistical_analysis=True,
                idle_timeout=self.idle_timeout,
                active_timeout=self.active_timeout,
                # One meter, so nfstream does not spawn worker processes. On
                # Windows those processes need an "if __name__ == '__main__'"
                # guard that does not exist inside a Streamlit capture thread,
                # and without it capture fails with a misleading "valid
                # interface name" error even when the interface is fine. A
                # single meter runs in-thread and is more than fast enough here.
                n_meters=1,
            )
        except Exception as error:  # noqa: BLE001
            raise CaptureError(
                f"Could not open interface '{self.interface}'. "
                "On Windows this usually means Npcap is missing, the app was "
                "not started from an Administrator terminal, or the chosen "
                "adapter is a virtual one with no traffic. Pick the adapter you "
                "actually use for internet (Wi-Fi or Ethernet). "
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
