"""
Live snapshot writer.

This replaces the side-channel HTTP server that the previous version used.

The reason is deployment. That server bound its own port on 127.0.0.1, which is
fine when the browser and the server are the same machine and useless anywhere
else: on a host, 127.0.0.1 in the browser means the viewer's own laptop, and
Streamlit Community Cloud exposes only the one Streamlit port anyway. The panel
would simply have come up blank.

So the panel now travels over Streamlit's own port, through its static file
serving:

    static/panel.html   the panel page, written here at startup
    static/live.json    the current snapshot, rewritten by the pipeline

Streamlit serves both at /app/static/... on the same origin as the app, reading
them from disk on every request. Live Monitoring points an iframe at panel.html
with a src that never changes, so Streamlit renders it once and never touches it
again, and the page polls live.json for itself.

That means the browser polls rather than being pushed to, and the data is up to
a second old. The trade is worth it: the blink was never about how the data
arrived, it was about Streamlit re-rendering the page. Nothing here is
re-rendered, so nothing blinks, and this works identically on a laptop and on a
deployed host.

The snapshot is written to a temporary file and then renamed. Rename is atomic,
so a browser polling mid-write reads either the old file or the new one, never
half of each.
"""

import json
import os
import tempfile
import threading
import time
from typing import Dict, List, Optional

# Flows carried in each snapshot. The panel only draws the most recent ones, and
# it tracks sequence numbers, so this only has to be large enough that a polling
# browser cannot miss flows between two polls.
SNAPSHOT_FLOWS = 400


def _wire(row: Dict) -> Dict:
    """
    Trim a flow down to what the panel draws.

    The full record carries twenty feature columns the browser has no use for;
    writing them would multiply the file size for nothing.
    """
    return {
        "ts": row.get("ts", time.time()),
        "src": row.get("src_ip", ""),
        "sport": row.get("src_port", 0),
        "dst": row.get("dst_ip", ""),
        "dport": row.get("dst_port", 0),
        "proto": row.get("protocol", ""),
        "pred": row.get("prediction", "BENIGN"),
        "conf": round(float(row.get("confidence", 0)), 3),
        "dur": round(float(row.get("Flow Duration", 0)) / 1_000_000, 2),
        "seq": row.get("seq", 0),
    }


class LiveFile:
    """Owns the two files under the app's static folder."""

    def __init__(self, static_dir: str, panel_html: str):
        self.static_dir = static_dir
        self.panel_path = os.path.join(static_dir, "panel.html")
        self.live_path = os.path.join(static_dir, "live.json")
        self._lock = threading.Lock()
        self.writes = 0

        os.makedirs(static_dir, exist_ok=True)

        # The panel page is generated rather than committed, so it can never
        # drift out of step with the theme colours it is built from.
        with open(self.panel_path, "w", encoding="utf-8") as handle:
            handle.write(panel_html)

        # Write an empty snapshot immediately. Without it a panel that loads
        # before the pipeline's first tick would get a 404 and show an error for
        # no reason.
        self._write({"seq": 0, "capturing": False, "source": "None",
                     "threshold": 0.7, "flows": [], "stats": {}})

    def _write(self, payload: Dict) -> None:
        body = json.dumps(payload, separators=(",", ":"))

        # Temp file in the same directory, then rename: rename is atomic within
        # a filesystem, so a reader never sees a partial file.
        fd, tmp = tempfile.mkstemp(dir=self.static_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
            os.replace(tmp, self.live_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def publish(self, store, capturing: bool, source: str, threshold: float) -> None:
        """Rewrite the snapshot from the current store contents."""
        with self._lock:
            flows = store.recent(SNAPSHOT_FLOWS)[::-1]  # oldest first
            self._write(
                {
                    "seq": store.last_seq(),
                    "capturing": bool(capturing),
                    "source": source,
                    "threshold": threshold,
                    "flows": [_wire(f) for f in flows],
                    "stats": store.stats(),
                    "at": time.time(),
                }
            )
            self.writes += 1

    @property
    def panel_url(self) -> str:
        """Relative URL Streamlit serves the panel from."""
        return "/app/static/panel.html"


_livefile: Optional[LiveFile] = None
_lock = threading.Lock()


def get_livefile(static_dir: str, panel_html: str) -> LiveFile:
    """One writer per process."""
    global _livefile
    with _lock:
        if _livefile is None:
            _livefile = LiveFile(static_dir, panel_html)
        return _livefile
