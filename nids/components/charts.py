"""
Chart helpers.

Every chart shares one layout so the shell stays consistent, and every chart
takes its colours from the theme rather than the Plotly defaults, which are
tuned for white backgrounds and read as too saturated on this one.
"""

from typing import Dict, List

import pandas as pd
import plotly.graph_objects as go

from ..theme import COLORS, PLOTLY_LAYOUT, class_color


def donut(counts: Dict[str, int], height: int = 240) -> go.Figure:
    """Attack distribution as a donut."""
    labels = list(counts.keys())
    values = list(counts.values())
    colors = [class_color(label) for label in labels]

    figure = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker=dict(colors=colors, line=dict(color=COLORS["base"], width=2)),
            textinfo="none",
            hovertemplate="%{label}<br>%{value} flows (%{percent})<extra></extra>",
            sort=False,
        )
    )

    total = sum(values)

    # Copy the shared layout before overriding the legend, otherwise the key is
    # passed twice and Plotly rejects the call.
    layout = dict(PLOTLY_LAYOUT)
    layout["legend"] = dict(
        orientation="v",
        x=1.0,
        y=0.5,
        font=dict(size=10, color=COLORS["text_secondary"]),
    )

    figure.update_layout(
        **layout,
        height=height,
        showlegend=True,
        annotations=[
            dict(
                text=f"<b>{total}</b><br><span style='font-size:9px'>FLOWS</span>",
                x=0.5,
                y=0.5,
                font=dict(size=17, color=COLORS["text"], family="Orbitron"),
                showarrow=False,
            )
        ],
    )
    return figure


def threats_over_time(frame: pd.DataFrame, bucket: str = "30s", height: int = 240) -> go.Figure:
    """Malicious flow count per time bucket, drawn as a filled line."""
    figure = go.Figure()

    if frame.empty or "ts" not in frame.columns:
        figure.update_layout(**PLOTLY_LAYOUT, height=height)
        return figure

    work = frame.copy()
    work["time"] = pd.to_datetime(work["ts"], unit="s")
    work["is_threat"] = (work["prediction"] != "BENIGN").astype(int)

    series = work.set_index("time")["is_threat"].resample(bucket).sum()

    figure.add_trace(
        go.Scatter(
            x=series.index,
            y=series.values,
            mode="lines",
            line=dict(color=COLORS["attack"], width=2, shape="spline", smoothing=0.6),
            fill="tozeroy",
            fillcolor="rgba(255, 92, 108, 0.14)",
            hovertemplate="%{x|%H:%M:%S}<br>%{y} threats<extra></extra>",
            name="Threats",
        )
    )

    layout = dict(PLOTLY_LAYOUT)
    layout["yaxis"] = dict(layout["yaxis"], title=None, rangemode="tozero")
    layout["xaxis"] = dict(layout["xaxis"], title=None)
    figure.update_layout(**layout, height=height, showlegend=False)
    return figure


def traffic_volume(frame: pd.DataFrame, bucket: str = "30s", height: int = 240) -> go.Figure:
    """Stacked normal and malicious flow counts over time."""
    figure = go.Figure()

    if frame.empty or "ts" not in frame.columns:
        figure.update_layout(**PLOTLY_LAYOUT, height=height)
        return figure

    work = frame.copy()
    work["time"] = pd.to_datetime(work["ts"], unit="s")
    work["kind"] = work["prediction"].apply(lambda x: "Normal" if x == "BENIGN" else "Malicious")

    grouped = (
        work.set_index("time")
        .groupby("kind")["kind"]
        .resample(bucket)
        .count()
        .rename("count")
        .reset_index()
    )

    for kind, color in (("Normal", COLORS["normal"]), ("Malicious", COLORS["attack"])):
        subset = grouped[grouped["kind"] == kind]
        figure.add_trace(
            go.Bar(
                x=subset["time"],
                y=subset["count"],
                name=kind,
                marker=dict(color=color, line=dict(width=0)),
                opacity=0.85,
                hovertemplate="%{x|%H:%M:%S}<br>" + kind + ": %{y}<extra></extra>",
            )
        )

    figure.update_layout(**PLOTLY_LAYOUT, height=height, barmode="stack", bargap=0.15)
    return figure


def top_sources(frame: pd.DataFrame, limit: int = 8, height: int = 260) -> go.Figure:
    """Horizontal bar chart of the noisiest malicious sources."""
    figure = go.Figure()

    if frame.empty:
        figure.update_layout(**PLOTLY_LAYOUT, height=height)
        return figure

    threats = frame[frame["prediction"] != "BENIGN"]
    if threats.empty:
        figure.update_layout(**PLOTLY_LAYOUT, height=height)
        return figure

    counts = threats["src_ip"].value_counts().head(limit).sort_values()

    figure.add_trace(
        go.Bar(
            x=counts.values,
            y=counts.index,
            orientation="h",
            marker=dict(
                color=counts.values,
                colorscale=[[0, COLORS["probe"]], [1, COLORS["critical"]]],
                line=dict(width=0),
            ),
            hovertemplate="%{y}<br>%{x} malicious flows<extra></extra>",
        )
    )

    layout = dict(PLOTLY_LAYOUT)
    layout["yaxis"] = dict(layout["yaxis"], gridcolor="rgba(0,0,0,0)")
    figure.update_layout(**layout, height=height, showlegend=False)
    return figure


def confidence_histogram(frame: pd.DataFrame, height: int = 240) -> go.Figure:
    """Distribution of model confidence, split by normal and malicious."""
    figure = go.Figure()

    if frame.empty or "confidence" not in frame.columns:
        figure.update_layout(**PLOTLY_LAYOUT, height=height)
        return figure

    normal = frame[frame["prediction"] == "BENIGN"]["confidence"]
    malicious = frame[frame["prediction"] != "BENIGN"]["confidence"]

    figure.add_trace(
        go.Histogram(
            x=normal, name="Normal", marker=dict(color=COLORS["normal"]),
            opacity=0.7, nbinsx=24,
        )
    )
    figure.add_trace(
        go.Histogram(
            x=malicious, name="Malicious", marker=dict(color=COLORS["attack"]),
            opacity=0.75, nbinsx=24,
        )
    )

    figure.update_layout(**PLOTLY_LAYOUT, height=height, barmode="overlay")
    return figure


def confusion_matrix(matrix: List[List[int]], labels: List[str], height: int = 420) -> go.Figure:
    """Confusion matrix heatmap."""
    figure = go.Figure(
        go.Heatmap(
            z=matrix,
            x=labels,
            y=labels,
            colorscale=[
                [0.0, COLORS["base"]],
                [0.25, "#0E3B38"],
                [0.6, COLORS["accent_dim"]],
                [1.0, COLORS["accent"]],
            ],
            showscale=True,
            hovertemplate="Actual %{y}<br>Predicted %{x}<br>%{z} flows<extra></extra>",
            colorbar=dict(
                outlinewidth=0,
                tickfont=dict(color=COLORS["text_muted"], size=9),
            ),
        )
    )

    layout = dict(PLOTLY_LAYOUT)
    layout["xaxis"] = dict(layout["xaxis"], title="Predicted", side="bottom")
    layout["yaxis"] = dict(layout["yaxis"], title="Actual", autorange="reversed")
    figure.update_layout(**layout, height=height)
    return figure


def roc_curve(curves: Dict[str, Dict], height: int = 340) -> go.Figure:
    """
    One-vs-rest ROC curves.

    curves maps a class name to {"fpr": [...], "tpr": [...], "auc": float}.
    """
    figure = go.Figure()

    figure.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(color=COLORS["text_muted"], width=1, dash="dash"),
            name="Chance",
            hoverinfo="skip",
        )
    )

    for name, data in curves.items():
        figure.add_trace(
            go.Scatter(
                x=data["fpr"],
                y=data["tpr"],
                mode="lines",
                line=dict(color=class_color(name), width=2),
                name=f"{name} (AUC {data['auc']:.3f})",
                hovertemplate="FPR %{x:.3f}<br>TPR %{y:.3f}<extra></extra>",
            )
        )

    layout = dict(PLOTLY_LAYOUT)
    layout["xaxis"] = dict(layout["xaxis"], title="False positive rate", range=[0, 1])
    layout["yaxis"] = dict(layout["yaxis"], title="True positive rate", range=[0, 1.02])
    figure.update_layout(**layout, height=height)
    return figure


def feature_importance(frame: pd.DataFrame, limit: int = 15, height: int = 420) -> go.Figure:
    """Top model features by importance."""
    figure = go.Figure()

    if frame is None or frame.empty:
        figure.update_layout(**PLOTLY_LAYOUT, height=height)
        return figure

    top = frame.head(limit).sort_values("importance")

    figure.add_trace(
        go.Bar(
            x=top["importance"],
            y=top["feature"],
            orientation="h",
            marker=dict(
                color=top["importance"],
                colorscale=[[0, COLORS["accent_dim"]], [1, COLORS["accent"]]],
                line=dict(width=0),
            ),
            hovertemplate="%{y}<br>importance %{x:.4f}<extra></extra>",
        )
    )

    layout = dict(PLOTLY_LAYOUT)
    layout["yaxis"] = dict(layout["yaxis"], gridcolor="rgba(0,0,0,0)")
    figure.update_layout(**layout, height=height, showlegend=False)
    return figure


# --------------------------------------------------------------------------
# Inline SVG charts
# --------------------------------------------------------------------------
#
# The live page draws its charts as SVG rather than with Plotly.
#
# Plotly mounts a JavaScript chart per figure and re-initialises it whenever
# Streamlit re-renders the element. On a page that refreshes on a timer that
# rebuild is the single heaviest thing on screen, and it reads as a flash. An
# SVG is just markup: it is replaced in place, costs nothing to paint, and
# matches how the radar on the same page is drawn.
#
# The trade is interactivity. These have no hover tooltips and no zoom. The
# Detection Results and Overview pages keep the Plotly versions, which is where
# someone would actually go to interrogate the numbers.


def svg_sparkline(frame, height: int = 130, buckets: int = 30, seconds: int = 300) -> str:
    """Threat count over the recent past, as a filled line."""
    import time as _time

    now = _time.time()
    width = 100.0  # viewBox units; the SVG scales to its container
    step = seconds / buckets

    counts = [0] * buckets
    if frame is not None and not frame.empty and "ts" in frame.columns:
        threats = frame[frame["prediction"] != "BENIGN"]
        for ts in threats["ts"]:
            age = now - float(ts)
            if 0 <= age < seconds:
                index = buckets - 1 - int(age / step)
                if 0 <= index < buckets:
                    counts[index] += 1

    peak = max(1, max(counts))

    points = []
    for i, value in enumerate(counts):
        x = (i / (buckets - 1)) * width
        y = height - 6 - (value / peak) * (height - 24)
        points.append(f"{x:.2f},{y:.2f}")

    line = " ".join(points)
    area = f"0,{height} {line} {width},{height}"

    return f"""
<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none"
     style="width:100%;height:{height}px;display:block;">
  <polygon points="{area}" fill="rgba(255,92,108,0.14)" />
  <polyline points="{line}" fill="none" stroke="{COLORS['attack']}"
            stroke-width="1.5" vector-effect="non-scaling-stroke"
            stroke-linejoin="round" />
  <line x1="0" y1="{height - 1}" x2="{width}" y2="{height - 1}"
        stroke="{COLORS['border']}" stroke-width="1" vector-effect="non-scaling-stroke" />
</svg>
<div style="display:flex;justify-content:space-between;
            font-family:var(--font-mono);font-size:0.62rem;
            color:{COLORS['text_muted']};margin-top:0.2rem;">
  <span>peak {peak}</span><span>last {seconds // 60} min</span>
</div>
"""


def svg_donut(counts: dict, size: int = 130) -> str:
    """Attack distribution as a donut, with a legend beside it."""
    import math

    total = sum(counts.values())
    if not total:
        return (
            f'<div style="height:{size}px;display:flex;align-items:center;'
            f'justify-content:center;color:{COLORS["text_muted"]};'
            f'font-family:var(--font-mono);font-size:0.76rem;">'
            f"No attacks detected yet.</div>"
        )

    cx = cy = size / 2
    outer = size / 2 - 6
    inner = outer * 0.62

    segments = []
    angle = -math.pi / 2

    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        sweep = (count / total) * math.pi * 2
        end = angle + sweep
        large = 1 if sweep > math.pi else 0

        # A full circle cannot be drawn with one arc, so a single-class donut
        # is drawn as two half circles instead.
        if abs(sweep - math.pi * 2) < 1e-6:
            segments.append(
                f'<circle cx="{cx}" cy="{cy}" r="{(outer + inner) / 2:.2f}" '
                f'fill="none" stroke="{class_color(label)}" '
                f'stroke-width="{outer - inner:.2f}" />'
            )
            angle = end
            continue

        x0, y0 = cx + math.cos(angle) * outer, cy + math.sin(angle) * outer
        x1, y1 = cx + math.cos(end) * outer, cy + math.sin(end) * outer
        x2, y2 = cx + math.cos(end) * inner, cy + math.sin(end) * inner
        x3, y3 = cx + math.cos(angle) * inner, cy + math.sin(angle) * inner

        segments.append(
            f'<path d="M {x0:.2f} {y0:.2f} '
            f'A {outer:.2f} {outer:.2f} 0 {large} 1 {x1:.2f} {y1:.2f} '
            f'L {x2:.2f} {y2:.2f} '
            f'A {inner:.2f} {inner:.2f} 0 {large} 0 {x3:.2f} {y3:.2f} Z" '
            f'fill="{class_color(label)}" stroke="{COLORS["base"]}" stroke-width="1.5" />'
        )
        angle = end

    legend = []
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1])[:7]:
        legend.append(
            f'<div style="display:flex;align-items:center;gap:6px;'
            f'font-family:var(--font-mono);font-size:0.66rem;'
            f'color:{COLORS["text"]};line-height:1.7;">'
            f'<i style="width:7px;height:7px;border-radius:50%;'
            f'background:{class_color(label)};box-shadow:0 0 6px {class_color(label)};'
            f'flex-shrink:0;"></i>{label} <span style="color:{COLORS["text_muted"]};">'
            f"{count}</span></div>"
        )

    return f"""
<div style="display:flex;align-items:center;gap:1rem;">
  <svg viewBox="0 0 {size} {size}" style="width:{size}px;height:{size}px;flex-shrink:0;">
    {''.join(segments)}
    <text x="{cx}" y="{cy - 3}" text-anchor="middle" dominant-baseline="middle"
          fill="{COLORS['text']}" font-family="Orbitron, sans-serif"
          font-size="15" font-weight="900">{total}</text>
    <text x="{cx}" y="{cy + 11}" text-anchor="middle" dominant-baseline="middle"
          fill="{COLORS['text_muted']}" font-family="JetBrains Mono, monospace"
          font-size="7">THREATS</text>
  </svg>
  <div>{''.join(legend)}</div>
</div>
"""
