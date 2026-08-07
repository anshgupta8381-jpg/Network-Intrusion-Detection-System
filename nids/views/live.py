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

from ..components import cards, charts, radar, radar_live
from ..core import state
from ..core.capture import NfstreamSource, PcapSource, SimulatedSource
from ..theme import COLORS, html


def _controls() -> None:
    """Capture-mode toggle (Simulation vs Live) and start/stop buttons."""
    capture = state.get_capture()
    settings = state.settings()

    nfstream_ready = NfstreamSource.available()

    # The mode toggle. Two clear choices rather than a dropdown: Simulation for
    # the generated-traffic demo, Live for real capture through nfstream.
    mode_col, cfg_col, refresh_col, alert_col, button_col = st.columns(
        [1.5, 1.3, 1, 1, 1.2]
    )

    with mode_col:
        mode = st.radio(
            "Capture mode",
            ["Simulation", "Live"],
            horizontal=True,
            help=(
                "Simulation generates realistic attack traffic and needs no "
                "drivers. Live captures real traffic from a network interface "
                "and needs nfstream plus Npcap installed."
            ),
        )

        # Stop if mode toggled while running
        is_sim = (capture.source_name == "Simulated")
        is_live = (capture.source_name == "nfstream")
        if (mode == "Live" and is_sim) or (mode == "Simulation" and is_live):
            if capture.running:
                capture.stop()
                st.rerun()

    interface = None

    with cfg_col:
        if mode == "Live":
            if nfstream_ready:
                interfaces = NfstreamSource.list_interfaces()
                if interfaces:
                    interface = st.selectbox("Interface", interfaces)
                else:
                    interface = st.text_input("Interface", value="Wi-Fi")
            else:
                # Live chosen but the library is missing: say so plainly instead
                # of failing when Start is pressed.
                st.markdown(
                    html(
                        f"""
                        <div style="font-size:0.72rem;line-height:1.5;
                                    color:{COLORS['probe']};padding-top:0.4rem;">
                        nfstream not installed.<br>
                        <code>pip install nfstream</code><br>
                        and install Npcap.
                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )
        else:
            settings["flows_per_second"] = st.number_input(
                "Flows/sec", 0.5, 60.0, float(settings["flows_per_second"]), 0.5
            )

    with refresh_col:
        settings["refresh_seconds"] = st.number_input(
            "Refresh (s)", 1, 30, int(settings["refresh_seconds"]),
            help="How often the live panel redraws. The radar keeps animating either way.",
        )

    with alert_col:
        settings["alert_threshold"] = st.slider(
            "Alert conf.", 0.0, 1.0, float(settings["alert_threshold"]), 0.05
        )

    with button_col:
        st.markdown(html("<div style='height:1.75rem;'></div>"), unsafe_allow_html=True)
        buttons = st.columns(2)

        # In Live mode without nfstream, Start would only raise, so it is disabled.
        can_start = mode == "Simulation" or nfstream_ready

        with buttons[0]:
            if capture.running:
                if st.button("Stop", width="stretch"):
                    capture.stop()
                    st.rerun()
            else:
                if st.button("Start", type="primary", width="stretch", disabled=not can_start):
                    # Unconditionally clear whatever the previous session left behind before starting.
                    # This ensures every new capture starts from 0, and retains the results in the 
                    # Results tab only while stopped.
                    state.reset_session()

                    if mode == "Live":
                        source = NfstreamSource(interface=interface or "Wi-Fi")
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
                if capture.running:
                    capture.stop()
                state.reset_session()
                st.rerun()

    # A one-line honest status under the controls, so it is always clear whether
    # the numbers on screen are generated or real.
    if capture.running and capture.source_name == "nfstream":
        st.caption(
            "Live capture is on. This shows real traffic through your own machine, "
            "so it will mostly read BENIGN unless something is actually attacking it."
        )
    elif capture.running:
        st.caption(
            "Simulation is on. The traffic below is generated for demonstration, "
            "not captured from the network."
        )


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
        # The heading names the actual source, so it is always clear whether the
        # rows below are generated or captured from a real interface.
        if capture.running and capture.source_name == "nfstream":
            cards.section("Live captured flows")
        elif capture.running:
            cards.section("Simulated traffic flows")
        else:
            cards.section("Traffic flows")
        cards.flow_table(state.recent_flows(80), height=430)

    with right:
        cards.section("Threat radar")
        blips = radar.build_blips(state.recent_flows(160))
        # Self-animating canvas radar: its sweep runs on requestAnimationFrame
        # inside the component, so the page rerunning around it does not reset
        # the sweep. Only the blips update when the page refreshes.
        radar_live.render(
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
