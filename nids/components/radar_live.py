"""
Self-animating radar component.

The CSS radar restarts its sweep on every rerun, because Streamlit replaces the
element and a fresh element begins its animation again. The negative
animation-delay trick cannot fix that: it only sets where a *new* element starts,
so with a new element each refresh the sweep still jumps.

This version sidesteps the problem entirely. The radar is a small HTML canvas
embedded with st.components.v1.html; inside it, requestAnimationFrame drives the
sweep at the browser's frame rate. Streamlit's reruns do not touch what is inside
the component, so the sweep never resets — it runs continuously regardless of how
often the surrounding page redraws.

Blips are passed in as data. When the page reruns and re-embeds the component
with new blips, the sweep keeps going; only the dots update. The sweep angle is
derived from Date.now(), so even a full re-embed lands it exactly where it should
be rather than at zero.
"""

import json
import time
from typing import Any, Dict, List

import streamlit.components.v1 as components

from ..theme import COLORS


def render(
    blips: List[Dict[str, Any]],
    height: int = 340,
    retention: float = 45.0,
    sweep_period: float = 4.0,
    scanning: bool = True,
    show_benign: bool = False,
) -> None:
    """Embed the self-animating radar. `blips` come from radar.build_blips."""
    if not show_benign:
        blips = [b for b in blips if b.get("severity") != "normal"]
    blips = [b for b in blips if b.get("age", 0) <= retention][-140:]

    payload = json.dumps(
        {
            "blips": blips,
            "retention": retention,
            "sweepPeriod": sweep_period,
            "scanning": scanning,
            "now": time.time(),
            "colors": {
                "accent": COLORS["accent"],
                "critical": COLORS["critical"],
                "attack": COLORS["attack"],
                "probe": COLORS["probe"],
                "normal": COLORS["normal"],
                "text": COLORS["text"],
                "muted": COLORS["text_muted"],
                "grid": "#1B4A47",
            },
        }
    )

    html = _TEMPLATE.replace("__PAYLOAD__", payload).replace("__H__", str(height))
    # A stable key would let Streamlit reuse the iframe across reruns, but
    # components.html does not take one. Instead the sweep clock is anchored to
    # DATA.now (server time), so even when the iframe is replaced on a rerun the
    # new one computes the sweep's absolute position and picks up exactly where
    # the old one was, rather than restarting at zero.
    components.html(html, height=height + 70)


_TEMPLATE = """
<div id="wrap" style="font-family:'JetBrains Mono',monospace;">
  <div style="display:flex;justify-content:space-between;font-size:11px;
              letter-spacing:0.14em;text-transform:uppercase;margin-bottom:4px;">
    <span id="contacts" style="font-weight:700;"></span>
    <span id="status"></span>
  </div>
  <div style="display:flex;justify-content:center;">
    <canvas id="radar" width="__H__" height="__H__"
            style="max-width:100%;border-radius:50%;"></canvas>
  </div>
  <div id="legend" style="display:flex;gap:14px;justify-content:center;
       margin-top:6px;font-size:10px;"></div>
</div>
<script>
const DATA = __PAYLOAD__;
const C = DATA.colors;
const cv = document.getElementById("radar");
const ctx = cv.getContext("2d");
const SIZE = cv.width, cx = SIZE/2, cy = SIZE/2, R = SIZE/2 - 10;
const SWEEP = DATA.sweepPeriod, RET = DATA.retention;

// Anchor the animation clock to the server time this payload was built, so the
// sweep angle is absolute rather than relative to when the component loaded.
const T0 = DATA.now - (performance.now()/1000);

// status + legend
document.getElementById("status").textContent = DATA.scanning ? "SCANNING" : "STANDBY";
document.getElementById("status").style.color = DATA.scanning ? C.accent : C.muted;
const threats = DATA.blips.filter(b => b.severity==="attack" || b.severity==="critical").length;
const cel = document.getElementById("contacts");
cel.textContent = threats ? threats + " CONTACTS" : "";
cel.style.color = C.attack;
document.getElementById("legend").innerHTML = [
  ["CRITICAL",C.critical],["ATTACK",C.attack],["PROBE",C.probe],["NORMAL",C.normal]
].map(([t,c]) => `<span style="color:${c};display:inline-flex;align-items:center;gap:4px;">
  <i style="width:6px;height:6px;border-radius:50%;background:${c};box-shadow:0 0 6px ${c};"></i>${t}</span>`).join("");

function sevColor(s){return s==="critical"?C.critical:s==="attack"?C.attack:s==="probe"?C.probe:C.normal;}

function drawGrid(){
  for(let i=1;i<=4;i++){
    ctx.beginPath();ctx.arc(cx,cy,R*i/4,0,Math.PI*2);
    ctx.strokeStyle=C.grid;ctx.globalAlpha=i===4?0.85:0.4;
    ctx.lineWidth=i===4?1.4:1;ctx.stroke();
  }
  ctx.globalAlpha=0.28;ctx.lineWidth=1;
  for(let a=0;a<360;a+=30){
    const r=(a-90)*Math.PI/180;
    ctx.beginPath();ctx.moveTo(cx,cy);
    ctx.lineTo(cx+Math.cos(r)*R,cy+Math.sin(r)*R);
    ctx.strokeStyle=C.grid;ctx.stroke();
  }
  ctx.globalAlpha=0.75;ctx.fillStyle=C.muted;
  ctx.font='8px monospace';ctx.textAlign='center';ctx.textBaseline='middle';
  for(let a=0;a<360;a+=90){
    const r=(a-90)*Math.PI/180;
    ctx.fillText(String(a).padStart(3,'0'),cx+Math.cos(r)*(R-16),cy+Math.sin(r)*(R-16));
  }
  ctx.globalAlpha=0.9;ctx.beginPath();ctx.arc(cx,cy,2.5,0,Math.PI*2);
  ctx.fillStyle=C.accent;ctx.fill();
}

function drawSweep(angle){
  ctx.save();ctx.translate(cx,cy);ctx.rotate(angle);
  const trail=Math.PI/3,steps=30;
  for(let i=0;i<steps;i++){
    ctx.beginPath();ctx.moveTo(0,0);
    ctx.arc(0,0,R,-trail*(i+1)/steps,-trail*i/steps);ctx.closePath();
    ctx.fillStyle=C.accent;ctx.globalAlpha=0.13*Math.pow(1-i/steps,2.1);ctx.fill();
  }
  ctx.globalAlpha=0.95;ctx.beginPath();ctx.moveTo(0,0);ctx.lineTo(R,0);
  ctx.strokeStyle=C.accent;ctx.lineWidth=1.6;
  ctx.shadowColor=C.accent;ctx.shadowBlur=14;ctx.stroke();ctx.restore();
}

function behind(a,b){let d=a-b;while(d<0)d+=Math.PI*2;while(d>=Math.PI*2)d-=Math.PI*2;return d;}

function drawBlips(sweepAngle,now){
  for(const b of DATA.blips){
    const age=(now-(b.ts!==undefined?b.ts:DATA.now));
    const ageEff=b.age!==undefined?b.age+(now-DATA.now):age;
    if(ageEff>RET)continue;
    const rad=(b.bearing-90)*Math.PI/180;
    const d=b.range*R;
    const x=cx+Math.cos(rad)*d,y=cy+Math.sin(rad)*d;
    const color=sevColor(b.severity);
    const baseR=b.severity==="critical"?4.6:b.severity==="attack"?3.9:b.severity==="probe"?3.1:2.4;
    const life=Math.max(0.12,1-ageEff/RET);
    const bh=behind(sweepAngle,rad);
    const refresh=bh<Math.PI/2.2?Math.pow(1-bh/(Math.PI/2.2),2.6):0;
    const alpha=Math.min(1,life*(0.42+refresh*0.75));
    if((b.severity==="critical"||b.severity==="attack")&&ageEff<6){
      const w=(ageEff%2)/2;
      ctx.beginPath();ctx.arc(x,y,baseR+w*22,0,Math.PI*2);
      ctx.strokeStyle=color;ctx.globalAlpha=(1-w)*0.5*life;ctx.lineWidth=1.4;ctx.stroke();
    }
    ctx.beginPath();ctx.arc(x,y,baseR*3.1,0,Math.PI*2);
    const g=ctx.createRadialGradient(x,y,0,x,y,baseR*3.1);
    g.addColorStop(0,color);g.addColorStop(1,'rgba(0,0,0,0)');
    ctx.fillStyle=g;ctx.globalAlpha=alpha*0.34;ctx.fill();
    ctx.beginPath();ctx.arc(x,y,baseR,0,Math.PI*2);
    ctx.fillStyle=color;ctx.globalAlpha=alpha;
    ctx.shadowColor=color;ctx.shadowBlur=12;ctx.fill();ctx.shadowBlur=0;
  }
  ctx.globalAlpha=1;
}

function frame(){
  const now=T0+performance.now()/1000;
  ctx.clearRect(0,0,SIZE,SIZE);
  drawGrid();
  const sweepAngle=DATA.scanning?((now%SWEEP)/SWEEP*Math.PI*2-Math.PI/2):-Math.PI/2;
  if(DATA.scanning)drawSweep(sweepAngle);
  drawBlips(sweepAngle,now);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
"""
