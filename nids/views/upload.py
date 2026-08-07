"""
Upload and Analyze page.

Batch mode. The user drops a CSV of pre-computed flow records, the schema is
validated against the model feature list, and the whole file is scored at once.
Output matches the live path exactly, so the results and alert screens do not
care where a row came from.
"""

import io
import time

import pandas as pd
import streamlit as st

from ..components import cards, charts
from ..core import db, state
from ..core.schema import align_to_schema
from ..theme import html, COLORS


def _pcap_to_frame(uploaded) -> "pd.DataFrame | None":
    """
    Convert an uploaded packet capture into a flow feature frame.

    Wireshark's own CSV export lists packets, not flows, so it does not carry
    the features the model needs. Instead the raw .pcap is run through nfstream,
    the same flow extractor family used to build CICIDS2017, which computes the
    twenty flow features per connection. The student uploads the capture and the
    conversion happens here, with nothing to export by hand.

    Returns a DataFrame of flow records, or None if the conversion could not run
    (with the reason shown to the user).
    """
    try:
        from nfstream import NFStreamer
    except Exception:
        st.error(
            "Reading .pcap files needs the nfstream library, which is not "
            "installed here. Install it with `pip install nfstream` (and Npcap "
            "on Windows), or upload a flow CSV instead."
        )
        return None

    import os
    import tempfile

    from ..core.capture import NfstreamSource

    # nfstream reads from a path, so the upload is written to a temp file first.
    suffix = ".pcapng" if uploaded.name.lower().endswith(".pcapng") else ".pcap"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(uploaded.getbuffer())
        tmp.close()

        with st.spinner("Converting the capture into flows with nfstream..."):
            # n_meters=1 for the same reason as live capture: without it
            # nfstream spawns worker processes that need an
            # "if __name__ == '__main__'" guard, which does not exist inside
            # Streamlit, and the conversion hangs indefinitely instead of
            # finishing. A single in-thread meter converts a capture of this
            # size in well under a second.
            streamer = NFStreamer(
                source=tmp.name, statistical_analysis=True, n_meters=1
            )
            records = [NfstreamSource.to_features(flow) for flow in streamer]

        if not records:
            return pd.DataFrame()

        st.success(
            f"Converted {len(records):,} flows from the capture. "
            "These are now scored exactly like an uploaded CSV."
        )
        return pd.DataFrame(records)

    except Exception as error:  # noqa: BLE001
        st.error(f"Could not read the capture: {error}")
        return None
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


def _validation_report(frame: pd.DataFrame, missing: list) -> None:
    """Show what was found and what was filled in."""
    found = len(state.get_engine().feature_columns) - len(missing)
    total = len(state.get_engine().feature_columns)

    columns = st.columns(3)

    with columns[0]:
        st.metric("Rows", f"{len(frame):,}")
    with columns[1]:
        st.metric("Features matched", f"{found}/{total}")
    with columns[2]:
        st.metric("Columns in file", f"{len(frame.columns)}")

    if missing:
        st.warning(
            f"{len(missing)} feature columns were not found and have been filled "
            f"with zero. Predictions on this file are less reliable than on a "
            f"complete export. Missing: {', '.join(missing[:8])}"
            + (" ..." if len(missing) > 8 else "")
        )
    else:
        st.success("All model features were found in the uploaded file.")


def render() -> None:
    engine = state.get_engine()

    cards.page_header(
        "UPLOAD & ANALYZE",
        "Batch classification of pre-computed flow records",
        f'<span class="dot" style="--chip-color:{COLORS["accent"]};"></span>'
        f"{len(engine.feature_columns)} features expected",
    )

    upload_column, sample_column = st.columns([2.2, 1])

    with upload_column:
        uploaded = st.file_uploader(
            "Drop a flow CSV or a packet capture here",
            type=["csv", "pcap", "pcapng"],
            help=(
                "Either a CICIDS2017-style flow CSV, or a raw packet capture "
                "(.pcap / .pcapng) from Wireshark or tcpdump. A capture is "
                "converted to flow features automatically, so you do not need "
                "to export a CSV from Wireshark yourself."
            ),
        )

    with sample_column:
        st.markdown(html("<div style='height:1.7rem;'></div>"), unsafe_allow_html=True)
        if st.button("Download sample CSV", width="stretch"):
            from ..core.simulator import sample_csv

            buffer = io.StringIO()
            sample_csv(500).to_csv(buffer, index=False)
            st.download_button(
                "Save sample_flows.csv",
                buffer.getvalue(),
                file_name="sample_flows.csv",
                mime="text/csv",
                width="stretch",
            )

    if uploaded is None:
        if st.session_state.batch_results is None:
            cards.empty_state(
                "No file loaded.",
                "Upload a CSV or a .pcap above, or download the sample file to "
                "see the expected column layout.",
            )
            return
    else:
        is_pcap = uploaded.name.lower().endswith((".pcap", ".pcapng"))

        if is_pcap:
            frame = _pcap_to_frame(uploaded)
            if frame is None:
                return
        else:
            try:
                frame = pd.read_csv(uploaded)
            except Exception as error:  # noqa: BLE001
                st.error(f"Could not read the file: {error}")
                return

        if frame.empty:
            st.error("The file has no rows." if not is_pcap else
                     "No flows were found in that capture. It may be empty or "
                     "contain only traffic the flow extractor could not parse.")
            return

        st.markdown(html("<div style='height:0.6rem;'></div>"), unsafe_allow_html=True)
        cards.section("Schema validation")

        _, missing = align_to_schema(frame, engine.feature_columns)
        _validation_report(frame, missing)

        with st.expander("Preview the first rows"):
            st.dataframe(frame.head(12), width="stretch")

        if st.button("Run classification", type="primary"):
            progress = st.progress(0.0, text="Aligning columns to the model schema")
            started = time.time()

            labels, confidences, _ = engine.predict_frame(frame)
            progress.progress(0.7, text="Scoring flows")

            results = pd.DataFrame(
                {
                    "ts": frame["ts"] if "ts" in frame.columns else time.time(),
                    "src_ip": frame.get("src_ip", pd.Series(["-"] * len(frame))),
                    "src_port": frame.get("src_port", pd.Series([0] * len(frame))),
                    "dst_ip": frame.get("dst_ip", pd.Series(["-"] * len(frame))),
                    "dst_port": frame.get("dst_port", pd.Series([0] * len(frame))),
                    "protocol": frame.get("protocol", pd.Series(["-"] * len(frame))),
                    "prediction": labels,
                    "confidence": confidences,
                }
            )

            if "Label" in frame.columns:
                results["actual"] = frame["Label"].astype(str)

            written = db.write_detections(results.to_dict("records"), source="batch")
            progress.progress(1.0, text="Done")
            elapsed = time.time() - started

            st.session_state.batch_results = results
            st.session_state.batch_name = uploaded.name

            st.success(
                f"Classified {len(results):,} flows in {elapsed:.2f}s. "
                f"{written} malicious detections written to the log."
            )

    results = st.session_state.batch_results
    if results is None:
        return

    st.markdown(html("<div style='height:1rem;'></div>"), unsafe_allow_html=True)
    cards.section(f"Results \u00b7 {st.session_state.batch_name or 'batch'}")

    malicious = int((results["prediction"] != "BENIGN").sum())
    normal = len(results) - malicious
    mean_confidence = float(results["confidence"].mean())

    cards.kpi_grid(
        [
            {"label": "Rows scored", "value": f"{len(results):,}", "color": COLORS["accent"]},
            {
                "label": "Malicious",
                "value": f"{malicious:,}",
                "color": COLORS["attack"],
                "delta": f"{malicious / len(results) * 100:.1f}% of file",
            },
            {"label": "Normal", "value": f"{normal:,}", "color": COLORS["normal"]},
            {
                "label": "Mean confidence",
                "value": f"{mean_confidence:.3f}",
                "color": COLORS["probe"],
            },
        ]
    )

    left, right = st.columns([1.4, 1])

    with left:
        cards.section("Per-file summary")
        counts = results[results["prediction"] != "BENIGN"]["prediction"].value_counts().to_dict()
        if counts:
            st.plotly_chart(
                charts.donut(counts, height=250),
                width="stretch",
                config={"displayModeBar": False},
            )
        else:
            cards.empty_state("Every row in this file was classified as normal.")

    with right:
        cards.section("Confidence spread")
        st.plotly_chart(
            charts.confidence_histogram(results, height=250),
            width="stretch",
            config={"displayModeBar": False},
        )

    # Where the file carried a Label column, report accuracy. This is the only
    # honest way to judge a batch, and CICIDS exports usually include it.
    if "actual" in results.columns and engine.status.mode == "MODEL":
        correct = int((results["prediction"] == results["actual"]).sum())
        st.info(
            f"The file included a Label column. Accuracy on this file: "
            f"{correct / len(results) * 100:.2f}% ({correct:,}/{len(results):,} correct)."
        )

    cards.section("Detection rows")
    st.dataframe(results.head(500), width="stretch", height=340)

    export = results.to_csv(index=False)
    st.download_button(
        "Download results as CSV",
        export,
        file_name=f"nids_results_{int(time.time())}.csv",
        mime="text/csv",
    )
