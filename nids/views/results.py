"""
Detection Results page.

The full result table for the current session, with the filters the design
document calls for: prediction, source address, protocol and time.
"""

import time

import pandas as pd
import streamlit as st

from ..components import cards
from ..core import state
from ..core.schema import CLASSES
from ..theme import html, COLORS


def _filter_bar(frame: pd.DataFrame) -> pd.DataFrame:
    """Draw the filter controls and return the filtered frame."""
    columns = st.columns([1, 1, 1, 1, 1])

    with columns[0]:
        prediction = st.selectbox("Prediction", ["All"] + CLASSES)

    with columns[1]:
        source = st.text_input("Source address contains", "")

    with columns[2]:
        protocols = ["All"] + sorted(frame["protocol"].dropna().unique().tolist())
        protocol = st.selectbox("Protocol", protocols)

    with columns[3]:
        window = st.selectbox(
            "Time window",
            ["All", "Last 1 min", "Last 5 min", "Last 15 min", "Last hour"],
        )

    with columns[4]:
        min_confidence = st.slider("Min confidence", 0.0, 1.0, 0.0, 0.05)

    filtered = frame.copy()

    if prediction != "All":
        filtered = filtered[filtered["prediction"] == prediction]

    if source:
        mask = filtered["src_ip"].astype(str).str.contains(source, case=False, na=False)
        filtered = filtered[mask]

    if protocol != "All":
        filtered = filtered[filtered["protocol"] == protocol]

    if window != "All":
        seconds = {
            "Last 1 min": 60,
            "Last 5 min": 300,
            "Last 15 min": 900,
            "Last hour": 3600,
        }[window]
        filtered = filtered[filtered["ts"] >= time.time() - seconds]

    filtered = filtered[filtered["confidence"] >= min_confidence]

    return filtered


def render() -> None:
    cards.page_header(
        "DETECTION RESULTS",
        "Every classified flow in the current session",
    )

    frame = state.flows_frame()

    if frame.empty:
        cards.empty_state(
            "No flows in this session.",
            "Start capture on the Live Monitoring page or upload a CSV.",
        )
        return

    filtered = _filter_bar(frame)

    st.markdown(html("<div style='height:0.8rem;'></div>"), unsafe_allow_html=True)

    malicious = int((filtered["prediction"] != "BENIGN").sum())
    mean_confidence = float(filtered["confidence"].mean()) if len(filtered) else 0.0

    cards.kpi_grid(
        [
            {
                "label": "Rows shown",
                "value": f"{len(filtered):,}",
                "color": COLORS["accent"],
                "delta": f"of {len(frame):,} total",
            },
            {"label": "Malicious", "value": f"{malicious:,}", "color": COLORS["attack"]},
            {
                "label": "Normal",
                "value": f"{len(filtered) - malicious:,}",
                "color": COLORS["normal"],
            },
            {
                "label": "Mean confidence",
                "value": f"{mean_confidence:.3f}",
                "color": COLORS["probe"],
            },
        ]
    )

    if filtered.empty:
        cards.empty_state("No rows match the current filters.")
        return

    cards.section("Results")

    rows = filtered.sort_values("ts", ascending=False).head(300).to_dict("records")
    cards.flow_table(rows, height=460)

    st.markdown(html("<div style='height:0.6rem;'></div>"), unsafe_allow_html=True)

    export_columns = st.columns(2)

    with export_columns[0]:
        display = filtered[
            ["ts", "src_ip", "src_port", "dst_ip", "dst_port", "protocol",
             "prediction", "confidence"]
        ].copy()
        display["ts"] = pd.to_datetime(display["ts"], unit="s")

        st.download_button(
            "Download filtered results (CSV)",
            display.to_csv(index=False),
            file_name=f"nids_detections_{int(time.time())}.csv",
            mime="text/csv",
            width="stretch",
        )

    with export_columns[1]:
        report = _text_report(filtered)
        st.download_button(
            "Download summary report (TXT)",
            report,
            file_name=f"nids_report_{int(time.time())}.txt",
            mime="text/plain",
            width="stretch",
        )


def _text_report(frame: pd.DataFrame) -> str:
    """
    Plain-text summary.

    The design document lists a PDF export. Text is the honest placeholder until
    reportlab is added; it carries the same content and needs no extra
    dependency, so the button is never a dead end.
    """
    engine = state.get_engine()
    malicious = frame[frame["prediction"] != "BENIGN"]

    lines = [
        "NETWORK INTRUSION DETECTION SYSTEM",
        "Detection summary report",
        "=" * 52,
        f"Generated       : {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Engine mode     : {engine.status.mode}",
        f"Model           : {engine.status.model_name}",
        f"Flows analysed  : {len(frame):,}",
        f"Malicious flows : {len(malicious):,} ({len(malicious) / max(len(frame), 1) * 100:.2f}%)",
        f"Normal flows    : {len(frame) - len(malicious):,}",
        "",
        "DETECTIONS BY CLASS",
        "-" * 52,
    ]

    for label, count in malicious["prediction"].value_counts().items():
        lines.append(f"  {label:<18} {count:>8,}")

    if not malicious.empty:
        lines += ["", "TOP SOURCE ADDRESSES", "-" * 52]
        for address, count in malicious["src_ip"].value_counts().head(10).items():
            lines.append(f"  {address:<18} {count:>8,} malicious flows")

        lines += ["", "MEAN CONFIDENCE BY CLASS", "-" * 52]
        for label, value in malicious.groupby("prediction")["confidence"].mean().items():
            lines.append(f"  {label:<18} {value:>8.3f}")

    if engine.status.mode == "SIMULATION":
        lines += [
            "",
            "NOTE",
            "-" * 52,
            "  The engine is running in simulation mode. These results come from",
            "  generated traffic, not from a trained model scoring real flows.",
        ]

    return "\n".join(lines)
