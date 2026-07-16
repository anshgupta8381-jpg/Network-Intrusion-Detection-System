"""
Detection log storage.

Session state holds the rolling live view, which is deliberately short-lived.
Anything that needs to survive a browser refresh or be exported later goes to
SQLite. Only malicious flows are written; logging every benign flow would grow
the file quickly and add nothing an analyst would read.
"""

import os
import sqlite3
import threading
import time
from typing import Dict, List, Optional

import pandas as pd

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "detections.db")

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS detections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,
    src_ip      TEXT    NOT NULL,
    src_port    INTEGER,
    dst_ip      TEXT    NOT NULL,
    dst_port    INTEGER,
    protocol    TEXT,
    prediction  TEXT    NOT NULL,
    confidence  REAL    NOT NULL,
    severity    TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    acknowledged INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(ts);
CREATE INDEX IF NOT EXISTS idx_detections_pred ON detections(prediction);
CREATE INDEX IF NOT EXISTS idx_detections_src ON detections(src_ip);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init() -> None:
    """Create the table on first run."""
    with _lock:
        connection = _connect()
        try:
            connection.executescript(SCHEMA)
            connection.commit()
        finally:
            connection.close()


def write_detections(rows: List[Dict], source: str = "live") -> int:
    """
    Persist malicious detections. Benign rows are skipped.

    Returns the number of rows written.
    """
    from ..theme import class_severity

    payload = []
    for row in rows:
        label = row.get("prediction", "BENIGN")
        if label == "BENIGN":
            continue
        payload.append(
            (
                float(row.get("ts", time.time())),
                str(row.get("src_ip", "")),
                int(row.get("src_port", 0) or 0),
                str(row.get("dst_ip", "")),
                int(row.get("dst_port", 0) or 0),
                str(row.get("protocol", "")),
                str(label),
                float(row.get("confidence", 0.0)),
                class_severity(label),
                source,
            )
        )

    if not payload:
        return 0

    with _lock:
        connection = _connect()
        try:
            connection.executemany(
                """
                INSERT INTO detections
                    (ts, src_ip, src_port, dst_ip, dst_port, protocol,
                     prediction, confidence, severity, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            connection.commit()
        finally:
            connection.close()

    return len(payload)


def read_detections(
    limit: int = 1000,
    since: Optional[float] = None,
    prediction: Optional[str] = None,
    src_ip: Optional[str] = None,
    min_confidence: float = 0.0,
) -> pd.DataFrame:
    """Read the log back with optional filters applied in SQL."""
    query = "SELECT * FROM detections WHERE confidence >= ?"
    params: List = [min_confidence]

    if since is not None:
        query += " AND ts >= ?"
        params.append(since)
    if prediction and prediction != "All":
        query += " AND prediction = ?"
        params.append(prediction)
    if src_ip:
        query += " AND src_ip LIKE ?"
        params.append(f"%{src_ip}%")

    query += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)

    with _lock:
        connection = _connect()
        try:
            frame = pd.read_sql_query(query, connection, params=params)
        finally:
            connection.close()

    return frame


def counts_by_class(since: Optional[float] = None) -> pd.DataFrame:
    """Aggregate detections per class for the distribution chart."""
    query = "SELECT prediction, COUNT(*) AS count FROM detections"
    params: List = []
    if since is not None:
        query += " WHERE ts >= ?"
        params.append(since)
    query += " GROUP BY prediction ORDER BY count DESC"

    with _lock:
        connection = _connect()
        try:
            frame = pd.read_sql_query(query, connection, params=params)
        finally:
            connection.close()

    return frame


def total_count() -> int:
    """Number of rows in the log."""
    with _lock:
        connection = _connect()
        try:
            cursor = connection.execute("SELECT COUNT(*) FROM detections")
            return int(cursor.fetchone()[0])
        finally:
            connection.close()


def acknowledge(detection_id: int) -> None:
    """Mark a single alert as handled."""
    with _lock:
        connection = _connect()
        try:
            connection.execute(
                "UPDATE detections SET acknowledged = 1 WHERE id = ?", (detection_id,)
            )
            connection.commit()
        finally:
            connection.close()


def clear() -> None:
    """Empty the log. Exposed on the settings page behind a confirmation."""
    with _lock:
        connection = _connect()
        try:
            connection.execute("DELETE FROM detections")
            connection.commit()
        finally:
            connection.close()
