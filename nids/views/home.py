"""Overview page. Session summary, radar, distribution and recent alerts."""

import time
from datetime import timedelta

import streamlit as st

from ..components import cards, charts, radar
from ..core import state
from ..theme import html, COLORS


def render() -> None:
    engine = state.get_engine()
    capture = state.get_capture()
    settings = state.settings()
    stats = state.stats()

    mode_color = COLORS["accent"] if engine.status.mode == "MODEL" else COLORS["probe"]
    cards.page_header(
        "OVERVIEW",
        "Session summary and current network posture",
        f'<span class="dot" style="--chip-color:{mode_color};"></span>'
        f"{engine.status.mode} &nbsp;|&nbsp; {engine.status.model_name}",
    )

    cards.kpi_grid(
        [
            {
                "label": "Total flows",
                "value": f"{stats['total']:,}",
                "color": COLORS["accent"],
                "delta": f"buffer holds {state.BUFFER_SIZE:,} max",
            },
            {
                "label": "Malicious",
                "value": f"{stats['malicious']:,}",
                "color": COLORS["attack"],
                "delta": f"{stats['rate']:.1f}% of all flows",
            },
            {
                "label": "Normal",
                "value": f"{stats['normal']:,}",
                "color": COLORS["normal"],
                "delta": "classified benign",
            },
            {
                "label": "Active alerts",
                "value": f"{stats['alerts']:,}",
                "color": COLORS["probe"],
                "delta": f"threshold {settings['alert_threshold']:.2f}",
            },
        ]
    )

    left, right = st.columns([1.35, 1])

    with left:
        cards.section("Threat radar")
        blips = radar.build_blips(state.recent_flows(160))
        radar.render(
            blips,
            height=430,
            retention=settings["radar_retention"],
            sweep_period=settings["sweep_period"],
            scanning=capture.running,
            show_benign=settings["show_benign_on_radar"],
        )

        if not capture.running:
            st.caption(
                "Radar is on standby. Start capture on the Live Monitoring page "
                "to resume the sweep."
            )

    with right:
        cards.section("Attack distribution")
        frame = state.flows_frame()

        if not frame.empty:
            counts = (
                frame[frame["prediction"] != "BENIGN"]["prediction"]
                .value_counts()
                .to_dict()
            )
            if counts:
                st.plotly_chart(
                    charts.donut(counts, height=230),
                    width="stretch",
                    config={"displayModeBar": False},
                )
            else:
                cards.empty_state("No attacks detected yet.")
        else:
            cards.empty_state("No traffic in this session.")

        cards.section("Recent alerts")
        cards.alert_feed(state.alerts(5), limit=5)

    st.markdown(html("<div style='height:0.8rem;'></div>"), unsafe_allow_html=True)

    lower_left, lower_right = st.columns([1.35, 1])
    frame = state.flows_frame()

    with lower_left:
        cards.section("Traffic volume")
        st.plotly_chart(
            charts.traffic_volume(frame, height=230),
            width="stretch",
            config={"displayModeBar": False},
        )

    with lower_right:
        cards.section("Top malicious sources")
        st.plotly_chart(
            charts.top_sources(frame, height=230),
            width="stretch",
            config={"displayModeBar": False},
        )

    recent_alerts = state.alerts(1)
    if recent_alerts:
        cards.alert_bar(recent_alerts[0])

    uptime = timedelta(seconds=int(time.time() - st.session_state.session_start))
    st.caption(
        f"Session uptime {uptime} \u00b7 capture source {capture.source_name} \u00b7 "
        f"{engine.status.feature_count} features per flow"
    )
