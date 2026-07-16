"""
Flow feature schema.

This is the contract between the offline training pipeline and the application.
The exported model is trained on FEATURE_COLUMNS in this exact order, and every
input path (live capture and CSV upload) is aligned to it before inference.

When the real model is exported, drop a feature_columns.json next to the model
file and the engine will use that list instead of the default below. Keeping the
column order in a file rather than hard-coding it means retraining with a
different feature set does not require a code change.
"""

# The 20-feature subset used by default. These are all bidirectional flow
# statistics available both in CICIDS2017 and from nfstream, which is what makes
# live capture and batch upload interchangeable.
FEATURE_COLUMNS = [
    "Flow Duration",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Total Length of Fwd Packets",
    "Total Length of Bwd Packets",
    "Fwd Packet Length Max",
    "Fwd Packet Length Mean",
    "Bwd Packet Length Max",
    "Bwd Packet Length Mean",
    "Flow Bytes/s",
    "Flow Packets/s",
    "Flow IAT Mean",
    "Flow IAT Std",
    "Flow IAT Max",
    "Fwd IAT Mean",
    "Bwd IAT Mean",
    "Min Packet Length",
    "Max Packet Length",
    "Packet Length Mean",
    "SYN Flag Count",
]

# Attack classes the application knows how to display. The CICIDS2017 labels are
# collapsed into these buckets during training.
CLASSES = [
    "BENIGN",
    "DoS",
    "DDoS",
    "PortScan",
    "FTP-Patator",
    "SSH-Patator",
    "Web Attack",
    "Bot",
    "Infiltration",
]

ATTACK_CLASSES = [c for c in CLASSES if c != "BENIGN"]

# Human-readable description shown in the alert feed and the about page.
CLASS_DESCRIPTIONS = {
    "BENIGN": "Normal traffic. No action required.",
    "DoS": "Denial of service against a single target.",
    "DDoS": "Distributed denial of service from many sources.",
    "PortScan": "Reconnaissance sweep across ports or hosts.",
    "FTP-Patator": "Brute force attempt against an FTP service.",
    "SSH-Patator": "Brute force attempt against an SSH service.",
    "Web Attack": "Injection, cross-site scripting, or web brute force.",
    "Bot": "Host contacting a command and control channel.",
    "Infiltration": "Internal compromise moving laterally.",
}

# Columns the result table displays, in order, on top of the model features.
METADATA_COLUMNS = ["ts", "src_ip", "src_port", "dst_ip", "dst_port", "protocol"]

RESULT_COLUMNS = METADATA_COLUMNS + ["prediction", "confidence"]


def normalise_columns(columns):
    """
    Return a lookup that maps loosely-formatted CSV headers onto schema names.

    CICIDS2017 CSV exports ship with inconsistent leading spaces and casing
    depending on which mirror the file came from, so a direct match on the raw
    header fails often enough to be worth handling.
    """
    lookup = {}
    for column in columns:
        key = str(column).strip().lower().replace("_", " ")
        key = " ".join(key.split())
        lookup[key] = column
    return lookup


def align_to_schema(frame, feature_columns=None):
    """
    Reindex a DataFrame onto the model feature order.

    Missing columns are filled with zero and reported back to the caller so the
    upload page can warn the analyst rather than silently scoring garbage.
    """
    import pandas as pd

    feature_columns = feature_columns or FEATURE_COLUMNS
    lookup = normalise_columns(frame.columns)

    aligned = pd.DataFrame(index=frame.index)
    missing = []

    for wanted in feature_columns:
        key = wanted.strip().lower().replace("_", " ")
        key = " ".join(key.split())
        if key in lookup:
            aligned[wanted] = pd.to_numeric(frame[lookup[key]], errors="coerce")
        else:
            aligned[wanted] = 0.0
            missing.append(wanted)

    # CICIDS2017 contains infinities in the rate columns wherever duration is
    # zero, and the training pipeline replaces them the same way.
    import numpy as np

    aligned = aligned.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    return aligned, missing
