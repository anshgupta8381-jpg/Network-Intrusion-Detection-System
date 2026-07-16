"""
Flow store.

Scored flows used to live in st.session_state, which worked while the page
itself did the scoring on every rerun. The live panel no longer reruns, so the
scoring happens in a background thread instead, and a background thread cannot
touch session state. The buffer therefore lives here, at process level, behind a
lock.

This is also the more honest place for it. Capture was always process-level, and
keeping a per-session copy of the same flows only ever made sense because the
scoring was stuck in the render path.
"""

import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional

import pandas as pd

# Flows kept in memory for the tables and charts. Older flows are dropped;
# anything malicious has already been written to SQLite by then.
BUFFER_SIZE = 3000
ALERT_SIZE = 200


class FlowStore:
    """Thread-safe ring buffer of scored flows, plus the alert feed."""

    def __init__(self, size: int = BUFFER_SIZE):
        self._lock = threading.Lock()
        self._flows: Deque[Dict] = deque(maxlen=size)
        self._alerts: Deque[Dict] = deque(maxlen=ALERT_SIZE)
        self.started_at = time.time()
        self._seq = 0

    # -- writing ---------------------------------------------------------

    def add(self, rows: List[Dict], alert_threshold: float) -> List[Dict]:
        """
        Append scored flows and return the ones that crossed the threshold.

        Each row gets a monotonic sequence number so the browser can tell what
        it has already drawn after a reconnect.
        """
        if not rows:
            return []

        raised = []
        with self._lock:
            for row in rows:
                self._seq += 1
                row["seq"] = self._seq
                self._flows.append(row)

                if (
                    row.get("prediction", "BENIGN") != "BENIGN"
                    and row.get("confidence", 0) >= alert_threshold
                ):
                    self._alerts.appendleft(row)
                    raised.append(row)

        return raised

    # -- reading ---------------------------------------------------------

    def recent(self, count: int = 200) -> List[Dict]:
        """Newest flows first."""
        with self._lock:
            return list(self._flows)[-count:][::-1]

    def since(self, seq: int, limit: int = 400) -> List[Dict]:
        """Flows newer than a sequence number, oldest first."""
        with self._lock:
            rows = [f for f in self._flows if f.get("seq", 0) > seq]
        return rows[-limit:]

    def alerts(self, count: int = 200) -> List[Dict]:
        with self._lock:
            return list(self._alerts)[:count]

    def frame(self) -> pd.DataFrame:
        with self._lock:
            rows = list(self._flows)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def stats(self) -> Dict:
        """Headline counters for the KPI cards."""
        with self._lock:
            flows = list(self._flows)
            alert_count = len(self._alerts)

        total = len(flows)
        malicious = sum(1 for f in flows if f.get("prediction", "BENIGN") != "BENIGN")
        return {
            "total": total,
            "malicious": malicious,
            "normal": total - malicious,
            "alerts": alert_count,
            "rate": (malicious / total * 100) if total else 0.0,
        }

    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    # -- lifecycle -------------------------------------------------------

    def clear(self) -> None:
        with self._lock:
            self._flows.clear()
            self._alerts.clear()
            self.started_at = time.time()

    def uptime(self) -> float:
        return time.time() - self.started_at


_store: Optional[FlowStore] = None
_store_lock = threading.Lock()


def get_store() -> FlowStore:
    """One store per process."""
    global _store
    with _store_lock:
        if _store is None:
            _store = FlowStore()
        return _store
