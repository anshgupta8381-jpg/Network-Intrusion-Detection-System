"""
Alerts and Logs page.

The alert feed comes from session state and covers the current session. The log
below it comes from SQLite and survives restarts, which is the difference that
matters when a detection needs to be looked up after the fact.
"""

import time

import pandas as pd
import streamlit as st

from ..components import cards
from ..core import db, state
from ..core.schema import ATTACK_CLASSES, CLASS_DESCRIPTIONS
from ..theme import html, COLORS, class_color


def render() -> None:
    cards.page_header(
        "ALERTS & LOGS",
        "Chronological alert feed and the persisted detection log",
        f'<span class="dot" style="--chip-color:{COLORS["attack"]};"></span>'
        f"{db.total_count():,} logged detections",
    )

    session_alerts = state.alerts()
    log_total = db.total_count()
    last_hour = db.read_detections(limit=10000, since=time.time() - 3600)
    critical = int((last_hour["severity"] == "critical").sum()) if not last_hour.empty else 0

    cards.kpi_grid(
        [
            {
                "label": "Session alerts",
                "value": f"{len(session_alerts):,}",
                "color": COLORS["probe"],
                "delta": "since this page loaded",
            },
            {
                "label": "Logged total",
                "value": f"{log_total:,}",
                "color": COLORS["accent"],
                "delta": "persisted to SQLite",
            },
            {
                "label": "Last hour",
                "value": f"{len(last_hour):,}",
                "color": COLORS["attack"],
                "delta": "detections written",
            },
            {
                "label": "Critical",
                "value": f"{critical:,}",
                "color": COLORS["critical"],
                "delta": "last hour",
            },
        ]
    )

    feed_column, log_column = st.columns([1, 2])

    with feed_column:
        cards.section("Live alert feed")
        cards.alert_feed(session_alerts, limit=12)

    with log_column:
        cards.section("Detection log")

        filters = st.columns([1, 1, 1])

        with filters[0]:
            prediction = st.selectbox("Attack type", ["All"] + ATTACK_CLASSES)
        with filters[1]:
            source = st.text_input("Source address", "")
        with filters[2]:
            window = st.selectbox(
                "Window", ["Last hour", "Last 24 hours", "Last 7 days", "All time"], index=1
            )

        since = {
            "Last hour": time.time() - 3600,
            "Last 24 hours": time.time() - 86400,
            "Last 7 days": time.time() - 604800,
            "All time": None,
        }[window]

        frame = db.read_detections(
            limit=2000,
            since=since,
            prediction=prediction,
            src_ip=source or None,
        )

        if frame.empty:
            cards.empty_state("No detections match these filters.")
        else:
            display = frame.copy()
            display["time"] = pd.to_datetime(display["ts"], unit="s").dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            display = display[
                ["time", "src_ip", "src_port", "dst_ip", "dst_port", "protocol",
                 "prediction", "confidence", "severity", "source"]
            ]

            st.dataframe(display, width="stretch", height=340, hide_index=True)

            st.download_button(
                "Export log as CSV",
                display.to_csv(index=False),
                file_name=f"nids_log_{int(time.time())}.csv",
                mime="text/csv",
            )

    st.markdown(html("<div style='height:1rem;'></div>"), unsafe_allow_html=True)

    with st.expander("What each attack class means"):
        rows = []
        for label in ATTACK_CLASSES:
            color = class_color(label)
            rows.append(
                f"""
                <div style="display:flex;gap:0.8rem;padding:0.45rem 0;
                            border-bottom:1px solid {COLORS['border']};">
                    <div style="min-width:110px;font-family:var(--font-mono);
                                font-size:0.76rem;font-weight:700;color:{color};">{label}</div>
                    <div style="font-size:0.78rem;color:{COLORS['text_secondary']};">
                        {CLASS_DESCRIPTIONS[label]}</div>
                </div>
                """
            )
        st.markdown(html("".join(rows)), unsafe_allow_html=True)
