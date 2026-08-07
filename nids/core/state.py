"""
Shared state.

The engine, the capture controller, the scoring pipeline and the stream server
must survive Streamlit reruns and must not be rebuilt on every keystroke, so all
of them are cached as resources.

Scored flows no longer live in session state. The live panel is a static iframe
fed by the stream server, so the scoring happens on a background thread, and a
background thread cannot touch session state. The flows live in core.store
instead. This module keeps the same accessors it always had, so the other pages
did not have to care where the buffer moved to.
"""

import os
import time
from typing import Dict, List

import streamlit as st

from . import db
from .capture import CaptureController
from .engine import Engine
from .pipeline import Pipeline
from .store import BUFFER_SIZE, get_store

DEFAULT_SETTINGS = {
    "interface": "Simulated",
    "refresh_seconds": 2,
    "alert_threshold": 0.70,
    "flows_per_second": 6.0,
    "attack_bias": 1.0,
    "radar_retention": 45,
    "sweep_period": 4.0,
    "show_benign_on_radar": False,
    "sound_alerts": False,
}


@st.cache_resource
def get_engine() -> Engine:
    """One engine per server process."""
    return Engine()


@st.cache_resource
def get_capture() -> CaptureController:
    """One capture controller per server process."""
    return CaptureController()


@st.cache_resource
def get_pipeline() -> Pipeline:
    """
    The scoring thread.

    Started once and kept running for the life of the process, so detections
    keep being logged even when nobody is looking at the Live Monitoring page.
    """
    pipeline = Pipeline(get_capture(), get_engine(), get_store())
    pipeline.start()
    return pipeline


def init() -> None:
    """Populate session state on first load."""
    if "initialised" in st.session_state:
        return

    # The log table must exist before anything tries to write a detection.
    # seed_demo runs before the capture controller is ever touched, so this
    # cannot be left to whichever component happens to be built first.
    db.init()

    st.session_state.initialised = True
    st.session_state.batch_results = None
    st.session_state.batch_name = None
    st.session_state.settings = dict(DEFAULT_SETTINGS)
    st.session_state.session_start = time.time()
    st.session_state.page = "Overview"
    st.session_state.seeded = False


def settings() -> Dict:
    return st.session_state.settings


def alerts(count: int = 200) -> List[Dict]:
    """Recent alerts, newest first."""
    return get_store().alerts(count)


def add_flows(rows: List[Dict]) -> List[Dict]:
    """
    Add scored flows to the store, raise alerts, and persist.

    Only the demo seed and the batch path use this now; live flows go through
    the pipeline thread, which writes to the store directly.
    """
    if not rows:
        return []

    raised = get_store().add(rows, settings()["alert_threshold"])
    if raised:
        db.write_detections(raised, source="live")
    return raised


def flows_frame():
    """Rolling buffer as a DataFrame, newest last."""
    return get_store().frame()


def recent_flows(count: int = 200) -> List[Dict]:
    """Newest flows first."""
    return get_store().recent(count)


def stats() -> Dict:
    """Headline counters for the KPI cards."""
    return get_store().stats()


def seed_demo(count: int = 240) -> None:
    """
    Fill the buffer once on first load.

    An empty dashboard makes it impossible to judge the layout, so the first
    visit gets a short history. Live capture appends to this and the settings
    page can clear it.
    """
    if st.session_state.seeded or get_store().stats()["total"]:
        st.session_state.seeded = True
        return

    from .simulator import generate_batch

    rows = generate_batch(count, attack_bias=settings()["attack_bias"], spread_seconds=900)
    engine = get_engine()
    engine.predict_records(rows)
    add_flows(rows)
    st.session_state.seeded = True


_autostarted = False


def autostart_demo() -> None:
    """
    Start simulated capture once, on the first load of the process.

    Without this, a visitor opening the app finds the radar parked on STANDBY
    and has to know to press Start. That is the right default for someone
    running this on their own machine to watch their own network, and the wrong
    one for a deployed demo, where the whole point is that the dashboard is
    already alive when the link is opened.

    It only ever fires once per process, so pressing Stop is respected rather
    than being undone on the next rerun. It also never overrides a capture that
    is already running, so it cannot interfere with a real interface.

    Turn it off by setting NIDS_AUTOSTART=0 in the environment.
    """
    global _autostarted

    if _autostarted:
        return
    _autostarted = True

    if os.environ.get("NIDS_AUTOSTART", "1") == "0":
        return

    capture = get_capture()
    if capture.running:
        return

    from .capture import SimulatedSource

    capture.start(
        SimulatedSource(
            flows_per_second=settings()["flows_per_second"],
            attack_bias=settings()["attack_bias"],
        )
    )


def reset_session() -> None:
    """Clear the live buffer and alert feed without touching the SQLite log."""
    # Drain any lingering flows from the capture queue before clearing the store
    # so the background pipeline doesn't score them and write them back.
    get_capture().drain(limit=4000)
    
    get_store().clear()
    st.session_state.seeded = False
    st.session_state.session_start = time.time()
