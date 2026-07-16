"""
Network Intrusion Detection System - dashboard entry point.

Run from the project root:

    streamlit run nids/app.py

The pages live in nids/views. Navigation is a styled radio in the sidebar rather
than Streamlit's built-in multipage router, because the router does not allow the
navigation to be restyled and the sidebar is a large part of the look here.
"""

import os
import sys

import streamlit as st

# Allow "streamlit run nids/app.py" from the project root by putting the parent
# directory on the path before the package imports run.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nids import theme                                    # noqa: E402
from nids.theme import html                               # noqa: E402
from nids.core import state                               # noqa: E402
from nids.views import (                                   # noqa: E402
    alerts,
    home,
    live,
    performance,
    results,
    settings as settings_view,
    upload,
)

PAGES = {
    "Overview": home.render,
    "Live Monitoring": live.render,
    "Upload & Analyze": upload.render,
    "Detection Results": results.render,
    "Model Performance": performance.render,
    "Alerts & Logs": alerts.render,
    "Settings / About": settings_view.render,
}


def sidebar() -> str:
    """Draw the sidebar and return the selected page name."""
    from nids.theme import COLORS

    engine = state.get_engine()
    capture = state.get_capture()

    with st.sidebar:
        st.markdown(html("""
            <div class="brand">
                <div class="brand-mark"></div>
                <div>
                    <div class="brand-name">NIDS</div>
                    <div class="brand-tag">Threat Detection</div>
                </div>
            </div>
            """), unsafe_allow_html=True)

        selected = st.radio(
            "Navigation",
            list(PAGES.keys()),
            label_visibility="collapsed",
            key="nav",
        )

        st.markdown(html("<div style='height:1.5rem;'></div>"), unsafe_allow_html=True)

        # Capture status.
        if capture.running:
            chip_color = COLORS["normal"]
            chip_text = f"Capturing {capture.source_name}"
        else:
            chip_color = COLORS["text_muted"]
            chip_text = "Capture stopped"

        # Engine status. Simulation is called out clearly rather than dressed up
        # as a working model, because a dashboard that looks live while running on
        # generated data is worse than one that admits it.
        if engine.status.mode == "MODEL":
            engine_color = COLORS["accent"]
            engine_text = f"Model: {engine.status.model_name}"
        else:
            engine_color = COLORS["probe"]
            engine_text = "Simulation mode"

        stats = state.stats()

        st.markdown(html(f"""
            <div class="status-chip" style="--chip-color:{chip_color};">
                <span class="dot"></span>{chip_text}
            </div>
            <div class="status-chip" style="--chip-color:{engine_color};">
                <span class="dot"></span>{engine_text}
            </div>
            <div class="status-chip" style="--chip-color:{COLORS['attack']};">
                <span class="dot"></span>{stats['malicious']:,} threats / {stats['total']:,} flows
            </div>
            """), unsafe_allow_html=True)

    return selected


def main() -> None:
    st.set_page_config(
        page_title="NIDS | Threat Detection",
        page_icon="\u25C9",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    theme.inject(st)
    state.init()

    # Bring the background stack up on first load: the stream server that feeds
    # the live panel, and the thread that scores captured flows. Both are cached
    # resources, so this builds them once per process rather than once per rerun.
    state.get_livefile()
    state.get_pipeline()

    state.seed_demo()

    # Bring simulated traffic up on first load so the dashboard is already live
    # when someone opens the link. Only fires once per process; pressing Stop
    # is respected. Disable with NIDS_AUTOSTART=0.
    state.autostart_demo()

    page = sidebar()
    PAGES[page]()


if __name__ == "__main__":
    main()
