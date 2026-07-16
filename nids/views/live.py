"""
Live Monitoring page.

Everything here is rendered by Streamlit. There is no iframe and no side
channel, because neither survives deployment: a second port is unreachable from
a host, and Streamlit Community Cloud does not serve this app's static folder,
so a panel delivered that way never loads.

So the live view is built the same way as the rest of the dashboard, and the
cost of that is honest: a fragment reruns on a timer, and a rerun replaces
elements. The work here is to make that replacement as cheap as possible rather
than to pretend it does not happen.

  * One fragment, holding only what changes. The controls, the header and the
    sidebar are outside it and are never touched by the timer.
  * The radar is the in-page CSS radar, not a canvas in an iframe. An iframe
    reloads on every rerun, which is a visible flash; an element is swapped in
    place. Its sweep stays continuous across reruns through a negative
    animation-delay computed from the server clock.
  * The charts are inline SVG, not Plotly. Plotly rebuilds its JavaScript chart
    on every render and is the heaviest thing on a timed page.
  * Two seconds by default, and adjustable. Slower means less movement.

Scoring still happens on the pipeline thread, not here, so detections keep being
logged while you are on another page and the render path stays light.
"""

import time

import streamlit as st

from ..components import cards, charts, radar
from ..core import state
from ..core.capture import NfstreamSource, PcapSource, SimulatedSource
from ..theme import COLORS, html


def _controls() -> None:
    """Capture source selector and start/stop buttons."""
    capture = state.get_capture()
    settings = state.settings()

    columns = st.columns([1.3, 1, 1, 1, 1.2])

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
                "plus Npcap and an Administrator terminal, and is not available "
                "on a deployed app."
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
        settings["refresh_seconds"] = st.number_input(
            "Refresh (s)", 1, 30, int(settings["refresh_seconds"]),
            help=(
                "How often the live panel redraws. Raising this makes the page "
                "calmer; the radar sweep keeps animating either way."
            ),
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


def _live_panel() -> None:
    """
    The only part that reruns on the timer.

    Deliberately holds nothing but light markup: KPI cards, the CSS radar, the
    flow table and two inline SVGs. No Plotly, no iframe, no component.
    """
    capture = state.get_capture()
    settings = state.settings()
    stats = state.stats()

    cards.kpi_grid(
        [
            {
                "label": "Total flows",
                "value": f"{stats['total']:,}",
                "color": COLORS["accent"],
                "delta": "streaming" if capture.running else "capture stopped",
            },
            {
                "label": "Malicious",
                "value": f"{stats['malicious']:,}",
                "color": COLORS["attack"],
                "delta": f"{stats['rate']:.1f}% of traffic",
            },
            {
                "label": "Normal",
                "value": f"{stats['normal']:,}",
                "color": COLORS["normal"],
                "delta": "no action required",
            },
            {
                "label": "Active alerts",
                "value": f"{stats['alerts']:,}",
                "color": COLORS["probe"],
                "delta": f"conf \u2265 {settings['alert_threshold']:.2f}",
            },
        ]
    )

    left, right = st.columns([1.5, 1])

    with left:
        cards.section("Live traffic flows")
        cards.flow_table(state.recent_flows(80), height=430)

    with right:
        cards.section("Threat radar")
        blips = radar.build_blips(state.recent_flows(160))
        radar.render(
            blips,
            height=340,
            retention=settings["radar_retention"],
            sweep_period=settings["sweep_period"],
            scanning=capture.running,
            show_benign=settings["show_benign_on_radar"],
        )

    st.markdown(html("<div style='height:0.5rem;'></div>"), unsafe_allow_html=True)

    frame = state.flows_frame()
    chart_left, chart_right = st.columns(2)

    with chart_left:
        cards.section("Threats over time")
        st.markdown(html(charts.svg_sparkline(frame)), unsafe_allow_html=True)

    with chart_right:
        cards.section("Attack distribution")
        counts = {}
        if not frame.empty:
            counts = (
                frame[frame["prediction"] != "BENIGN"]["prediction"].value_counts().to_dict()
            )
        st.markdown(html(charts.svg_donut(counts)), unsafe_allow_html=True)

    recent_alerts = state.alerts(1)
    if recent_alerts:
        cards.alert_bar(recent_alerts[0])


def render() -> None:
    capture = state.get_capture()
    settings = state.settings()

    # The pipeline scores captured flows on its own thread. Cached, so this
    # builds it once per process rather than once per rerun.
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
        "Real-time flow capture, extraction and classification",
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

    # Only the fragment reruns, and only while capture is running. Passing
    # run_every=None parks it, so a stopped dashboard does not spin the CPU.
    interval = settings["refresh_seconds"] if capture.running else None
    st.fragment(_live_panel, run_every=interval)()

    st.caption(
        f"{pipeline.scored:,} flows scored this session \u00b7 "
        f"panel redraws every {settings['refresh_seconds']}s while capturing"
    )
