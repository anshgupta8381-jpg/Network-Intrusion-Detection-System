"""
Synthetic traffic generator.

The application is built ahead of the trained model, so this module stands in
for both the capture layer and the inference layer. It produces flows whose
feature values sit in a plausible range for each class, which is enough to drive
every screen, the radar and the alerting logic.

This is a development aid, not part of the detection path. Once the real model
and nfstream capture are wired in, the simulator only remains as a demo mode
for presentations where live traffic is not available.
"""

import random
import time
from typing import Dict, List

from .schema import FEATURE_COLUMNS

# A small cast of recurring hosts. Reusing addresses means the radar shows the
# same attacker returning to the same bearing, which reads far better than
# uniformly random noise.
INTERNAL_HOSTS = [f"192.168.1.{i}" for i in (12, 24, 31, 44, 57, 68, 79, 88, 101, 112)]
SERVERS = [f"10.0.0.{i}" for i in (3, 5, 7, 9, 11)]

HOSTILE_HOSTS = [
    "203.0.113.7",
    "203.0.113.9",
    "198.51.100.2",
    "198.51.100.44",
    "45.147.230.18",
    "185.220.101.34",
    "91.219.236.166",
    "104.244.76.13",
]

BOTNET_SWARM = [f"172.16.{a}.{b}" for a in (4, 9, 21) for b in (11, 45, 90)]

# Relative frequency of each class in the simulated stream. Benign dominates,
# which mirrors the real class imbalance in CICIDS2017 and keeps the dashboard
# honest about how rare a true positive actually is.
CLASS_WEIGHTS = {
    "BENIGN": 78,
    "PortScan": 7,
    "DoS": 5,
    "DDoS": 3,
    "SSH-Patator": 2.5,
    "FTP-Patator": 1.5,
    "Web Attack": 1.5,
    "Bot": 1,
    "Infiltration": 0.5,
}

# Confidence band per class. Infiltration is rare in CICIDS2017 and the model is
# genuinely less certain about it, so the simulated confidence reflects that
# rather than reporting a flat 0.99 everywhere.
CONFIDENCE_BANDS = {
    "BENIGN": (0.88, 0.995),
    "PortScan": (0.82, 0.97),
    "DoS": (0.90, 0.995),
    "DDoS": (0.93, 0.998),
    "SSH-Patator": (0.85, 0.97),
    "FTP-Patator": (0.83, 0.96),
    "Web Attack": (0.72, 0.93),
    "Bot": (0.68, 0.91),
    "Infiltration": (0.55, 0.82),
}

PROTOCOLS = ["TCP", "UDP"]


def _profile(label: str) -> Dict[str, float]:
    """Return a feature dictionary shaped like the given class."""
    r = random.random

    if label == "BENIGN":
        fwd_packets = random.randint(4, 60)
        bwd_packets = random.randint(3, 55)
        duration = random.uniform(50_000, 9_000_000)
        fwd_bytes = fwd_packets * random.uniform(60, 900)
        bwd_bytes = bwd_packets * random.uniform(60, 1400)
        syn = random.randint(0, 2)

    elif label == "PortScan":
        # Very short flows, one packet out, little or nothing back.
        fwd_packets = random.randint(1, 2)
        bwd_packets = random.randint(0, 1)
        duration = random.uniform(20, 8_000)
        fwd_bytes = fwd_packets * random.uniform(40, 60)
        bwd_bytes = bwd_packets * random.uniform(0, 60)
        syn = 1

    elif label in ("DoS", "DDoS"):
        # Long, packet-heavy, asymmetric.
        fwd_packets = random.randint(400, 9000)
        bwd_packets = random.randint(0, 40)
        duration = random.uniform(1_000_000, 30_000_000)
        fwd_bytes = fwd_packets * random.uniform(60, 1500)
        bwd_bytes = bwd_packets * random.uniform(0, 200)
        syn = random.randint(1, 60) if label == "DoS" else random.randint(50, 400)

    elif label in ("FTP-Patator", "SSH-Patator"):
        # Repeated small login attempts with steady inter-arrival times.
        fwd_packets = random.randint(10, 40)
        bwd_packets = random.randint(8, 35)
        duration = random.uniform(400_000, 5_000_000)
        fwd_bytes = fwd_packets * random.uniform(40, 250)
        bwd_bytes = bwd_packets * random.uniform(40, 300)
        syn = random.randint(1, 6)

    elif label == "Web Attack":
        fwd_packets = random.randint(6, 45)
        bwd_packets = random.randint(5, 40)
        duration = random.uniform(100_000, 4_000_000)
        fwd_bytes = fwd_packets * random.uniform(300, 2400)
        bwd_bytes = bwd_packets * random.uniform(200, 3000)
        syn = random.randint(1, 4)

    elif label == "Bot":
        # Small, regular beacons out to a controller.
        fwd_packets = random.randint(2, 10)
        bwd_packets = random.randint(2, 10)
        duration = random.uniform(200_000, 2_000_000)
        fwd_bytes = fwd_packets * random.uniform(80, 400)
        bwd_bytes = bwd_packets * random.uniform(80, 400)
        syn = random.randint(0, 2)

    else:  # Infiltration
        fwd_packets = random.randint(20, 300)
        bwd_packets = random.randint(15, 280)
        duration = random.uniform(2_000_000, 20_000_000)
        fwd_bytes = fwd_packets * random.uniform(200, 4000)
        bwd_bytes = bwd_packets * random.uniform(200, 4000)
        syn = random.randint(0, 5)

    total_packets = max(1, fwd_packets + bwd_packets)
    total_bytes = fwd_bytes + bwd_bytes
    seconds = max(duration / 1_000_000, 1e-6)

    fwd_mean = fwd_bytes / max(fwd_packets, 1)
    bwd_mean = bwd_bytes / max(bwd_packets, 1)
    iat_mean = duration / total_packets

    return {
        "Flow Duration": duration,
        "Total Fwd Packets": float(fwd_packets),
        "Total Backward Packets": float(bwd_packets),
        "Total Length of Fwd Packets": fwd_bytes,
        "Total Length of Bwd Packets": bwd_bytes,
        "Fwd Packet Length Max": fwd_mean * random.uniform(1.1, 2.4),
        "Fwd Packet Length Mean": fwd_mean,
        "Bwd Packet Length Max": bwd_mean * random.uniform(1.1, 2.6),
        "Bwd Packet Length Mean": bwd_mean,
        "Flow Bytes/s": total_bytes / seconds,
        "Flow Packets/s": total_packets / seconds,
        "Flow IAT Mean": iat_mean,
        "Flow IAT Std": iat_mean * r() * 0.9,
        "Flow IAT Max": iat_mean * random.uniform(1.5, 6.0),
        "Fwd IAT Mean": iat_mean * random.uniform(0.7, 1.3),
        "Bwd IAT Mean": iat_mean * random.uniform(0.7, 1.4),
        "Min Packet Length": random.uniform(0, 60),
        "Max Packet Length": max(fwd_mean, bwd_mean) * random.uniform(1.2, 3.0),
        "Packet Length Mean": total_bytes / total_packets,
        "SYN Flag Count": float(syn),
    }


def _endpoints(label: str):
    """Pick a plausible source and destination pair for the class."""
    if label == "BENIGN":
        return random.choice(INTERNAL_HOSTS), random.choice(SERVERS)
    if label == "DDoS":
        return random.choice(BOTNET_SWARM + HOSTILE_HOSTS), random.choice(SERVERS[:2])
    if label == "Bot":
        return random.choice(INTERNAL_HOSTS), random.choice(HOSTILE_HOSTS)
    if label == "Infiltration":
        return random.choice(INTERNAL_HOSTS), random.choice(SERVERS)
    return random.choice(HOSTILE_HOSTS), random.choice(SERVERS)


def _ports(label: str):
    src_port = random.randint(1024, 65535)
    dst_port = {
        "FTP-Patator": 21,
        "SSH-Patator": 22,
        "Web Attack": random.choice([80, 443, 8080]),
        "DoS": 80,
        "DDoS": 80,
        "Bot": random.choice([6667, 8080, 4444]),
    }.get(label, random.choice([80, 443, 22, 53, 3389, 445, 8080]))

    if label == "PortScan":
        dst_port = random.randint(1, 9000)

    return src_port, dst_port


def sample_label(attack_bias: float = 1.0) -> str:
    """
    Draw a class from the weighted distribution.

    attack_bias scales every attack weight, so a demo can be pushed toward a
    busy scope without editing the base distribution.
    """
    labels, weights = [], []
    for label, weight in CLASS_WEIGHTS.items():
        labels.append(label)
        weights.append(weight if label == "BENIGN" else weight * attack_bias)
    return random.choices(labels, weights=weights, k=1)[0]


def generate_flow(ts: float = None, attack_bias: float = 1.0) -> Dict:
    """Produce one labelled flow record with features and metadata."""
    ts = ts if ts is not None else time.time()
    label = sample_label(attack_bias)

    src_ip, dst_ip = _endpoints(label)
    src_port, dst_port = _ports(label)
    low, high = CONFIDENCE_BANDS[label]

    record = {
        "ts": ts,
        "src_ip": src_ip,
        "src_port": src_port,
        "dst_ip": dst_ip,
        "dst_port": dst_port,
        "protocol": "UDP" if label == "DDoS" and random.random() < 0.3 else random.choice(PROTOCOLS),
        "prediction": label,
        "confidence": round(random.uniform(low, high), 3),
        "_truth": label,
    }
    record.update(_profile(label))
    return record


def generate_batch(count: int, attack_bias: float = 1.0, spread_seconds: float = 600.0) -> List[Dict]:
    """Produce a list of flows spread backwards over a time window."""
    now = time.time()
    rows = []
    for i in range(count):
        ts = now - spread_seconds * (1 - i / max(count - 1, 1))
        rows.append(generate_flow(ts=ts, attack_bias=attack_bias))
    return rows


def sample_csv(count: int = 500) -> "pd.DataFrame":
    """Build a CICIDS-style CSV the upload page can be tested against."""
    import pandas as pd

    rows = generate_batch(count, attack_bias=2.0)
    frame = pd.DataFrame(rows)
    frame = frame.rename(columns={"_truth": "Label"})
    keep = FEATURE_COLUMNS + ["Label"]
    return frame[keep]
