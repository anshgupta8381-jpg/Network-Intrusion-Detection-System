"""
Visual theme for the NIDS dashboard.

Colour choices follow WCAG 2.x contrast guidance for dark interfaces:

  * The page base is near-black (#05060A) rather than pure #000000. Pure black
    paired with pure white measures 21:1 and triggers halation ("glowing" text)
    for readers with astigmatism.
  * Body text is off-white (#E6EAF2) instead of #FFFFFF. Measured against the
    card surface (#0C0E14) this is roughly 15:1, comfortably above the 4.5:1
    AA minimum for normal text without being harsh.
  * Secondary text (#9AA6BF) measures about 7.2:1 and clears AAA.
  * Muted text (#707C96) measures about 4.6:1 and is only used for labels,
    captions and large text.
  * Status colours are desaturated versions of the obvious primaries. Fully
    saturated red (#FF0000) and green (#00FF00) are hard to read on dark
    backgrounds even when the ratio technically passes, so the palette uses
    #FF5C6C, #3FDD9B and #FFB454 instead.
  * Status is never communicated by colour alone (WCAG 1.4.1). Every status is
    also carried by a text label and a glyph.
"""

# --------------------------------------------------------------------------
# Colour tokens
# --------------------------------------------------------------------------

COLORS = {
    # Surfaces, darkest to lightest
    "base": "#05060A",
    "surface": "#0C0E14",
    "surface_2": "#12151E",
    "surface_3": "#191D2A",
    "border": "#232838",
    "border_bright": "#2F3648",

    # Text
    "text": "#E6EAF2",
    "text_secondary": "#9AA6BF",
    "text_muted": "#707C96",

    # Accent
    "accent": "#3BE8DC",
    "accent_dim": "#1E9E97",
    "accent_soft": "rgba(59, 232, 220, 0.12)",

    # Status
    "normal": "#3FDD9B",
    "probe": "#FFB454",
    "attack": "#FF5C6C",
    "critical": "#FF3355",
    "info": "#8FA6FF",
    "violet": "#B48CFF",

    # Radar
    "radar_grid": "#1B4A47",
    "radar_sweep": "#3BE8DC",
}

# Colour assigned to each prediction class shown in tables and charts.
CLASS_COLORS = {
    "BENIGN": COLORS["normal"],
    "PortScan": COLORS["probe"],
    "DoS": COLORS["attack"],
    "DDoS": COLORS["critical"],
    "FTP-Patator": COLORS["violet"],
    "SSH-Patator": COLORS["violet"],
    "Web Attack": COLORS["attack"],
    "Bot": COLORS["info"],
    "Infiltration": COLORS["critical"],
}

# Severity bucket per class. Drives the radar, the alert feed and row styling.
CLASS_SEVERITY = {
    "BENIGN": "normal",
    "PortScan": "probe",
    "DoS": "attack",
    "DDoS": "critical",
    "FTP-Patator": "attack",
    "SSH-Patator": "attack",
    "Web Attack": "attack",
    "Bot": "attack",
    "Infiltration": "critical",
}

SEVERITY_COLORS = {
    "normal": COLORS["normal"],
    "probe": COLORS["probe"],
    "attack": COLORS["attack"],
    "critical": COLORS["critical"],
}

# Glyph shown next to every status so meaning does not depend on colour alone.
SEVERITY_GLYPH = {
    "normal": "\u25CF",    # filled circle
    "probe": "\u25B2",     # triangle
    "attack": "\u25C6",    # diamond
    "critical": "\u2716",  # cross
}


def class_color(label: str) -> str:
    """Return the display colour for a prediction label."""
    if label in CLASS_COLORS:
        return CLASS_COLORS[label]
    for key, value in CLASS_COLORS.items():
        if label.lower().startswith(key.lower()):
            return value
    return COLORS["text_secondary"]


def class_severity(label: str) -> str:
    """Return the severity bucket for a prediction label."""
    if label in CLASS_SEVERITY:
        return CLASS_SEVERITY[label]
    for key, value in CLASS_SEVERITY.items():
        if label.lower().startswith(key.lower()):
            return value
    return "attack"


# --------------------------------------------------------------------------
# Global stylesheet
# --------------------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --base: #05060A;
    --surface: #0C0E14;
    --surface-2: #12151E;
    --surface-3: #191D2A;
    --border: #232838;
    --border-bright: #2F3648;
    --text: #E6EAF2;
    --text-secondary: #9AA6BF;
    --text-muted: #707C96;
    --accent: #3BE8DC;
    --accent-dim: #1E9E97;
    --normal: #3FDD9B;
    --probe: #FFB454;
    --attack: #FF5C6C;
    --critical: #FF3355;
    --violet: #B48CFF;
    --font-display: 'Orbitron', sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
    --font-body: 'Inter', sans-serif;
}

/* ---------- Page shell ---------- */

.stApp {
    background:
        radial-gradient(1200px 600px at 15% -10%, rgba(59, 232, 220, 0.07), transparent 60%),
        radial-gradient(900px 500px at 95% 0%, rgba(180, 140, 255, 0.05), transparent 55%),
        var(--base);
    color: var(--text);
    font-family: var(--font-body);
}

/* Fine grid overlay that gives the page a depth plane behind the content. */
.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    background-image:
        linear-gradient(rgba(59, 232, 220, 0.045) 1px, transparent 1px),
        linear-gradient(90deg, rgba(59, 232, 220, 0.045) 1px, transparent 1px);
    background-size: 46px 46px;
    mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, #000 20%, transparent 78%);
    -webkit-mask-image: radial-gradient(ellipse 80% 60% at 50% 30%, #000 20%, transparent 78%);
}

/* Slow scanline pass. Kept very low contrast so it never fights with text. */
.stApp::after {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    background: repeating-linear-gradient(
        to bottom,
        rgba(255, 255, 255, 0.014) 0px,
        rgba(255, 255, 255, 0.014) 1px,
        transparent 1px,
        transparent 3px
    );
    opacity: 0.5;
}

.block-container {
    padding-top: 2.2rem;
    padding-bottom: 3rem;
    max-width: 1500px;
    position: relative;
    z-index: 1;
}

header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }

/* ---------- Typography ---------- */

h1, h2, h3 { font-family: var(--font-display); letter-spacing: 0.02em; color: var(--text); }
p, span, div, label { color: var(--text); }

.page-title {
    font-family: var(--font-display);
    font-size: 2.1rem;
    font-weight: 900;
    letter-spacing: 0.06em;
    margin: 0;
    background: linear-gradient(92deg, var(--text) 0%, var(--accent) 55%, var(--violet) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.page-subtitle {
    color: var(--text-secondary);
    font-size: 0.92rem;
    letter-spacing: 0.04em;
    margin-top: 0.25rem;
}

.section-title {
    font-family: var(--font-display);
    font-size: 0.95rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text);
    margin: 0 0 0.9rem 0;
    display: flex;
    align-items: center;
    gap: 0.6rem;
}

.section-title::before {
    content: "";
    width: 3px;
    height: 14px;
    background: var(--accent);
    box-shadow: 0 0 10px var(--accent);
    border-radius: 2px;
}

.mono { font-family: var(--font-mono); }

/* ---------- Panels ---------- */

.panel {
    position: relative;
    background:
        linear-gradient(160deg, rgba(255, 255, 255, 0.035) 0%, rgba(255, 255, 255, 0) 42%),
        var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1.15rem 1.25rem;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.05) inset,
        0 -1px 0 rgba(0, 0, 0, 0.6) inset,
        0 18px 40px -18px rgba(0, 0, 0, 0.95);
    overflow: hidden;
}

/* Clipped corner, a common convention in operations tooling. */
.panel::after {
    content: "";
    position: absolute;
    top: -1px;
    right: -1px;
    width: 16px;
    height: 16px;
    background: var(--base);
    border-left: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    transform: rotate(45deg) translate(6px, -12px);
}

/* ---------- KPI cards ---------- */

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 0.9rem;
    margin-bottom: 1.1rem;
    perspective: 1200px;
}

.kpi {
    position: relative;
    background:
        linear-gradient(155deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0) 45%),
        var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem 1.1rem 1.05rem 1.1rem;
    transform-style: preserve-3d;
    transition: transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1),
                box-shadow 0.35s ease,
                border-color 0.35s ease;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.06) inset,
        0 20px 44px -22px rgba(0, 0, 0, 0.95);
    overflow: hidden;
}

.kpi::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--kpi-accent, var(--accent));
    box-shadow: 0 0 14px var(--kpi-accent, var(--accent));
}

/* Sheen that travels across the card on hover. */
.kpi::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(115deg, transparent 30%, rgba(255, 255, 255, 0.07) 46%, transparent 62%);
    transform: translateX(-120%);
    transition: transform 0.7s ease;
}

.kpi:hover {
    transform: translateY(-4px) rotateX(5deg) rotateY(-3deg) scale(1.015);
    border-color: var(--border-bright);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.08) inset,
        0 26px 54px -20px rgba(0, 0, 0, 0.98),
        0 0 28px -8px var(--kpi-accent, var(--accent));
}

.kpi:hover::after { transform: translateX(120%); }

.kpi-label {
    font-family: var(--font-body);
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-muted);
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

.kpi-value {
    font-family: var(--font-display);
    font-size: 2.05rem;
    font-weight: 900;
    line-height: 1.15;
    margin-top: 0.35rem;
    color: var(--kpi-accent, var(--text));
    text-shadow: 0 0 22px color-mix(in srgb, var(--kpi-accent, var(--accent)) 45%, transparent);
    font-variant-numeric: tabular-nums;
}

.kpi-delta {
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--text-secondary);
    margin-top: 0.3rem;
}

/* ---------- Status pills ---------- */

.pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 0.18rem 0.55rem;
    border-radius: 6px;
    border: 1px solid currentColor;
    background: color-mix(in srgb, currentColor 12%, transparent);
}

/* ---------- Alert banner ---------- */

.alert-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border: 1px solid rgba(255, 92, 108, 0.5);
    border-left: 3px solid var(--attack);
    background: linear-gradient(90deg, rgba(255, 92, 108, 0.16), rgba(255, 92, 108, 0.03));
    border-radius: 10px;
    padding: 0.75rem 1rem;
    margin-top: 1rem;
    animation: alert-breathe 2.4s ease-in-out infinite;
}

@keyframes alert-breathe {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255, 92, 108, 0.24); }
    50%      { box-shadow: 0 0 26px -4px rgba(255, 92, 108, 0.55); }
}

.alert-text {
    font-family: var(--font-mono);
    font-size: 0.85rem;
    font-weight: 700;
    color: #FF8792;
    letter-spacing: 0.03em;
}

/* ---------- Sidebar ---------- */

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #090B11 0%, #06070C 100%);
    border-right: 1px solid var(--border);
}

section[data-testid="stSidebar"] > div { padding-top: 1.2rem; }

.brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0 0.4rem 1rem 0.4rem;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1rem;
}

.brand-mark {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: radial-gradient(circle at 32% 30%, #7FFFF4, var(--accent) 45%, var(--accent-dim) 100%);
    box-shadow: 0 0 18px rgba(59, 232, 220, 0.6), 0 0 4px #fff inset;
    animation: pulse-mark 2.6s ease-in-out infinite;
    flex-shrink: 0;
}

@keyframes pulse-mark {
    0%, 100% { transform: scale(1); opacity: 1; }
    50%      { transform: scale(0.9); opacity: 0.75; }
}

.brand-name {
    font-family: var(--font-display);
    font-size: 1.35rem;
    font-weight: 900;
    letter-spacing: 0.12em;
    color: var(--text);
    line-height: 1;
}

.brand-tag {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    letter-spacing: 0.16em;
    color: var(--text-muted);
    text-transform: uppercase;
    margin-top: 0.25rem;
}

/* Sidebar navigation rendered as radio buttons. */
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 0.15rem; }

section[data-testid="stSidebar"] div[role="radiogroup"] label {
    display: flex;
    align-items: center;
    padding: 0.5rem 0.7rem;
    border-radius: 8px;
    border-left: 2px solid transparent;
    cursor: pointer;
    transition: background 0.18s ease, border-color 0.18s ease, transform 0.18s ease;
}

section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    background: rgba(59, 232, 220, 0.07);
    transform: translateX(2px);
}

section[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none; }

section[data-testid="stSidebar"] div[role="radiogroup"] label p {
    font-family: var(--font-body);
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-secondary);
    margin: 0;
}

section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: linear-gradient(90deg, rgba(59, 232, 220, 0.16), transparent);
    border-left-color: var(--accent);
}

section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
    color: var(--accent);
    font-weight: 700;
}

.status-chip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.55rem 0.7rem;
    font-family: var(--font-mono);
    font-size: 0.72rem;
    color: var(--text-secondary);
    margin-top: 0.6rem;
}

.dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--chip-color, var(--normal));
    box-shadow: 0 0 10px var(--chip-color, var(--normal));
    animation: dot-blink 1.8s ease-in-out infinite;
}

@keyframes dot-blink {
    0%, 100% { opacity: 1; }
    50%      { opacity: 0.35; }
}

/* ---------- Widgets ---------- */

.stButton > button {
    font-family: var(--font-display);
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    background: linear-gradient(180deg, var(--surface-3), var(--surface-2));
    color: var(--text);
    border: 1px solid var(--border-bright);
    border-radius: 9px;
    padding: 0.5rem 1.1rem;
    width: 100%;
    transition: all 0.2s ease;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.07) inset, 0 8px 18px -10px rgba(0, 0, 0, 0.9);
}

.stButton > button:hover {
    border-color: var(--accent);
    color: var(--accent);
    transform: translateY(-1px);
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.1) inset, 0 0 22px -6px var(--accent);
}

.stButton > button:active { transform: translateY(1px); }

.stButton > button[kind="primary"] {
    background: linear-gradient(180deg, var(--accent), var(--accent-dim));
    color: #04211F;
    border-color: var(--accent);
}

div[data-testid="stSelectbox"] > div > div,
div[data-testid="stNumberInput"] input,
div[data-testid="stTextInput"] input {
    background: var(--surface-2) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 8px !important;
    font-family: var(--font-mono) !important;
}

div[data-testid="stMetricValue"] {
    font-family: var(--font-display);
    color: var(--accent);
}

/* Tabs */
button[data-baseweb="tab"] {
    font-family: var(--font-display) !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase;
    color: var(--text-muted) !important;
}

button[data-baseweb="tab"][aria-selected="true"] { color: var(--accent) !important; }
div[data-baseweb="tab-highlight"] { background: var(--accent) !important; }
div[data-baseweb="tab-border"] { background: var(--border) !important; }

/* Data tables */
div[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
}

/* File uploader */
section[data-testid="stFileUploaderDropzone"] {
    background: var(--surface-2);
    border: 1px dashed var(--border-bright);
    border-radius: 12px;
}

section[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent); }

/* Expander */
details[data-testid="stExpander"] {
    background: var(--surface);
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
}

/* Progress and slider accents */
div[data-testid="stSlider"] div[role="slider"] { background: var(--accent) !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: var(--base); }
::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent-dim); }

/* ---------- Radar ---------- */

/*
 * The radar is drawn in the page rather than inside a component iframe.
 * An iframe is torn down and reloaded on every rerun, which reads as a flash;
 * plain elements are just re-rendered in place.
 *
 * Nothing here uses JavaScript. The sweep and the per-blip flash are CSS
 * animations, and continuity across reruns comes from a negative
 * animation-delay computed from the server clock: a fresh element with
 * "animation-delay: -1.2s" starts already 1.2s into its cycle, so the sweep
 * carries on from where it was instead of snapping back to zero.
 */

.radar-shell {
    display: flex;
    justify-content: center;
    align-items: center;
    perspective: 900px;
}

.radar {
    position: relative;
    width: 100%;
    max-width: var(--radar-size, 420px);
    aspect-ratio: 1;
    border-radius: 50%;
    transform: rotateX(8deg);
    transition: transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
    background:
        radial-gradient(circle at 50% 45%, #071614 0%, #04070B 62%, #020406 100%);
    box-shadow:
        0 0 0 1px rgba(59, 232, 220, 0.22),
        0 0 60px -10px rgba(59, 232, 220, 0.35),
        0 40px 70px -30px rgba(0, 0, 0, 1),
        inset 0 0 60px rgba(0, 0, 0, 0.85);
    overflow: hidden;
}

.radar:hover { transform: rotateX(0deg) scale(1.02); }

/* Range rings and bearing spokes, both drawn with gradients. */
.radar-grid {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background:
        repeating-radial-gradient(circle at 50% 50%,
            transparent 0, transparent calc(12.5% - 1px),
            var(--radar-grid) calc(12.5% - 1px), var(--radar-grid) 12.5%),
        repeating-conic-gradient(from 0deg at 50% 50%,
            var(--radar-grid) 0deg 0.25deg, transparent 0.25deg 30deg);
    opacity: 0.55;
}

.radar-rim {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    border: 1px solid var(--radar-grid);
    opacity: 0.9;
}

/* The sweep: a cone of light with a bright leading edge. */
.radar-sweep {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: conic-gradient(
        from 0deg at 50% 50%,
        rgba(59, 232, 220, 0.42) 0deg,
        rgba(59, 232, 220, 0.10) 14deg,
        rgba(59, 232, 220, 0.03) 40deg,
        transparent 60deg,
        transparent 360deg
    );
    transform: rotate(0deg);
    animation: radar-spin var(--sweep-period, 4s) linear infinite;
    animation-delay: var(--sweep-delay, 0s);
}

.radar-sweep::after {
    content: "";
    position: absolute;
    left: 50%;
    top: 0;
    width: 1.5px;
    height: 50%;
    background: linear-gradient(to bottom, transparent, var(--accent));
    box-shadow: 0 0 12px var(--accent);
    transform-origin: bottom center;
}

@keyframes radar-spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
}

.radar-center {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 5px;
    height: 5px;
    margin: -2.5px 0 0 -2.5px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 10px var(--accent);
}

.radar-cross {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 14px;
    height: 14px;
    margin: -7px 0 0 -7px;
    opacity: 0.35;
    background:
        linear-gradient(var(--accent), var(--accent)) center/100% 1px no-repeat,
        linear-gradient(var(--accent), var(--accent)) center/1px 100% no-repeat;
}

/*
 * A blip is two nested elements. The outer one carries the age fade as a fixed
 * opacity; the inner one animates. Splitting them is what lets the two effects
 * multiply, since a single element cannot hold both a static and an animated
 * opacity.
 */
.blip {
    position: absolute;
    width: 0;
    height: 0;
}

.blip-dot {
    position: absolute;
    left: 0;
    top: 0;
    width: var(--size, 8px);
    height: var(--size, 8px);
    margin-left: calc(var(--size, 8px) / -2);
    margin-top: calc(var(--size, 8px) / -2);
    border-radius: 50%;
    background: var(--c);
    box-shadow: 0 0 10px var(--c), 0 0 22px -4px var(--c);
    animation: blip-pass var(--sweep-period, 4s) linear infinite;
    animation-delay: var(--blip-delay, 0s);
}

/*
 * The flash is timed so it lands as the sweep crosses the blip. The delay for
 * each blip is derived from its bearing, so this stays in step with the sweep
 * without any script.
 */
@keyframes blip-pass {
    0%   { opacity: 1;    transform: scale(1.6); }
    10%  { opacity: 0.95; transform: scale(1); }
    100% { opacity: 0.32; transform: scale(1); }
}

/* Expanding ring on fresh high-severity contacts. */
.blip-wave {
    position: absolute;
    left: 0;
    top: 0;
    width: 8px;
    height: 8px;
    margin: -4px 0 0 -4px;
    border-radius: 50%;
    border: 1px solid var(--c);
    animation: blip-wave 2s ease-out infinite;
}

@keyframes blip-wave {
    0%   { transform: scale(0.6); opacity: 0.6; }
    100% { transform: scale(5); opacity: 0; }
}

.blip-label {
    position: absolute;
    left: 10px;
    top: -6px;
    font-family: var(--font-mono);
    font-size: 8.5px;
    color: var(--text);
    white-space: nowrap;
    opacity: 0.85;
}

.radar-bearing {
    position: absolute;
    font-family: var(--font-mono);
    font-size: 8px;
    color: var(--text-muted);
    opacity: 0.75;
}

.radar-parked .radar-sweep { animation: none; opacity: 0.25; }
.radar-parked .radar-grid  { opacity: 0.3; }
.radar-parked .blip-dot    { animation: none; opacity: 0.5; }
.radar-parked .blip-wave   { animation: none; opacity: 0; }

.radar-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 9.5px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}

.radar-legend {
    display: flex;
    gap: 0.9rem;
    justify-content: center;
    margin-top: 0.5rem;
    font-family: var(--font-mono);
    font-size: 9.5px;
    letter-spacing: 0.06em;
}

.radar-legend span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.radar-legend i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 7px currentColor;
}

/* Respect the operating system reduced-motion setting. */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.001ms !important;
    }
    .blip-dot { opacity: 0.85 !important; }
}
</style>
"""


def html(markup: str) -> str:
    """
    Flatten markup before handing it to st.markdown.

    st.markdown does not dedent its input, and Markdown treats any line indented
    by four or more spaces as a code block. Markup written inline in a Python
    function is naturally indented to match the surrounding code, so passing it
    straight through renders the tags as literal text instead of as HTML.

    Stripping every line to column zero avoids that. Empty lines are dropped as
    well, because a blank line terminates an HTML block in CommonMark and would
    let the parser start reinterpreting what follows. Lines are joined with a
    newline rather than concatenated so that words in text nodes stay separated.

    Nothing here relies on <pre> or any other whitespace-sensitive element, so
    flattening is safe for every string in this application.
    """
    lines = (line.strip() for line in markup.splitlines())
    return "\n".join(line for line in lines if line)


def inject(st) -> None:
    """Inject the global stylesheet into the running Streamlit app."""
    st.markdown(CSS, unsafe_allow_html=True)


# Shared Plotly layout so every chart matches the shell.
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="JetBrains Mono, monospace", size=11, color=COLORS["text_secondary"]),
    margin=dict(l=10, r=10, t=30, b=10),
    xaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"], linecolor=COLORS["border"]),
    yaxis=dict(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"], linecolor=COLORS["border"]),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=COLORS["text_secondary"])),
    hoverlabel=dict(
        bgcolor=COLORS["surface_2"],
        bordercolor=COLORS["border_bright"],
        font=dict(family="JetBrains Mono, monospace", color=COLORS["text"]),
    ),
)
