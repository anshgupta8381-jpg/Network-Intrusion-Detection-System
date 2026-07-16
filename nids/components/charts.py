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
