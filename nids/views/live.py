"""
Live Monitoring page.

This page does not refresh. That is the point.

Everything that changes as traffic arrives lives in the panel, which Streamlit
serves from the app's static folder and which is embedded here in an iframe
whose src never changes. Streamlit renders that iframe once and then leaves it
alone, so there is no timer, no rerun, and nothing being replaced. The panel
polls its own snapshot file and draws each flow as it is scored.

What is left in Streamlit is the part that only changes when the user changes
it: the capture controls.

The earlier design ran the whole page on a timer and re-rendered it every few
seconds. Fragments narrowed the scope of that but not the mechanism; a rerun
still replaces elements, and replacing elements is what the eye reads as a
blink. The only way to stop it is to stop re-rendering, which is what this does.
"""

import time
from urllib.parse import urlencode

import streamlit as st

from ..components import cards
from ..core import state
from ..core.capture import NfstreamSource, PcapSource, SimulatedSource
from ..theme import COLORS, html

PANEL_HEIGHT = 900


def _controls() -> None:
    """Capture source selector and start/stop buttons."""
    capture = state.get_capture()
    settings = state.settings()

    columns = st.columns([1.4, 1, 1, 1, 1.2])

    with columns[0]:
        options = ["Simulated"]
        if NfstreamSource.available():
            options.append("Live interface")
            options.append("PCAP file")

        source_kind = st.selectbox(
            "Capture source",
            options,
            help=(
                "Simulated needs no drivers. Live interface requires nfstream "
                "plus Npcap and an Administrator terminal."
            ),
        )

    interface = None
    pcap_path = None

    with columns[1]:
        if source_kind == "Live interface":
            interfaces = NfstreamSource.list_interfaces()
            if interfaces:
                interface = st.selectbox("Interface", interfaces)
            else:
                interface = st.text_input("Interface", value="Wi-Fi")
        elif source_kind == "PCAP file":
            pcap_path = st.text_input("PCAP path", value="data/sample.pcap")
        else:
            settings["flows_per_second"] = st.number_input(
                "Flows/sec", 0.5, 60.0, float(settings["flows_per_second"]), 0.5
            )

    with columns[2]:
        settings["sweep_period"] = st.number_input(
            "Sweep (s)", 1.0, 10.0, float(settings["sweep_period"]), 0.5,
            help="Seconds for one full rotation of the radar.",
        )

    with columns[3]:
        settings["alert_threshold"] = st.slider(
            "Alert conf.", 0.0, 1.0, float(settings["alert_threshold"]), 0.05
        )

    with columns[4]:
        st.markdown(html("<div style='height:1.75rem;'></div>"), unsafe_allow_html=True)
        buttons = st.columns(2)

        with buttons[0]:
            if capture.running:
                if st.button("Stop", width="stretch"):
                    capture.stop()
                    st.rerun()
            else:
                if st.button("Start", type="primary", width="stretch"):
                    if source_kind == "Live interface":
                        source = NfstreamSource(interface=interface)
                    elif source_kind == "PCAP file":
                        source = PcapSource(path=pcap_path)
                    else:
                        source = SimulatedSource(
                            flows_per_second=settings["flows_per_second"],
                            attack_bias=settings["attack_bias"],
                        )
                    capture.start(source)
                    time.sleep(0.4)
                    st.rerun()

        with buttons[1]:
            if st.button("Clear", width="stretch"):
                state.reset_session()
                st.rerun()


def render() -> None:
    capture = state.get_capture()
    settings = state.settings()

    # Starting these is what brings the page to life: the pipeline scores
    # captured flows on a thread and republishes the snapshot the panel polls.
    # Both are cached resources, so they are built once per process, not once
    # per rerun.
    livefile = state.get_livefile()
    pipeline = state.get_pipeline()
    pipeline.alert_threshold = settings["alert_threshold"]

    status_color = COLORS["normal"] if capture.running else COLORS["text_muted"]
    status_text = (
        f"Capturing {capture.source_name} \u00b7 {int(capture.uptime())}s"
        if capture.running
        else "Standby"
    )

    cards.page_header(
        "LIVE MONITORING",
        "Streaming flow capture, extraction and classification",
        f'<span class="dot" style="--chip-color:{status_color};"></span>{status_text}',
    )

    _controls()

    if capture.error:
        st.error(capture.error)

    if pipeline.error:
        st.error(pipeline.error)

    if capture.dropped:
        st.warning(
            f"{capture.dropped} flows were dropped because the capture queue "
            "filled up. Lower the capture rate."
        )

    if not capture.running:
        st.caption(
            "Capture is stopped. The panel below keeps polling and starts "
            "drawing again as soon as you press Start; it does not need to be "
            "reloaded."
        )

    # The query string carries the display settings. Changing one of these does
    # change the src, so the panel reloads on that specific edit. That is the
    # right trade: it happens when the user asks for it, not on a timer.
    query = urlencode(
        {
            "retention": settings["radar_retention"],
            "sweep": settings["sweep_period"],
            "benign": "1" if settings["show_benign_on_radar"] else "0",
            "threshold": settings["alert_threshold"],
        }
    )

    # A relative URL on Streamlit's own origin and port. That is what makes the
    # panel work unchanged on a deployed host, where a second port would not be
    # reachable at all.
    st.iframe(f"{livefile.panel_url}?{query}", height=PANEL_HEIGHT)

    st.caption(
        f"Panel polls /app/static/live.json \u00b7 "
        f"{livefile.writes:,} snapshots published \u00b7 "
        f"{pipeline.scored:,} flows scored this session"
    )
