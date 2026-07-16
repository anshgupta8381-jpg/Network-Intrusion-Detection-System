"""
Inference engine.

The application never trains. It loads whatever the offline pipeline exported
and serves it for both live and batch input.

Expected files in the models directory:

    models/
        model.joblib             the fitted classifier
        scaler.joblib            the scaler fitted on the training features
        feature_columns.json     ordered feature names used at training time
        label_encoder.joblib     optional, maps class indices back to names
        metrics.json             optional, evaluation results for the
                                 model performance page

If model.joblib is absent the engine reports SIMULATION mode and returns the
labels attached by the simulator. Every screen keeps working, which is what lets
the interface be finished before the model is.
"""

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .schema import FEATURE_COLUMNS, align_to_schema

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


@dataclass
class EngineStatus:
    """Describes what the engine is currently able to do."""

    mode: str = "SIMULATION"        # SIMULATION or MODEL
    model_name: str = "None"
    feature_count: int = len(FEATURE_COLUMNS)
    classes: List[str] = field(default_factory=list)
    has_scaler: bool = False
    message: str = ""


class Engine:
    """Loads the exported artefacts once and scores flows on demand."""

    def __init__(self, models_dir: str = MODELS_DIR):
        self.models_dir = models_dir
        self.model = None
        self.scaler = None
        self.label_encoder = None
        self.feature_columns = list(FEATURE_COLUMNS)
        self.metrics = None
        self.status = EngineStatus()
        self._load()

    # -- loading ---------------------------------------------------------

    def _path(self, name: str) -> str:
        return os.path.join(self.models_dir, name)

    def _load(self) -> None:
        model_path = self._path("model.joblib")

        if not os.path.exists(model_path):
            self.status = EngineStatus(
                mode="SIMULATION",
                model_name="None",
                feature_count=len(self.feature_columns),
                classes=[],
                has_scaler=False,
                message="No model.joblib found. Running on simulated traffic.",
            )
            self._load_metrics()
            return

        try:
            import joblib
        except ImportError:
            self.status.message = "joblib is not installed. Run: pip install joblib"
            return

        try:
            self.model = joblib.load(model_path)

            columns_path = self._path("feature_columns.json")
            if os.path.exists(columns_path):
                with open(columns_path, "r", encoding="utf-8") as handle:
                    self.feature_columns = json.load(handle)

            scaler_path = self._path("scaler.joblib")
            if os.path.exists(scaler_path):
                self.scaler = joblib.load(scaler_path)

            encoder_path = self._path("label_encoder.joblib")
            if os.path.exists(encoder_path):
                self.label_encoder = joblib.load(encoder_path)

            classes = []
            if self.label_encoder is not None:
                classes = list(self.label_encoder.classes_)
            elif hasattr(self.model, "classes_"):
                classes = [str(c) for c in self.model.classes_]

            self.status = EngineStatus(
                mode="MODEL",
                model_name=type(self.model).__name__,
                feature_count=len(self.feature_columns),
                classes=classes,
                has_scaler=self.scaler is not None,
                message="Model loaded.",
            )

        except Exception as error:  # noqa: BLE001 - surfaced in the interface
            self.model = None
            self.status = EngineStatus(
                mode="SIMULATION",
                message=f"Model failed to load ({error}). Falling back to simulation.",
            )

        self._load_metrics()

    def _load_metrics(self) -> None:
        metrics_path = self._path("metrics.json")
        if os.path.exists(metrics_path):
            try:
                with open(metrics_path, "r", encoding="utf-8") as handle:
                    self.metrics = json.load(handle)
            except Exception:  # noqa: BLE001
                self.metrics = None

    # -- inference -------------------------------------------------------

    def _decode(self, indices) -> List[str]:
        if self.label_encoder is not None:
            return [str(x) for x in self.label_encoder.inverse_transform(indices)]
        return [str(x) for x in indices]

    def predict_frame(self, frame: pd.DataFrame) -> Tuple[List[str], List[float], List[str]]:
        """
        Score a DataFrame of raw flow features.

        Returns predictions, confidences and the list of feature columns that
        were missing from the input and had to be zero-filled.
        """
        aligned, missing = align_to_schema(frame, self.feature_columns)

        if self.model is None:
            # Simulation mode. Use the attached ground truth where the caller
            # supplied it, otherwise treat everything as benign rather than
            # inventing a detection.
            if "_truth" in frame.columns:
                labels = frame["_truth"].astype(str).tolist()
            elif "Label" in frame.columns:
                labels = frame["Label"].astype(str).tolist()
            elif "prediction" in frame.columns:
                labels = frame["prediction"].astype(str).tolist()
            else:
                labels = ["BENIGN"] * len(frame)

            if "confidence" in frame.columns:
                confidences = frame["confidence"].astype(float).tolist()
            else:
                from .simulator import CONFIDENCE_BANDS
                import random

                confidences = []
                for label in labels:
                    low, high = CONFIDENCE_BANDS.get(label, (0.6, 0.9))
                    confidences.append(round(random.uniform(low, high), 3))

            return labels, confidences, missing

        # The DataFrame is passed to the scaler rather than a raw array. When the
        # scaler was fitted with feature names, sklearn then verifies the column
        # order for us and raises on a mismatch, which is a far better outcome
        # than silently scoring columns in the wrong order.
        features = aligned
        if self.scaler is not None:
            features = self.scaler.transform(aligned)

        raw = self.model.predict(features)
        labels = self._decode(raw)

        if hasattr(self.model, "predict_proba"):
            proba = self.model.predict_proba(features)
            confidences = np.max(proba, axis=1).round(3).tolist()
        else:
            # Trees without probability output still need a number in the
            # confidence column, and a flat placeholder is more honest than a
            # fabricated distribution.
            confidences = [1.0] * len(labels)

        return labels, [float(c) for c in confidences], missing

    def predict_records(self, records: List[dict]) -> List[dict]:
        """Score a list of flow dictionaries and write results back onto them."""
        if not records:
            return []

        frame = pd.DataFrame(records)
        labels, confidences, _ = self.predict_frame(frame)

        for record, label, confidence in zip(records, labels, confidences):
            record["prediction"] = label
            record["confidence"] = round(float(confidence), 3)

        return records

    def reload(self) -> None:
        """Re-read the model directory. Used by the settings page."""
        self.model = None
        self.scaler = None
        self.label_encoder = None
        self.metrics = None
        self._load()

    def available_models(self) -> List[str]:
        """List every .joblib in the models directory that is not a scaler."""
        if not os.path.isdir(self.models_dir):
            return []
        return sorted(
            name
            for name in os.listdir(self.models_dir)
            if name.endswith(".joblib") and "scaler" not in name and "encoder" not in name
        )

    def feature_importance(self) -> Optional[pd.DataFrame]:
        """Return a sorted importance table when the model exposes one."""
        if self.model is None or not hasattr(self.model, "feature_importances_"):
            return None

        importances = self.model.feature_importances_
        if len(importances) != len(self.feature_columns):
            return None

        return (
            pd.DataFrame({"feature": self.feature_columns, "importance": importances})
            .sort_values("importance", ascending=False)
            .reset_index(drop=True)
        )
