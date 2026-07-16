"""
Settings and About page.

Capture configuration, alerting thresholds, model management, and a diagnostics
panel that reports what is actually installed on this machine. The diagnostics
matter more than they look: most live-capture failures on Windows come down to
Npcap or privileges, and guessing at that from an error traceback is painful.
"""

import os
import platform
import sys

import streamlit as st

from ..components import cards
from ..core import db, state
from ..core.capture import NfstreamSource
from ..core.engine import MODELS_DIR
from ..core.schema import CLASS_DESCRIPTIONS, FEATURE_COLUMNS
from ..theme import html, COLORS


def _dependency_row(name: str, ok: bool, detail: str) -> str:
    color = COLORS["normal"] if ok else COLORS["probe"]
    glyph = "\u25CF OK" if ok else "\u25B2 MISSING"
    return f"""
    <div style="display:flex;align-items:center;gap:0.8rem;padding:0.5rem 0;
                border-bottom:1px solid {COLORS['border']};">
        <div style="min-width:120px;font-family:var(--font-mono);font-size:0.78rem;
                    color:{COLORS['text']};">{name}</div>
        <div style="min-width:90px;font-family:var(--font-mono);font-size:0.72rem;
                    font-weight:700;color:{color};">{glyph}</div>
        <div style="font-size:0.75rem;color:{COLORS['text_muted']};">{detail}</div>
    </div>
    """


def _check(module: str):
    """Return (installed, version string)."""
    try:
        imported = __import__(module)
        return True, getattr(imported, "__version__", "installed")
    except Exception:  # noqa: BLE001
        return False, "not installed"


def render() -> None:
    engine = state.get_engine()
    capture = state.get_capture()
    settings = state.settings()

    cards.page_header(
        "SETTINGS & ABOUT",
        "Capture configuration, model management and environment diagnostics",
    )

    tabs = st.tabs(["Capture", "Alerts & radar", "Model", "Diagnostics", "About"])

    # -- Capture ---------------------------------------------------------

    with tabs[0]:
        cards.section("Capture configuration")
        columns = st.columns(2)

        with columns[0]:
            st.markdown(
                html(
                    f"""
                    <div style="font-size:0.8rem;color:{COLORS['text_secondary']};
                                line-height:1.6;padding-bottom:0.8rem;">
                        There is no refresh interval. The live panel holds an open
                        stream and draws each flow as it is scored, so there is
                        nothing to poll and nothing to re-render.
                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )
            settings["flows_per_second"] = st.number_input(
                "Simulated flows per second",
                0.5, 60.0, float(settings["flows_per_second"]), 0.5,
                help="Only applies to the simulated capture source.",
            )

        with columns[1]:
            settings["attack_bias"] = st.slider(
                "Simulated attack bias", 0.2, 6.0, float(settings["attack_bias"]), 0.2,
                help=(
                    "Scales attack frequency in simulated traffic. Leave at 1.0 for "
                    "a realistic class imbalance; raise it for a busier demo."
                ),
            )
            interfaces = NfstreamSource.list_interfaces()
            st.text_area(
                "Interfaces visible to this machine",
                "\n".join(interfaces) if interfaces else "None detected.",
                height=100,
                disabled=True,
            )

        st.markdown(html("<div style='height:0.6rem;'></div>"), unsafe_allow_html=True)
        cards.section("Session")

        buttons = st.columns(3)

        with buttons[0]:
            if st.button("Clear live buffer", width="stretch"):
                state.reset_session()
                st.success("Live buffer and alert feed cleared.")

        with buttons[1]:
            if st.button("Stop capture", width="stretch"):
                capture.stop()
                st.success("Capture stopped.")

        with buttons[2]:
            confirm = st.checkbox("Confirm log wipe")
            if st.button("Clear detection log", width="stretch", disabled=not confirm):
                db.clear()
                st.success("Detection log cleared.")

    # -- Alerts and radar ------------------------------------------------

    with tabs[1]:
        cards.section("Alerting")
        columns = st.columns(2)

        with columns[0]:
            settings["alert_threshold"] = st.slider(
                "Alert confidence threshold", 0.0, 1.0,
                float(settings["alert_threshold"]), 0.05,
                help=(
                    "A malicious prediction below this confidence still appears in "
                    "the results table but does not raise an alert."
                ),
            )

        with columns[1]:
            st.markdown(html(f"""
                <div style="font-size:0.8rem;color:{COLORS['text_secondary']};
                            line-height:1.6;padding-top:0.5rem;">
                    Lowering the threshold catches more attacks and produces more
                    false positives. Raising it does the opposite. There is no
                    correct value; it depends on how much noise an analyst will
                    tolerate before they stop reading the feed.
                </div>
                """), unsafe_allow_html=True)

        st.markdown(html("<div style='height:0.8rem;'></div>"), unsafe_allow_html=True)
        cards.section("Radar")

        radar_columns = st.columns(3)

        with radar_columns[0]:
            settings["radar_retention"] = st.slider(
                "Blip retention (seconds)", 10, 180, int(settings["radar_retention"]),
                help="How long a contact stays on the scope before it fades out.",
            )

        with radar_columns[1]:
            settings["sweep_period"] = st.slider(
                "Sweep period (seconds)", 1.0, 10.0, float(settings["sweep_period"]), 0.5,
                help="Time for one full rotation.",
            )

        with radar_columns[2]:
            settings["show_benign_on_radar"] = st.checkbox(
                "Show normal traffic on radar",
                value=settings["show_benign_on_radar"],
                help=(
                    "Off by default. Benign flows outnumber attacks by roughly "
                    "forty to one, and drawing them buries the threats."
                ),
            )

    # -- Model -----------------------------------------------------------

    with tabs[2]:
        cards.section("Deployed model")

        status_color = COLORS["accent"] if engine.status.mode == "MODEL" else COLORS["probe"]
        st.markdown(html(f"""
            <div class="panel" style="margin-bottom:1rem;">
                <div style="display:flex;gap:2.5rem;flex-wrap:wrap;">
                    <div>
                        <div class="kpi-label">Mode</div>
                        <div style="font-family:var(--font-display);font-size:1.2rem;
                                    color:{status_color};font-weight:700;">
                            {engine.status.mode}</div>
                    </div>
                    <div>
                        <div class="kpi-label">Classifier</div>
                        <div style="font-family:var(--font-mono);font-size:1rem;
                                    color:{COLORS['text']};padding-top:0.35rem;">
                            {engine.status.model_name}</div>
                    </div>
                    <div>
                        <div class="kpi-label">Features</div>
                        <div style="font-family:var(--font-mono);font-size:1rem;
                                    color:{COLORS['text']};padding-top:0.35rem;">
                            {engine.status.feature_count}</div>
                    </div>
                    <div>
                        <div class="kpi-label">Scaler</div>
                        <div style="font-family:var(--font-mono);font-size:1rem;
                                    color:{COLORS['text']};padding-top:0.35rem;">
                            {"loaded" if engine.status.has_scaler else "none"}</div>
                    </div>
                </div>
                <div style="margin-top:0.9rem;font-size:0.78rem;
                            color:{COLORS['text_secondary']};">
                    {engine.status.message}</div>
            </div>
            """), unsafe_allow_html=True)

        model_columns = st.columns([2, 1])

        with model_columns[0]:
            available = engine.available_models()
            if available:
                st.selectbox("Available model files", available)
            else:
                st.info(
                    f"No .joblib files in {MODELS_DIR}. "
                    "Export the trained model there and press Reload."
                )

        with model_columns[1]:
            st.markdown(html("<div style='height:1.75rem;'></div>"), unsafe_allow_html=True)
            if st.button("Reload model", type="primary", width="stretch"):
                engine.reload()
                st.rerun()

        cards.section("Expected feature order")
        st.caption(
            "The model is served on these columns in this order. Override the list "
            "by placing feature_columns.json in the models folder."
        )
        st.code("\n".join(f"{i + 1:>2}. {name}" for i, name in enumerate(engine.feature_columns)))

    # -- Diagnostics -----------------------------------------------------

    with tabs[3]:
        cards.section("Environment")

        rows = [
            _dependency_row("Python", True, sys.version.split()[0]),
            _dependency_row("Platform", True, f"{platform.system()} {platform.release()}"),
            _dependency_row("Models folder", os.path.isdir(MODELS_DIR), MODELS_DIR),
        ]

        for module, note in (
            ("streamlit", "dashboard framework"),
            ("pandas", "data handling"),
            ("numpy", "numerics"),
            ("plotly", "charts"),
            ("sklearn", "model runtime and scaler"),
            ("joblib", "model loading"),
            ("xgboost", "needed only if the exported model is XGBoost"),
            ("nfstream", "live capture and flow extraction"),
        ):
            ok, version = _check(module)
            rows.append(_dependency_row(module, ok, f"{version} \u00b7 {note}"))

        st.markdown(html("".join(rows)), unsafe_allow_html=True)

        st.markdown(html("<div style='height:1rem;'></div>"), unsafe_allow_html=True)
        cards.section("Live capture readiness")

        nfstream_ok = NfstreamSource.available()
        interfaces = NfstreamSource.list_interfaces()

        if not nfstream_ok:
            st.warning(
                "nfstream is not installed, so only simulated capture and CSV "
                "upload are available. Install it with: pip install nfstream"
            )
        elif not interfaces:
            st.warning(
                "nfstream is installed but no interfaces were found. On Windows "
                "this almost always means Npcap is not installed. Install Npcap "
                "with WinPcap API compatibility enabled, then restart this app."
            )
        else:
            st.success(
                f"nfstream is installed and {len(interfaces)} interfaces are visible. "
                "Live capture also needs this app to be started from an "
                "Administrator terminal."
            )

    # -- About -----------------------------------------------------------

    with tabs[4]:
        cards.section("About this system")

        st.markdown(html(f"""
            <div style="font-size:0.86rem;color:{COLORS['text_secondary']};
                        line-height:1.75;max-width:70ch;">
            This dashboard is the application layer described in the design
            document. It sits on top of a classifier trained offline on the
            CICIDS2017 benchmark and does not train anything itself. It loads the
            exported model and serves it.
            <br><br>
            Traffic reaches the model through two paths. Live capture reads an
            interface with nfstream, groups packets into bidirectional flows, and
            extracts the same flow features used during training. Batch upload
            takes a CSV of pre-computed flow records. Both paths align to the same
            feature order, run through the same scaler, and produce the same
            output structure, which is why the results, alerts and reports do not
            need to know where a row came from.
            <br><br>
            Two limits are worth stating plainly. Live capture only sees what the
            interface sees, so it works properly on a mirror or SPAN port and
            shows very little on an ordinary switched port. And detection is only
            as good as the training data: traffic that was rare in CICIDS2017 gets
            classified with low confidence, which is exactly why the confidence
            score sits next to every prediction rather than being hidden.
            </div>
            """), unsafe_allow_html=True)

        st.markdown(html("<div style='height:1rem;'></div>"), unsafe_allow_html=True)
        cards.section("Detection classes")

        rows = []
        for label, description in CLASS_DESCRIPTIONS.items():
            from ..theme import class_color

            rows.append(
                f"""
                <div style="display:flex;gap:0.9rem;padding:0.45rem 0;
                            border-bottom:1px solid {COLORS['border']};">
                    <div style="min-width:110px;font-family:var(--font-mono);
                                font-size:0.76rem;font-weight:700;
                                color:{class_color(label)};">{label}</div>
                    <div style="font-size:0.78rem;color:{COLORS['text_secondary']};">
                        {description}</div>
                </div>
                """
            )
        st.markdown(html("".join(rows)), unsafe_allow_html=True)

        st.markdown(html("<div style='height:1rem;'></div>"), unsafe_allow_html=True)
        cards.section("Accessibility notes")
        st.markdown(html(f"""
            <div style="font-size:0.82rem;color:{COLORS['text_secondary']};
                        line-height:1.7;max-width:70ch;">
            Body text is off-white (#E6EAF2) on a near-black surface rather than
            pure white on pure black. Pure white on pure black measures 21:1 and
            causes halation for readers with astigmatism, so the palette trades a
            little contrast for comfort while staying far above the WCAG AA
            minimum of 4.5:1.
            <br><br>
            Status colours are desaturated for the same reason: fully saturated
            red and green are hard to read on dark surfaces even when the measured
            ratio passes. Every status also carries a text label and a shape, so
            meaning never depends on colour alone. Animation respects the
            operating system reduced-motion setting.
            </div>
            """), unsafe_allow_html=True)
