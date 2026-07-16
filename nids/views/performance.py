"""
Model Performance page.

Reads models/metrics.json, which the offline training pipeline is expected to
write. Nothing here is computed live: the application does not have the test set
and inventing numbers on the dashboard would defeat the point of the page.

Expected metrics.json shape:

{
  "model_name": "RandomForest",
  "trained_at": "2026-02-14",
  "dataset": "CICIDS2017",
  "test_size": 565575,
  "overall": {"accuracy": 0.997, "precision": 0.994, "recall": 0.991, "f1": 0.992},
  "per_class": [
      {"class": "BENIGN", "precision": 0.999, "recall": 0.999, "f1": 0.999, "support": 454621}
  ],
  "confusion_matrix": {"labels": ["BENIGN", "DoS"], "matrix": [[1, 2], [3, 4]]},
  "roc": {"BENIGN": {"fpr": [0, 1], "tpr": [0, 1], "auc": 0.99}},
  "comparison": [{"model": "RandomForest", "accuracy": 0.997, "f1": 0.992, "train_seconds": 412}]
}
"""

import pandas as pd
import streamlit as st

from ..components import cards, charts
from ..core import state
from ..theme import html, COLORS, PLOTLY_LAYOUT


def _no_metrics_guidance() -> None:
    """Explain exactly what to export, since this page cannot fabricate it."""
    cards.empty_state(
        "No evaluation metrics found.",
        "The training pipeline has not exported models/metrics.json yet.",
    )

    st.markdown(html("<div style='height:1rem;'></div>"), unsafe_allow_html=True)

    with st.expander("What the training notebook needs to export", expanded=True):
        st.markdown(
            "Add this to the end of the training notebook, after the best model "
            "has been selected. It writes everything this page renders."
        )
        st.code(
            '''import json, joblib
from sklearn.metrics import (accuracy_score, precision_recall_fscore_support,
                             confusion_matrix, roc_curve, auc,
                             classification_report)
from sklearn.preprocessing import label_binarize

y_pred  = best_model.predict(X_test)
y_proba = best_model.predict_proba(X_test)
labels  = list(best_model.classes_)

precision, recall, f1, _ = precision_recall_fscore_support(
    y_test, y_pred, average="weighted", zero_division=0)

report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
per_class = [
    {"class": name,
     "precision": round(vals["precision"], 4),
     "recall":    round(vals["recall"], 4),
     "f1":        round(vals["f1-score"], 4),
     "support":   int(vals["support"])}
    for name, vals in report.items()
    if name in labels
]

# One-vs-rest ROC. Downsample the curve so the JSON stays small.
y_bin = label_binarize(y_test, classes=labels)
roc = {}
for i, name in enumerate(labels):
    fpr, tpr, _ = roc_curve(y_bin[:, i], y_proba[:, i])
    step = max(1, len(fpr) // 200)
    roc[name] = {"fpr": fpr[::step].tolist(),
                 "tpr": tpr[::step].tolist(),
                 "auc": float(auc(fpr, tpr))}

metrics = {
    "model_name": type(best_model).__name__,
    "trained_at": "2026-07-15",
    "dataset": "CICIDS2017",
    "test_size": int(len(y_test)),
    "overall": {"accuracy":  float(accuracy_score(y_test, y_pred)),
                "precision": float(precision),
                "recall":    float(recall),
                "f1":        float(f1)},
    "per_class": per_class,
    "confusion_matrix": {"labels": labels,
                         "matrix": confusion_matrix(y_test, y_pred, labels=labels).tolist()},
    "roc": roc,
    "comparison": comparison_rows,   # one dict per model you trained
}

with open("metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

joblib.dump(best_model, "model.joblib")
joblib.dump(scaler,     "scaler.joblib")
with open("feature_columns.json", "w") as f:
    json.dump(list(X_train.columns), f, indent=2)''',
            language="python",
        )
        st.markdown(
            "Copy `model.joblib`, `scaler.joblib`, `feature_columns.json` and "
            "`metrics.json` into the `models/` folder, then press Reload model "
            "on the Settings page."
        )


def render() -> None:
    engine = state.get_engine()

    cards.page_header(
        "MODEL PERFORMANCE",
        "Evaluation of the deployed classifier on the held-out test set",
        f'<span class="dot" style="--chip-color:'
        f'{COLORS["accent"] if engine.metrics else COLORS["text_muted"]};"></span>'
        f"{engine.status.model_name}",
    )

    metrics = engine.metrics
    if not metrics:
        _no_metrics_guidance()
        return

    overall = metrics.get("overall", {})

    cards.kpi_grid(
        [
            {
                "label": "Accuracy",
                "value": f"{overall.get('accuracy', 0) * 100:.2f}%",
                "color": COLORS["accent"],
                "delta": f"{metrics.get('test_size', 0):,} test flows",
            },
            {
                "label": "Precision",
                "value": f"{overall.get('precision', 0) * 100:.2f}%",
                "color": COLORS["normal"],
                "delta": "weighted average",
            },
            {
                "label": "Recall",
                "value": f"{overall.get('recall', 0) * 100:.2f}%",
                "color": COLORS["probe"],
                "delta": "weighted average",
            },
            {
                "label": "F1 score",
                "value": f"{overall.get('f1', 0) * 100:.2f}%",
                "color": COLORS["violet"],
                "delta": metrics.get("dataset", "CICIDS2017"),
            },
        ]
    )

    tabs = st.tabs(
        ["Confusion matrix", "ROC curves", "Per class", "Feature importance", "Model comparison"]
    )

    with tabs[0]:
        confusion = metrics.get("confusion_matrix")
        if confusion:
            st.plotly_chart(
                charts.confusion_matrix(confusion["matrix"], confusion["labels"]),
                width="stretch",
                config={"displayModeBar": False},
            )
            st.caption(
                "Rows are the true class, columns are what the model predicted. "
                "Off-diagonal cells are the errors worth reading closely."
            )
        else:
            cards.empty_state("No confusion matrix in metrics.json.")

    with tabs[1]:
        roc = metrics.get("roc")
        if roc:
            st.plotly_chart(
                charts.roc_curve(roc),
                width="stretch",
                config={"displayModeBar": False},
            )
            st.caption(
                "One-vs-rest curves. A class sitting close to the diagonal is one "
                "the model cannot separate from the rest."
            )
        else:
            cards.empty_state("No ROC data in metrics.json.")

    with tabs[2]:
        per_class = metrics.get("per_class")
        if per_class:
            frame = pd.DataFrame(per_class)
            st.dataframe(frame, width="stretch", hide_index=True)

            import plotly.graph_objects as go

            figure = go.Figure()
            for column, color in (
                ("precision", COLORS["accent"]),
                ("recall", COLORS["probe"]),
                ("f1", COLORS["violet"]),
            ):
                if column in frame.columns:
                    figure.add_trace(
                        go.Bar(
                            x=frame["class"],
                            y=frame[column],
                            name=column.capitalize(),
                            marker=dict(color=color, line=dict(width=0)),
                        )
                    )

            layout = dict(PLOTLY_LAYOUT)
            layout["yaxis"] = dict(layout["yaxis"], range=[0, 1.02])
            figure.update_layout(**layout, height=320, barmode="group")
            st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

            st.caption(
                "Classes with low support are the ones to be sceptical about. "
                "A high score on a class with a few hundred test flows says much "
                "less than the same score on a class with a hundred thousand."
            )
        else:
            cards.empty_state("No per-class breakdown in metrics.json.")

    with tabs[3]:
        importance = engine.feature_importance()
        if importance is not None:
            st.plotly_chart(
                charts.feature_importance(importance),
                width="stretch",
                config={"displayModeBar": False},
            )
            st.caption(
                "Read from the loaded model directly. Tree ensembles expose this; "
                "an SVM does not, and the tab stays empty in that case."
            )
        else:
            cards.empty_state(
                "The deployed model does not expose feature importances.",
                "Random Forest, XGBoost and Decision Tree do. SVM does not.",
            )

    with tabs[4]:
        comparison = metrics.get("comparison")
        if comparison:
            frame = pd.DataFrame(comparison)
            st.dataframe(frame, width="stretch", hide_index=True)
            st.caption("Every model trained during selection, as recorded at training time.")
        else:
            cards.empty_state("No model comparison in metrics.json.")

    st.caption(
        f"Model {metrics.get('model_name', 'unknown')} \u00b7 "
        f"trained {metrics.get('trained_at', 'unknown')} \u00b7 "
        f"dataset {metrics.get('dataset', 'unknown')}"
    )
