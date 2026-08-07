"""
Scoring pipeline.

Capture produces raw flows on one thread. The live panel is a static page that
never triggers a rerun. So nothing in the render path is left to do the scoring,
and this thread takes it over:

    capture queue -> engine.predict -> store -> live.json (browser) -> SQLite

Running it here rather than in the page has a second benefit: detections keep
being logged while the user is on another page, or with no browser open at all.
Previously, scoring only happened when the Live Monitoring page happened to be
rerunning, which meant the log quietly had holes in it.

The browser is fed through a JSON file written into Streamlit's static folder
rather than through a socket. See core/livefile.py for why.
"""

import threading
import time
from typing import Optional

from . import db
from .capture import CaptureController
from .engine import Engine
from .store import FlowStore

# How often the pipeline drains the capture queue and republishes the snapshot.
# This is not a page refresh interval: the page is never re-rendered. It only
# controls how fresh the file the browser polls is, and how much batching the
# model gets, since scoring one flow at a time would be wasteful.
DRAIN_INTERVAL = 0.5
DRAIN_LIMIT = 400


class Pipeline:
    """Owns the scoring thread."""

    def __init__(self, capture: CaptureController, engine: Engine, store: FlowStore):
        self.capture = capture
        self.engine = engine
        self.store = store
        self.livefile = None  # set by the app once the writer exists
        self.alert_threshold = 0.70
        self.scored = 0
        self.error: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return

        # The table must exist before the thread's first write. Leaving this to
        # whichever page happens to load first is how the previous version ended
        # up writing into a database with no table in it.
        db.init()

        self._stop = threading.Event()

        def worker():
            while not self._stop.is_set():
                try:
                    session_id_before = self.store.session_id
                    rows = self.capture.drain(limit=DRAIN_LIMIT)
                    if rows:
                        self.engine.predict_records(rows)
                        if self.store.session_id == session_id_before:
                            raised = self.store.add(rows, self.alert_threshold)
                            self.scored += len(rows)
                            if raised:
                                db.write_detections(raised, source="live")

                    # Republish even when no flows arrived, so the panel still
                    # learns that capture stopped or started.
                    if self.livefile is not None:
                        self.livefile.publish(
                            store=self.store,
                            capturing=self.capture.running,
                            source=self.capture.source_name,
                            threshold=self.alert_threshold,
                        )

                except Exception as error:  # noqa: BLE001 - surfaced in the interface
                    self.error = f"Pipeline error: {error}"

                self._stop.wait(DRAIN_INTERVAL)

        self._thread = threading.Thread(target=worker, name="nids-pipeline", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
