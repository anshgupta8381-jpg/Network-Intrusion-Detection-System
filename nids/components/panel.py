"""
The live panel.

A complete, self-contained page written to the app's static folder and embedded
in Streamlit through an iframe whose src never changes. Streamlit renders that
iframe once and never touches it again, which is the entire reason this exists:
nothing here is re-rendered by Streamlit, so nothing here blinks.

The page polls /app/static/live.json for itself and draws what has changed since
the last poll: a new table row, a new radar contact, a nudged counter. The radar
animates on requestAnimationFrame, so the sweep runs at the browser's frame rate
regardless of how often the data refreshes.

Polling a file rather than holding a socket open is what makes this deployable.
Anything socket-based needs a second port, and a deployed host only exposes the
one Streamlit port. The cost is that flows show up up to a second late, which is
invisible in use; the blink was never about how the data arrived, it was about
Streamlit re-rendering the page.

The canvas radar from the first version of this dashboard is reused here almost
unchanged. The canvas was never the problem; being inside an iframe that
Streamlit reloaded on every rerun was.
"""

from ..theme import COLORS

_PANEL = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>NIDS live panel</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --base: __BASE__;
    --surface: __SURFACE__;
    --surface-2: __SURFACE2__;
    --border: __BORDER__;
    --border-bright: __BORDER_BRIGHT__;
    --text: __TEXT__;
    --text-secondary: __TEXT_SECONDARY__;
    --text-muted: __TEXT_MUTED__;
    --accent: __ACCENT__;
    --normal: __NORMAL__;
    --probe: __PROBE__;
    --attack: __ATTACK__;
    --critical: __CRITICAL__;
    --violet: __VIOLET__;
    --info: __INFO__;
    --font-display: 'Orbitron', sans-serif;
    --font-mono: 'JetBrains Mono', monospace;
    --font-body: 'Inter', sans-serif;
}

* { box-sizing: border-box; }

html, body {
    margin: 0;
    padding: 0;
    background: transparent;
    color: var(--text);
    font-family: var(--font-body);
    overflow: hidden;
}

#panel { padding: 2px; }

/* ---------- counters ---------- */

.kpis {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.7rem;
    margin-bottom: 0.9rem;
}

.kpi {
    position: relative;
    background: linear-gradient(155deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0) 45%), var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0.7rem 0.85rem;
    overflow: hidden;
    transition: border-color 0.25s ease, box-shadow 0.25s ease;
}

.kpi::before {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 2px;
    background: var(--c);
    box-shadow: 0 0 12px var(--c);
}

.kpi-label {
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--text-muted);
}

.kpi-value {
    font-family: var(--font-display);
    font-size: 1.55rem;
    font-weight: 900;
    color: var(--c);
    text-shadow: 0 0 18px color-mix(in srgb, var(--c) 45%, transparent);
    font-variant-numeric: tabular-nums;
    line-height: 1.2;
    margin-top: 0.15rem;
}

.kpi-delta {
    font-family: var(--font-mono);
    font-size: 0.62rem;
    color: var(--text-secondary);
}

/* A counter pulses when its number changes, so the eye is drawn to the change
   rather than to the whole panel being repainted. */
.kpi.bump { border-color: var(--c); box-shadow: 0 0 22px -8px var(--c); }

/* ---------- layout ---------- */

.grid {
    display: grid;
    grid-template-columns: 1.45fr 1fr;
    gap: 0.9rem;
}

.card {
    background: linear-gradient(160deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0) 42%), var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 0.8rem 0.9rem;
    overflow: hidden;
}

.card-title {
    font-family: var(--font-display);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.6rem;
}

.card-title::before {
    content: "";
    width: 3px; height: 12px;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
    border-radius: 2px;
}

/* ---------- table ---------- */

#table-wrap {
    height: 360px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--base);
}

table { width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 0.72rem; }

thead th {
    position: sticky; top: 0; z-index: 2;
    background: var(--surface-2);
    color: var(--text-muted);
    text-align: left;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-size: 0.58rem;
    padding: 0.5rem 0.6rem;
    border-bottom: 1px solid var(--border);
}

tbody td {
    padding: 0.42rem 0.6rem;
    border-bottom: 1px solid rgba(35,40,56,0.6);
    white-space: nowrap;
}

tbody tr:hover { background: rgba(59,232,220,0.06) !important; }
.mut { color: var(--text-muted); }

/* New rows slide in instead of appearing, which reads as movement rather than
   as the table being rebuilt. */
@keyframes row-in {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
}
tbody tr { animation: row-in 0.28s ease-out; }

/* ---------- radar ---------- */

#radar-box { display: flex; justify-content: center; perspective: 900px; }

#radar {
    display: block;
    border-radius: 50%;
    transform: rotateX(8deg);
    transition: transform 0.5s cubic-bezier(0.2,0.8,0.2,1);
    box-shadow:
        0 0 0 1px rgba(59,232,220,0.22),
        0 0 60px -10px rgba(59,232,220,0.35),
        0 40px 70px -30px rgba(0,0,0,1),
        inset 0 0 60px rgba(0,0,0,0.85);
    background: radial-gradient(circle at 50% 45%, #071614 0%, #04070B 62%, #020406 100%);
}

#radar-box:hover #radar { transform: rotateX(0deg) scale(1.02); }

.radar-meta {
    display: flex;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: 0.58rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.3rem;
}

.legend {
    display: flex;
    gap: 0.8rem;
    justify-content: center;
    margin-top: 0.5rem;
    font-family: var(--font-mono);
    font-size: 0.58rem;
}

.legend span { display: inline-flex; align-items: center; gap: 4px; }
.legend i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 6px currentColor; }

/* ---------- charts ---------- */

.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 0.9rem; margin-top: 0.9rem; }

/* ---------- alert bar ---------- */

#alert-bar {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border: 1px solid rgba(255,92,108,0.5);
    border-left: 3px solid var(--attack);
    background: linear-gradient(90deg, rgba(255,92,108,0.16), rgba(255,92,108,0.03));
    border-radius: 10px;
    padding: 0.6rem 0.9rem;
    margin-top: 0.9rem;
    font-family: var(--font-mono);
    font-size: 0.76rem;
    font-weight: 700;
    color: #FF8792;
    animation: breathe 2.4s ease-in-out infinite;
}

@keyframes breathe {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255,92,108,0.24); }
    50%      { box-shadow: 0 0 26px -4px rgba(255,92,108,0.55); }
}

#conn {
    font-family: var(--font-mono);
    font-size: 0.58rem;
    letter-spacing: 0.1em;
    color: var(--text-muted);
    text-align: right;
    padding: 0.3rem 0.1rem 0 0;
}

::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--base); }
::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 6px; }

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
</head>
<body>
<div id="panel">

  <div class="kpis">
    <div class="kpi" style="--c:var(--accent);" id="k-total">
      <div class="kpi-label">Total flows</div>
      <div class="kpi-value" id="v-total">0</div>
      <div class="kpi-delta" id="d-total">streaming</div>
    </div>
    <div class="kpi" style="--c:var(--attack);" id="k-mal">
      <div class="kpi-label">Malicious</div>
      <div class="kpi-value" id="v-mal">0</div>
      <div class="kpi-delta" id="d-mal">0.0% of traffic</div>
    </div>
    <div class="kpi" style="--c:var(--normal);" id="k-norm">
      <div class="kpi-label">Normal</div>
      <div class="kpi-value" id="v-norm">0</div>
      <div class="kpi-delta">no action required</div>
    </div>
    <div class="kpi" style="--c:var(--probe);" id="k-alert">
      <div class="kpi-label">Active alerts</div>
      <div class="kpi-value" id="v-alert">0</div>
      <div class="kpi-delta" id="d-alert">conf &ge; 0.70</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Live traffic flows</div>
      <div id="table-wrap">
        <table>
          <thead><tr>
            <th>Time</th><th>Source</th><th>Destination</th>
            <th>Proto</th><th>Dur</th><th>Prediction</th>
            <th style="text-align:right;">Conf</th>
          </tr></thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Threat radar</div>
      <div class="radar-meta">
        <span id="contacts" style="color:var(--attack);font-weight:700;"></span>
        <span id="status" style="color:var(--text-muted);">CONNECTING</span>
      </div>
      <div id="radar-box"><canvas id="radar"></canvas></div>
      <div class="legend">
        <span style="color:var(--critical);"><i></i>CRITICAL</span>
        <span style="color:var(--attack);"><i></i>ATTACK</span>
        <span style="color:var(--probe);"><i></i>PROBE</span>
        <span style="color:var(--normal);"><i></i>NORMAL</span>
      </div>
    </div>
  </div>

  <div class="charts">
    <div class="card">
      <div class="card-title">Threats over time</div>
      <canvas id="spark" height="150"></canvas>
    </div>
    <div class="card">
      <div class="card-title">Attack distribution</div>
      <canvas id="donut" height="150"></canvas>
    </div>
  </div>

  <div id="alert-bar"><span id="alert-text"></span><span id="alert-sev" style="color:var(--text-secondary);font-weight:400;"></span></div>
  <div id="conn"></div>
</div>

<script>
// ---------------------------------------------------------------- config

const C = {
  normal:   getStyle('--normal'),
  probe:    getStyle('--probe'),
  attack:   getStyle('--attack'),
  critical: getStyle('--critical'),
  violet:   getStyle('--violet'),
  info:     getStyle('--info'),
  accent:   getStyle('--accent'),
  text:     getStyle('--text'),
  muted:    getStyle('--text-muted'),
  grid:     '#1B4A47',
  border:   getStyle('--border'),
};

function getStyle(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

const SEVERITY = {
  'BENIGN': 'normal', 'PortScan': 'probe', 'DoS': 'attack', 'DDoS': 'critical',
  'FTP-Patator': 'attack', 'SSH-Patator': 'attack', 'Web Attack': 'attack',
  'Bot': 'attack', 'Infiltration': 'critical',
};

const CLASS_COLOR = {
  'BENIGN': C.normal, 'PortScan': C.probe, 'DoS': C.attack, 'DDoS': C.critical,
  'FTP-Patator': C.violet, 'SSH-Patator': C.violet, 'Web Attack': C.attack,
  'Bot': C.info, 'Infiltration': C.critical,
};

const GLYPH = { normal: '\\u25CF', probe: '\\u25B2', attack: '\\u25C6', critical: '\\u2716' };

function sevOf(p) { return SEVERITY[p] || 'attack'; }
function colOf(p) { return CLASS_COLOR[p] || C.text; }
function sevColor(s) {
  return s === 'critical' ? C.critical : s === 'attack' ? C.attack
       : s === 'probe' ? C.probe : C.normal;
}

// Tunables pushed in from Streamlit via the query string, so changing them in
// the sidebar does not require re-rendering the panel.
const params    = new URLSearchParams(location.search);
let RETENTION   = parseFloat(params.get('retention')  || '45');
let SWEEP       = parseFloat(params.get('sweep')      || '4');
let SHOW_BENIGN = params.get('benign') === '1';
let THRESHOLD   = parseFloat(params.get('threshold')  || '0.7');

const MAX_ROWS  = 120;
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------------------------------------------------------------- state

const state = {
  total: 0, malicious: 0, normal: 0, alerts: 0,
  blips: [],
  classCounts: {},
  buckets: new Map(),   // 10s bucket -> threat count
  lastSeq: 0,
  perMin: [],
};

// ---------------------------------------------------------------- radar

const canvas = document.getElementById('radar');
const ctx = canvas.getContext('2d');
let SIZE = 0, cx = 0, cy = 0, R = 0;

function sizeRadar() {
  const box = document.getElementById('radar-box');
  const dpr = window.devicePixelRatio || 1;
  SIZE = Math.max(200, Math.min(box.clientWidth - 8, 380));
  canvas.width = SIZE * dpr;
  canvas.height = SIZE * dpr;
  canvas.style.width = SIZE + 'px';
  canvas.style.height = SIZE + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx = SIZE / 2; cy = SIZE / 2; R = SIZE / 2 - 10;
}
sizeRadar();
window.addEventListener('resize', sizeRadar);

// Stable bearing per source address, so the same attacker always returns to the
// same part of the scope. Any stable hash does; this is djb2.
function hashOf(s) {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h;
}

function bearingOf(src) { return (hashOf(src) % 3600) / 10; }

function rangeOf(src, conf) {
  const priv = /^(10\\.|192\\.168\\.|172\\.16\\.|127\\.)/.test(src);
  const jitter = (hashOf(src + 'r') % 100) / 100;
  const base = priv ? 0.18 + jitter * 0.28 : 0.52 + jitter * 0.34;
  return Math.min(0.96, base + conf * 0.08);
}

function drawGrid() {
  ctx.save();
  for (let i = 1; i <= 4; i++) {
    ctx.beginPath();
    ctx.arc(cx, cy, R * i / 4, 0, Math.PI * 2);
    ctx.strokeStyle = C.grid;
    ctx.globalAlpha = i === 4 ? 0.85 : 0.4;
    ctx.lineWidth = i === 4 ? 1.4 : 1;
    ctx.stroke();
  }
  ctx.globalAlpha = 0.28; ctx.lineWidth = 1;
  for (let a = 0; a < 360; a += 30) {
    const r = (a - 90) * Math.PI / 180;
    ctx.beginPath(); ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(r) * R, cy + Math.sin(r) * R);
    ctx.strokeStyle = C.grid; ctx.stroke();
  }
  ctx.globalAlpha = 0.5;
  for (let a = 0; a < 360; a += 5) {
    const r = (a - 90) * Math.PI / 180;
    const long = a % 30 === 0;
    const inner = R - (long ? 8 : 4);
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(r) * inner, cy + Math.sin(r) * inner);
    ctx.lineTo(cx + Math.cos(r) * R, cy + Math.sin(r) * R);
    ctx.strokeStyle = C.grid; ctx.lineWidth = long ? 1.3 : 0.7; ctx.stroke();
  }
  ctx.globalAlpha = 0.75;
  ctx.fillStyle = C.muted;
  ctx.font = '8px "JetBrains Mono", monospace';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (let a = 0; a < 360; a += 90) {
    const r = (a - 90) * Math.PI / 180;
    ctx.fillText(String(a).padStart(3, '0'), cx + Math.cos(r) * (R - 17), cy + Math.sin(r) * (R - 17));
  }
  ctx.globalAlpha = 0.9;
  ctx.beginPath(); ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
  ctx.fillStyle = C.accent; ctx.fill();
  ctx.globalAlpha = 0.35;
  ctx.beginPath();
  ctx.moveTo(cx - 7, cy); ctx.lineTo(cx + 7, cy);
  ctx.moveTo(cx, cy - 7); ctx.lineTo(cx, cy + 7);
  ctx.strokeStyle = C.accent; ctx.lineWidth = 1; ctx.stroke();
  ctx.restore();
}

function drawSweep(angle) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(angle);
  const trail = Math.PI / 3, steps = 30;
  for (let i = 0; i < steps; i++) {
    ctx.beginPath(); ctx.moveTo(0, 0);
    ctx.arc(0, 0, R, -trail * (i + 1) / steps, -trail * i / steps);
    ctx.closePath();
    ctx.fillStyle = C.accent;
    ctx.globalAlpha = 0.13 * Math.pow(1 - i / steps, 2.1);
    ctx.fill();
  }
  ctx.globalAlpha = 0.95;
  ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(R, 0);
  ctx.strokeStyle = C.accent; ctx.lineWidth = 1.6;
  ctx.shadowColor = C.accent; ctx.shadowBlur = 14;
  ctx.stroke();
  ctx.restore();
}

function behind(a, b) {
  let d = a - b;
  while (d < 0) d += Math.PI * 2;
  while (d >= Math.PI * 2) d -= Math.PI * 2;
  return d;
}

function drawBlips(sweepAngle, now) {
  for (const b of state.blips) {
    const age = (now - b.ts) / 1000;
    if (age > RETENTION) continue;

    const rad = (b.bearing - 90) * Math.PI / 180;
    const d = b.range * R;
    const x = cx + Math.cos(rad) * d;
    const y = cy + Math.sin(rad) * d;
    const color = sevColor(b.sev);
    const baseR = b.sev === 'critical' ? 4.6 : b.sev === 'attack' ? 3.9 : b.sev === 'probe' ? 3.1 : 2.4;
    const life = Math.max(0.12, 1 - age / RETENTION);

    let refresh = 0.45;
    if (!reduceMotion) {
      const bh = behind(sweepAngle, rad);
      refresh = bh < Math.PI / 2.2 ? Math.pow(1 - bh / (Math.PI / 2.2), 2.6) : 0;
    }
    const alpha = Math.min(1, life * (0.42 + refresh * 0.75));

    if ((b.sev === 'critical' || b.sev === 'attack') && age < 6 && !reduceMotion) {
      const w = (age % 2) / 2;
      ctx.beginPath(); ctx.arc(x, y, baseR + w * 22, 0, Math.PI * 2);
      ctx.strokeStyle = color; ctx.globalAlpha = (1 - w) * 0.5 * life;
      ctx.lineWidth = 1.4; ctx.stroke();
    }

    ctx.beginPath(); ctx.arc(x, y, baseR * 3.1, 0, Math.PI * 2);
    const halo = ctx.createRadialGradient(x, y, 0, x, y, baseR * 3.1);
    halo.addColorStop(0, color); halo.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = halo; ctx.globalAlpha = alpha * 0.34; ctx.fill();

    ctx.beginPath(); ctx.arc(x, y, baseR, 0, Math.PI * 2);
    ctx.fillStyle = color; ctx.globalAlpha = alpha;
    ctx.shadowColor = color; ctx.shadowBlur = 12; ctx.fill(); ctx.shadowBlur = 0;

    if (b.sev === 'critical' && alpha > 0.55) {
      const s = baseR + 5;
      ctx.strokeStyle = color; ctx.globalAlpha = alpha * 0.8; ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x-s, y-s+3); ctx.lineTo(x-s, y-s); ctx.lineTo(x-s+3, y-s);
      ctx.moveTo(x+s-3, y-s); ctx.lineTo(x+s, y-s); ctx.lineTo(x+s, y-s+3);
      ctx.moveTo(x+s, y+s-3); ctx.lineTo(x+s, y+s); ctx.lineTo(x+s-3, y+s);
      ctx.moveTo(x-s+3, y+s); ctx.lineTo(x-s, y+s); ctx.lineTo(x-s, y+s-3);
      ctx.stroke();
      ctx.font = '8px "JetBrains Mono", monospace';
      ctx.fillStyle = C.text; ctx.globalAlpha = alpha * 0.85;
      ctx.textAlign = 'left';
      ctx.fillText(b.src, x + s + 4, y);
    }
  }
  ctx.globalAlpha = 1;
}

const T0 = Date.now() / 1000;

function frame() {
  const now = Date.now();
  ctx.clearRect(0, 0, SIZE, SIZE);
  drawGrid();
  const sweepAngle = reduceMotion ? -Math.PI / 2
      : ((now / 1000 - T0) % SWEEP) / SWEEP * Math.PI * 2 - Math.PI / 2;
  if (!reduceMotion) drawSweep(sweepAngle);
  drawBlips(sweepAngle, now);

  // Drop contacts that have aged out, so the array does not grow forever.
  if (state.blips.length > 400) {
    state.blips = state.blips.filter(b => (now - b.ts) / 1000 <= RETENTION).slice(-300);
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ---------------------------------------------------------------- charts

function drawSpark() {
  const cv = document.getElementById('spark');
  const c2 = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = cv.parentElement.clientWidth - 30, h = 130;
  cv.width = w * dpr; cv.height = h * dpr;
  cv.style.width = w + 'px'; cv.style.height = h + 'px';
  c2.setTransform(dpr, 0, 0, dpr, 0, 0);
  c2.clearRect(0, 0, w, h);

  const nowB = Math.floor(Date.now() / 10000);
  const pts = [];
  for (let i = 29; i >= 0; i--) pts.push(state.buckets.get(nowB - i) || 0);
  const max = Math.max(1, ...pts);

  c2.strokeStyle = C.border; c2.lineWidth = 1;
  c2.beginPath(); c2.moveTo(0, h - 1); c2.lineTo(w, h - 1); c2.stroke();

  c2.beginPath();
  pts.forEach((v, i) => {
    const x = (i / (pts.length - 1)) * w;
    const y = h - 6 - (v / max) * (h - 20);
    i ? c2.lineTo(x, y) : c2.moveTo(x, y);
  });
  c2.strokeStyle = C.attack; c2.lineWidth = 2; c2.stroke();
  c2.lineTo(w, h); c2.lineTo(0, h); c2.closePath();
  c2.fillStyle = 'rgba(255,92,108,0.14)'; c2.fill();

  c2.fillStyle = C.muted; c2.font = '9px "JetBrains Mono", monospace';
  c2.textAlign = 'left'; c2.fillText('peak ' + max, 2, 10);
  c2.textAlign = 'right'; c2.fillText('last 5 min', w - 2, 10);
}

function drawDonut() {
  const cv = document.getElementById('donut');
  const c2 = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const w = cv.parentElement.clientWidth - 30, h = 130;
  cv.width = w * dpr; cv.height = h * dpr;
  cv.style.width = w + 'px'; cv.style.height = h + 'px';
  c2.setTransform(dpr, 0, 0, dpr, 0, 0);
  c2.clearRect(0, 0, w, h);

  const entries = Object.entries(state.classCounts).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, e) => s + e[1], 0);
  const dcx = 62, dcy = h / 2, outer = 48, inner = 30;

  if (!total) {
    c2.fillStyle = C.muted; c2.font = '10px "JetBrains Mono", monospace';
    c2.textAlign = 'center'; c2.fillText('no attacks yet', w / 2, h / 2);
    return;
  }

  let a0 = -Math.PI / 2;
  for (const [label, count] of entries) {
    const a1 = a0 + (count / total) * Math.PI * 2;
    c2.beginPath();
    c2.arc(dcx, dcy, outer, a0, a1);
    c2.arc(dcx, dcy, inner, a1, a0, true);
    c2.closePath();
    c2.fillStyle = colOf(label); c2.fill();
    c2.strokeStyle = getStyle('--base'); c2.lineWidth = 2; c2.stroke();
    a0 = a1;
  }

  c2.fillStyle = C.text;
  c2.font = '900 15px Orbitron, sans-serif';
  c2.textAlign = 'center'; c2.textBaseline = 'middle';
  c2.fillText(String(total), dcx, dcy - 4);
  c2.fillStyle = C.muted; c2.font = '8px "JetBrains Mono", monospace';
  c2.fillText('THREATS', dcx, dcy + 10);

  let ly = 14;
  c2.textAlign = 'left'; c2.textBaseline = 'middle';
  for (const [label, count] of entries.slice(0, 7)) {
    c2.fillStyle = colOf(label);
    c2.fillRect(124, ly - 3, 7, 7);
    c2.fillStyle = C.text;
    c2.font = '9px "JetBrains Mono", monospace';
    c2.fillText(label + '  ' + count, 136, ly);
    ly += 15;
  }
}

// ---------------------------------------------------------------- table

const rowsEl = document.getElementById('rows');

function addRow(f) {
  const sev = sevOf(f.pred);
  const color = colOf(f.pred);
  const bg = sev === 'critical' ? 'rgba(255,51,85,0.12)'
           : sev === 'attack'   ? 'rgba(255,92,108,0.09)'
           : sev === 'probe'    ? 'rgba(255,180,84,0.07)' : 'transparent';

  const t = new Date(f.ts * 1000).toLocaleTimeString('en-GB');
  const tr = document.createElement('tr');
  tr.style.background = bg;
  tr.innerHTML =
    '<td class="mut">' + t + '</td>' +
    '<td>' + f.src + '<span class="mut">:' + f.sport + '</span></td>' +
    '<td>' + f.dst + '<span class="mut">:' + f.dport + '</span></td>' +
    '<td class="mut">' + f.proto + '</td>' +
    '<td class="mut">' + f.dur.toFixed(2) + 's</td>' +
    '<td style="color:' + color + ';font-weight:700;">' + GLYPH[sev] + ' ' + f.pred + '</td>' +
    '<td style="text-align:right;">' + f.conf.toFixed(2) + '</td>';

  rowsEl.insertBefore(tr, rowsEl.firstChild);
  while (rowsEl.children.length > MAX_ROWS) rowsEl.removeChild(rowsEl.lastChild);
}

// ---------------------------------------------------------------- counters

function bump(id) {
  const el = document.getElementById(id);
  el.classList.add('bump');
  setTimeout(() => el.classList.remove('bump'), 380);
}

function paintCounters() {
  document.getElementById('v-total').textContent = state.total.toLocaleString();
  document.getElementById('v-mal').textContent   = state.malicious.toLocaleString();
  document.getElementById('v-norm').textContent  = state.normal.toLocaleString();
  document.getElementById('v-alert').textContent = state.alerts.toLocaleString();
  const rate = state.total ? (state.malicious / state.total * 100) : 0;
  document.getElementById('d-mal').textContent = rate.toFixed(1) + '% of traffic';
  document.getElementById('d-alert').textContent = 'conf \\u2265 ' + THRESHOLD.toFixed(2);

  const threats = state.blips.filter(b => b.sev === 'attack' || b.sev === 'critical').length;
  document.getElementById('contacts').textContent = threats ? threats + ' CONTACTS' : '';
}

function showAlert(f) {
  const bar = document.getElementById('alert-bar');
  const sev = sevOf(f.pred);
  document.getElementById('alert-text').innerHTML =
    GLYPH[sev] + ' ALERT &nbsp; ' + f.pred + ' from ' + f.src + ' &rarr; ' + f.dst + ':' + f.dport +
    ' &nbsp;|&nbsp; confidence ' + f.conf.toFixed(2) +
    ' &nbsp;|&nbsp; ' + new Date(f.ts * 1000).toLocaleTimeString('en-GB');
  document.getElementById('alert-sev').textContent = sev.toUpperCase();
  bar.style.display = 'flex';
}

// ---------------------------------------------------------------- ingest

function ingest(flows, isSnapshot) {
  let latestAlert = null;

  for (const f of flows) {
    if (f.seq <= state.lastSeq) continue;
    state.lastSeq = f.seq;

    state.total++;
    const sev = sevOf(f.pred);
    const malicious = f.pred !== 'BENIGN';

    if (malicious) {
      state.malicious++;
      state.classCounts[f.pred] = (state.classCounts[f.pred] || 0) + 1;
      const b = Math.floor(f.ts * 1000 / 10000);
      state.buckets.set(b, (state.buckets.get(b) || 0) + 1);
      if (f.conf >= THRESHOLD) { state.alerts++; latestAlert = f; }
    } else {
      state.normal++;
    }

    if (SHOW_BENIGN || malicious) {
      state.blips.push({
        bearing: bearingOf(f.src), range: rangeOf(f.src, f.conf),
        sev: sev, src: f.src, ts: f.ts * 1000,
      });
    }

    if (!isSnapshot) addRow(f);
  }

  if (isSnapshot) {
    for (const f of flows.slice(-MAX_ROWS)) addRow(f);
  }

  paintCounters();
  drawSpark();
  drawDonut();
  if (latestAlert) showAlert(latestAlert);
}

// ---------------------------------------------------------------- polling

const statusEl = document.getElementById('status');
const connEl = document.getElementById('conn');

function setStatus(text, color) {
  statusEl.textContent = text;
  statusEl.style.color = color;
}

// live.json sits next to this page, so a relative URL works both locally and on
// a deployed host without knowing either address.
const LIVE_URL = 'live.json';
const POLL_MS = 800;

let received = 0;
let firstLoad = true;
let misses = 0;

async function poll() {
  try {
    // Cache buster. Streamlit serves the file straight from disk, but a browser
    // or a proxy in front of it would happily hand back the previous copy.
    const r = await fetch(LIVE_URL + '?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const snap = await r.json();

    misses = 0;

    // Only flows newer than the last one drawn. ingest() checks seq as well, so
    // a repeated snapshot is harmless.
    const fresh = snap.flows.filter(f => f.seq > state.lastSeq);
    if (fresh.length) {
      received += fresh.length;
      ingest(fresh, firstLoad);
      firstLoad = false;
    } else if (firstLoad && snap.flows.length) {
      ingest(snap.flows, true);
      firstLoad = false;
    }

    if (typeof snap.threshold === 'number' && snap.threshold !== THRESHOLD) {
      THRESHOLD = snap.threshold;
      paintCounters();
    }

    if (snap.capturing) {
      setStatus('SCANNING', C.accent);
    } else {
      setStatus('STANDBY', C.muted);
    }

    connEl.textContent = 'live \\u00b7 ' + received.toLocaleString()
      + ' flows \\u00b7 ' + (snap.source || 'idle');

  } catch (err) {
    misses++;
    // One failed poll is nothing; several in a row means the app is gone.
    if (misses > 3) setStatus('DISCONNECTED', C.attack);
  }
}

poll();
setInterval(poll, POLL_MS);

window.addEventListener('resize', () => { drawSpark(); drawDonut(); });
paintCounters(); drawSpark(); drawDonut();
</script>
</body>
</html>
"""


def build() -> str:
    """Return the panel page with the theme colours substituted in."""
    return (
        _PANEL.replace("__BASE__", COLORS["base"])
        .replace("__SURFACE2__", COLORS["surface_2"])
        .replace("__SURFACE__", COLORS["surface"])
        .replace("__BORDER_BRIGHT__", COLORS["border_bright"])
        .replace("__BORDER__", COLORS["border"])
        .replace("__TEXT_SECONDARY__", COLORS["text_secondary"])
        .replace("__TEXT_MUTED__", COLORS["text_muted"])
        .replace("__TEXT__", COLORS["text"])
        .replace("__ACCENT__", COLORS["accent"])
        .replace("__NORMAL__", COLORS["normal"])
        .replace("__PROBE__", COLORS["probe"])
        .replace("__ATTACK__", COLORS["attack"])
        .replace("__CRITICAL__", COLORS["critical"])
        .replace("__VIOLET__", COLORS["violet"])
        .replace("__INFO__", COLORS["info"])
    )
