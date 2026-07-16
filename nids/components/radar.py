"""
Live threat radar.

Drawn as plain elements in the page, not inside a component iframe. That choice
is the point of this module: Streamlit reloads a component iframe every time it
reruns, and a reload is visible as a flash. Ordinary elements are re-rendered in
place, so the radar can update on a timer without blinking.

Because there is no iframe there is also no JavaScript, so the sweep and the
per-blip flash are CSS animations (see the radar section of theme.CSS). The
animations survive reruns through a negative animation-delay computed here from
the server clock: an element rendered with "animation-delay: -1.2s" begins 1.2
seconds into its cycle, so a fresh element picks the sweep up where the previous
one left off rather than restarting at zero.

Each detected flow becomes a blip:

  * bearing  - stable per source address, derived from a hash of the address, so
               the same attacker keeps returning to the same part of the scope
  * range    - 0.0 at the centre (local network) to 1.0 at the rim (remote)
  * severity - drives colour, blip size and whether a shockwave ring is drawn
  * age      - blips fade out over the retention window

Contrast note: labels use the off-white body colour, not pure white, to stay
consistent with the rest of the interface.
"""

import hashlib
import math
import time
from typing import Any, Dict, List

import streamlit as st

from ..theme import COLORS, class_severity, html

# Colour and diameter per severity bucket.
_SEVERITY_STYLE = {
    "critical": (COLORS["critical"], 9.0),
    "attack": (COLORS["attack"], 7.5),
    "probe": (COLORS["probe"], 6.0),
    "normal": (COLORS["normal"], 4.5),
}


def bearing_for(address: str) -> float:
    """Map an address to a stable bearing in degrees (0-360)."""
    digest = hashlib.md5(str(address).encode("utf-8")).hexdigest()
    return (int(digest[:6], 16) % 3600) / 10.0


def range_for(address: str, confidence: float) -> float:
    """
    Map a flow to a radar range between 0.18 and 0.96.

    Private addresses sit closer to the centre. Within a band, a higher model
    confidence pushes the blip slightly outward so certain detections sit on the
    clearer part of the scope.
    """
    text = str(address)
    is_private = (
        text.startswith("10.")
        or text.startswith("192.168.")
        or text.startswith("172.16.")
        or text.startswith("127.")
    )
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    jitter = (int(digest[6:10], 16) % 100) / 100.0

    if is_private:
        base = 0.18 + jitter * 0.28
    else:
        base = 0.52 + jitter * 0.34

    return min(0.96, base + float(confidence) * 0.08)


def build_blips(rows: List[Dict[str, Any]], now: float = None) -> List[Dict[str, Any]]:
    """
    Convert flow records into radar blips.

    Every row needs: src_ip, prediction, confidence, ts (epoch seconds).
    """
    now = now if now is not None else time.time()
    blips = []

    for row in rows:
        label = row.get("prediction", "BENIGN")
        confidence = float(row.get("confidence", 0.5))
        source = row.get("src_ip", "0.0.0.0")

        blips.append(
            {
                "bearing": bearing_for(source),
                "range": range_for(source, confidence),
                "severity": class_severity(label),
                "label": label,
                "src": str(source),
                "age": max(0.0, now - float(row.get("ts", now))),
                "confidence": confidence,
            }
        )

    return blips


def _blip_markup(
    blip: Dict[str, Any], phase: float, sweep_period: float, retention: float
) -> str:
    """Build one blip, positioned and phase-locked to the sweep."""
    color, size = _SEVERITY_STYLE.get(blip["severity"], _SEVERITY_STYLE["attack"])

    # Polar to cartesian, as percentages of the scope. Bearing zero is north, so
    # ninety degrees come off to match screen coordinates.
    radians = math.radians(blip["bearing"] - 90.0)
    x = 50.0 + math.cos(radians) * blip["range"] * 50.0
    y = 50.0 + math.sin(radians) * blip["range"] * 50.0

    fade = max(0.12, 1.0 - blip["age"] / retention)

    # Delay that makes this blip flash exactly as the sweep crosses its bearing.
    # The sweep sits at angle zero at (now - phase) and reaches this bearing
    # (bearing / 360) of a period later; solving for the negative delay that
    # places the flash there gives the expression below.
    bearing_offset = (blip["bearing"] / 360.0) * sweep_period
    delay = (phase - bearing_offset) % sweep_period

    parts = [
        f'<div class="blip" style="left:{x:.2f}%;top:{y:.2f}%;'
        f'opacity:{fade:.3f};--c:{color};--size:{size}px;'
        f'--blip-delay:-{delay:.3f}s;">'
    ]

    # A ring only on fresh, serious contacts. Drawing it on everything would turn
    # the scope into noise.
    if blip["severity"] in ("critical", "attack") and blip["age"] < 6:
        parts.append(f'<div class="blip-wave" style="--c:{color};"></div>')

    parts.append('<div class="blip-dot"></div>')

    if blip["severity"] == "critical" and fade > 0.55:
        parts.append(f'<div class="blip-label">{blip["src"]}</div>')

    parts.append("</div>")
    return "".join(parts)


def render(
    blips: List[Dict[str, Any]],
    height: int = 420,
    retention: float = 45.0,
    sweep_period: float = 4.0,
    scanning: bool = True,
    show_benign: bool = False,
) -> None:
    """
    Draw the radar.

    Args:
        blips: output of build_blips
        height: maximum diameter of the scope in pixels
        retention: seconds a blip stays on the scope before it disappears
        sweep_period: seconds for one full rotation of the sweep
        scanning: when False the sweep is parked and the scope dims
        show_benign: when False only non-benign blips are drawn
    """
    if not show_benign:
        blips = [b for b in blips if b["severity"] != "normal"]

    blips = [b for b in blips if b["age"] <= retention][-140:]

    now = time.time()
    phase = now % sweep_period

    threats = sum(1 for b in blips if b["severity"] in ("attack", "critical"))
    dots = "".join(_blip_markup(b, phase, sweep_period, retention) for b in blips)

    bearings = []
    for angle, style in (
        (0, "left:50%;top:6%;transform:translateX(-50%);"),
        (90, "right:5%;top:50%;transform:translateY(-50%);"),
        (180, "left:50%;bottom:6%;transform:translateX(-50%);"),
        (270, "left:5%;top:50%;transform:translateY(-50%);"),
    ):
        bearings.append(f'<div class="radar-bearing" style="{style}">{angle:03d}</div>')

    parked = "" if scanning else " radar-parked"
    status = "SCANNING" if scanning else "STANDBY"
    status_color = COLORS["accent"] if scanning else COLORS["text_muted"]
    contacts = f"{threats} CONTACTS" if threats else "&nbsp;"

    markup = f"""
<div class="radar-meta">
<span style="color:{COLORS['attack']};font-weight:700;">{contacts}</span>
<span style="color:{status_color};">{status}</span>
</div>
<div class="radar-shell">
<div class="radar{parked}" style="--radar-size:{height}px;--sweep-period:{sweep_period}s;--sweep-delay:-{phase:.3f}s;">
<div class="radar-grid"></div>
<div class="radar-rim"></div>
<div class="radar-sweep"></div>
<div class="radar-cross"></div>
<div class="radar-center"></div>
{"".join(bearings)}
{dots}
</div>
</div>
<div class="radar-legend">
<span style="color:{COLORS['critical']};"><i></i>CRITICAL</span>
<span style="color:{COLORS['attack']};"><i></i>ATTACK</span>
<span style="color:{COLORS['probe']};"><i></i>PROBE</span>
<span style="color:{COLORS['normal']};"><i></i>NORMAL</span>
</div>
"""

    st.markdown(html(markup), unsafe_allow_html=True)
