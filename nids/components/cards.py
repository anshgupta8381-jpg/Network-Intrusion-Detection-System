"""
Shared interface building blocks.

Everything here returns markup rather than writing to the page where possible,
so callers can compose panels without fighting Streamlit's column layout.
"""

import time
from datetime import datetime
from typing import Dict, List

import streamlit as st

from ..theme import html, COLORS, SEVERITY_GLYPH, class_color, class_severity


def page_header(title: str, subtitle: str, right: str = "") -> None:
    """Title block at the top of every page."""
    right_html = (
        f'<div class="status-chip" style="margin:0;">{right}</div>' if right else ""
    )
    st.markdown(html(f"""
        <div style="display:flex;align-items:flex-end;justify-content:space-between;
                    gap:1rem;margin-bottom:1.4rem;">
            <div>
                <div class="page-title">{title}</div>
                <div class="page-subtitle">{subtitle}</div>
            </div>
            {right_html}
        </div>
        """), unsafe_allow_html=True)


def kpi_grid(items: List[Dict]) -> None:
    """
    Render a row of KPI cards.

    Each item: {"label": str, "value": str, "color": hex, "delta": str}
    """
    cards = []
    for item in items:
        color = item.get("color", COLORS["accent"])
        delta = item.get("delta", "")
        delta_html = f'<div class="kpi-delta">{delta}</div>' if delta else ""
        cards.append(
            f"""
            <div class="kpi" style="--kpi-accent:{color};">
                <div class="kpi-label">{item['label']}</div>
                <div class="kpi-value">{item['value']}</div>
                {delta_html}
            </div>
            """
        )

    st.markdown(html(f'<div class="kpi-grid">{"".join(cards)}</div>'), unsafe_allow_html=True)


def section(title: str) -> None:
    """Small uppercase heading with an accent bar."""
    st.markdown(html(f'<div class="section-title">{title}</div>'), unsafe_allow_html=True)


def pill(label: str) -> str:
    """Status pill markup for a prediction label."""
    color = class_color(label)
    glyph = SEVERITY_GLYPH[class_severity(label)]
    return (
        f'<span class="pill" style="color:{color};">{glyph} {label}</span>'
    )


def alert_bar(row: Dict) -> None:
    """Banner for the most recent high-confidence detection."""
    when = datetime.fromtimestamp(row["ts"]).strftime("%H:%M:%S")
    severity = class_severity(row["prediction"])
    glyph = SEVERITY_GLYPH[severity]

    st.markdown(html(f"""
        <div class="alert-bar">
            <div class="alert-text">
                {glyph} ALERT &nbsp; {row['prediction']} from {row['src_ip']}
                &rarr; {row['dst_ip']}:{row['dst_port']}
                &nbsp;|&nbsp; confidence {row['confidence']:.2f}
                &nbsp;|&nbsp; {when}
            </div>
            <div style="color:{COLORS['text_secondary']};font-size:0.75rem;
                        font-family:var(--font-mono);white-space:nowrap;">
                {severity.upper()}
            </div>
        </div>
        """), unsafe_allow_html=True)


def flow_table(rows: List[Dict], height: int = 420, show_index: bool = False) -> None:
    """
    Custom HTML flow table.

    st.dataframe cannot colour a whole row by value, and colouring the prediction
    alone loses the scannability that makes a live feed usable, so the table is
    rendered directly.
    """
    if not rows:
        st.markdown(html(f"""
            <div style="height:{height}px;display:flex;align-items:center;
                        justify-content:center;color:{COLORS['text_muted']};
                        font-family:var(--font-mono);font-size:0.85rem;
                        border:1px dashed {COLORS['border']};border-radius:10px;">
                No flows captured yet. Start capture on the Live Monitoring page.
            </div>
            """), unsafe_allow_html=True)
        return

    body = []
    for row in rows:
        label = row.get("prediction", "BENIGN")
        severity = class_severity(label)
        color = class_color(label)
        glyph = SEVERITY_GLYPH[severity]
        when = datetime.fromtimestamp(row["ts"]).strftime("%H:%M:%S")
        duration = row.get("Flow Duration", 0) / 1_000_000

        row_bg = "transparent"
        if severity == "critical":
            row_bg = "rgba(255, 51, 85, 0.12)"
        elif severity == "attack":
            row_bg = "rgba(255, 92, 108, 0.09)"
        elif severity == "probe":
            row_bg = "rgba(255, 180, 84, 0.07)"

        body.append(
            f"""
            <tr style="background:{row_bg};">
                <td class="c-mut">{when}</td>
                <td>{row.get('src_ip', '')}<span class="c-mut">:{row.get('src_port', '')}</span></td>
                <td>{row.get('dst_ip', '')}<span class="c-mut">:{row.get('dst_port', '')}</span></td>
                <td class="c-mut">{row.get('protocol', '')}</td>
                <td class="c-mut">{duration:.2f}s</td>
                <td style="color:{color};font-weight:700;">{glyph} {label}</td>
                <td style="text-align:right;">{row.get('confidence', 0):.2f}</td>
            </tr>
            """
        )

    st.markdown(html(f"""
        <div style="max-height:{height}px;overflow-y:auto;border:1px solid {COLORS['border']};
                    border-radius:10px;background:{COLORS['base']};">
        <style>
            table.flows {{
                width:100%; border-collapse:collapse;
                font-family:'JetBrains Mono', monospace; font-size:0.76rem;
            }}
            table.flows thead th {{
                position:sticky; top:0; z-index:2;
                background:{COLORS['surface_2']};
                color:{COLORS['text_muted']};
                text-align:left; font-weight:600; letter-spacing:0.1em;
                text-transform:uppercase; font-size:0.64rem;
                padding:0.6rem 0.7rem;
                border-bottom:1px solid {COLORS['border']};
            }}
            table.flows tbody td {{
                padding:0.5rem 0.7rem;
                border-bottom:1px solid rgba(35, 40, 56, 0.6);
                color:{COLORS['text']};
                white-space:nowrap;
            }}
            table.flows tbody tr:hover {{ background:rgba(59, 232, 220, 0.06) !important; }}
            table.flows .c-mut {{ color:{COLORS['text_muted']}; }}
        </style>
        <table class="flows">
            <thead>
                <tr>
                    <th>Time</th><th>Source</th><th>Destination</th>
                    <th>Proto</th><th>Duration</th><th>Prediction</th>
                    <th style="text-align:right;">Conf</th>
                </tr>
            </thead>
            <tbody>{''.join(body)}</tbody>
        </table>
        </div>
        """), unsafe_allow_html=True)


def alert_feed(rows: List[Dict], limit: int = 8) -> None:
    """Compact chronological list of recent alerts."""
    if not rows:
        st.markdown(html(f"""
            <div style="color:{COLORS['text_muted']};font-family:var(--font-mono);
                        font-size:0.78rem;padding:1.2rem 0;text-align:center;">
                No alerts raised in this session.
            </div>
            """), unsafe_allow_html=True)
        return

    items = []
    for row in rows[:limit]:
        label = row.get("prediction", "")
        color = class_color(label)
        glyph = SEVERITY_GLYPH[class_severity(label)]
        when = datetime.fromtimestamp(row["ts"]).strftime("%H:%M:%S")
        ago = max(0, int(time.time() - row["ts"]))
        ago_text = f"{ago}s ago" if ago < 60 else f"{ago // 60}m ago"

        items.append(
            f"""
            <div style="display:flex;align-items:center;gap:0.7rem;
                        padding:0.55rem 0.6rem;border-radius:8px;
                        border-left:2px solid {color};
                        background:linear-gradient(90deg,
                            color-mix(in srgb, {color} 10%, transparent), transparent);
                        margin-bottom:0.4rem;">
                <div style="color:{color};font-size:0.8rem;">{glyph}</div>
                <div style="flex:1;min-width:0;">
                    <div style="font-family:var(--font-mono);font-size:0.76rem;
                                font-weight:700;color:{color};">{label}</div>
                    <div style="font-family:var(--font-mono);font-size:0.68rem;
                                color:{COLORS['text_muted']};overflow:hidden;
                                text-overflow:ellipsis;white-space:nowrap;">
                        {row.get('src_ip', '')} &rarr; {row.get('dst_ip', '')}
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-family:var(--font-mono);font-size:0.7rem;
                                color:{COLORS['text_secondary']};">{row.get('confidence', 0):.2f}</div>
                    <div style="font-family:var(--font-mono);font-size:0.62rem;
                                color:{COLORS['text_muted']};">{ago_text}</div>
                </div>
            </div>
            """
        )

    st.markdown(html("".join(items)), unsafe_allow_html=True)


def empty_state(message: str, hint: str = "") -> None:
    """Placeholder for pages with nothing to show yet."""
    hint_html = (
        f'<div style="color:{COLORS["text_muted"]};font-size:0.76rem;'
        f'margin-top:0.5rem;">{hint}</div>'
        if hint
        else ""
    )
    st.markdown(html(f"""
        <div style="border:1px dashed {COLORS['border']};border-radius:12px;
                    padding:3rem 1rem;text-align:center;">
            <div style="color:{COLORS['text_secondary']};font-family:var(--font-mono);
                        font-size:0.9rem;">{message}</div>
            {hint_html}
        </div>
        """), unsafe_allow_html=True)
