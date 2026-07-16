# NIDS - Network Intrusion Detection Dashboard

A Streamlit application layer for a machine learning based network intrusion
detection system. It sits on top of a classifier trained offline on CICIDS2017,
supports live capture and batch CSV analysis, and presents detections in a dark
security-operations interface with a live threat radar.

This is the application described in the design document. It does not train
anything. It loads an exported model and serves it.

**Windows setup: see [SETUP_WINDOWS.md](SETUP_WINDOWS.md).**
**Deploying: see [DEPLOY.md](DEPLOY.md).**

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run nids/app.py
```

Run it from the repository root, not from inside `nids/`.

The dashboard runs immediately in **simulation mode** with generated traffic, so
the whole interface can be built and reviewed before the model exists. Drop the
trained model into `models/` and it switches to real inference with no code
change.

---

## What works right now

| Feature | Status |
|---|---|
| All seven screens | Working |
| Streaming live panel, no reruns and no blink | Working |
| Threat radar with live sweep and blips | Working |
| Simulated traffic source | Working |
| Background capture and scoring threads | Working |
| CSV upload, schema validation, batch scoring | Working |
| SQLite detection log, filters, CSV export | Working |
| Alert feed and thresholds | Working |
| nfstream live capture | Code complete, needs Npcap on your machine |
| PCAP replay | Code complete, needs nfstream |
| Real predictions | Needs `models/model.joblib` |
| Model Performance page | Needs `models/metrics.json` |

---

## Architecture

Five layers, data moving upward, exactly as the design document specifies.

```
  Presentation   views/ + components/     Streamlit, radar, charts, tables
  Inference      core/engine.py           loads model + scaler, predicts
  Preprocessing  core/schema.py           column alignment, cleaning, scaling
  Feature        core/capture.py          nfstream flow statistics -> CICIDS names
  Capture        core/capture.py          nfstream / PCAP / simulator
```

Training is a separate offline pipeline that produces `models/`. The app only
loads and serves.

### The two input paths converge

Live capture and CSV upload produce the same record structure, align to the same
feature order, pass through the same scaler and the same model. That is why the
results table, the alert logic, the radar and the exports do not need to know
where a row came from.

### Real-time approach, and why the live panel is not a Streamlit page

Streamlit renders from the server: every rerun replaces the elements on the
page. That is fine for a form and wrong for a live console, because replacing
elements is exactly what the eye reads as a blink. There is no setting that
makes it silent, and fragments narrow the scope of a rerun without changing the
mechanism.

So the live panel does not use Streamlit's render path at all:

    capture thread -> pipeline thread (scores) -> static/live.json -> browser
                                              -> store -> SQLite

`core/livefile.py` writes two files into `nids/static/`, which Streamlit serves
on its own port at `/app/static/`: the panel page, and a `live.json` snapshot the
pipeline rewrites twice a second. Live Monitoring embeds the panel in an iframe
whose src never changes, so Streamlit renders it once and then leaves it alone.
The panel polls its own snapshot and appends each new flow itself. Nothing
reruns, nothing is replaced, nothing blinks, and the radar animates at the
browser's frame rate rather than stepping once per refresh.

The snapshot is written to a temp file and renamed, so a poll landing mid-write
reads the old file or the new one, never half of each.

An earlier version pushed over Server-Sent Events from a server on its own port.
That was better locally, instant instead of up to a second late, and undeployable:
a browser resolves `127.0.0.1` to the viewer's own machine, and hosts expose only
the one Streamlit port. Polling one file on the app's own origin works in both
places, and the second of latency is invisible. The blink was never about how the
data arrived; it was about Streamlit re-rendering the page.

This is close to how real consoles work: a long-lived page, a server that
pushes, and a client that mutates only what changed.

Two consequences worth knowing:

  * Scoring moved out of the render path onto a background thread, so detections
    are logged continuously, including while you are on another page. In the old
    design, scoring only happened when Live Monitoring happened to be rerunning,
    which quietly left holes in the log.
  * Scored flows live in `core/store.py` at process level rather than in session
    state, because a background thread cannot touch session state.

The capture queue is bounded on purpose: if the pipeline falls behind, dropping
the oldest flows beats growing memory without limit, and the drop count is shown
on the live page rather than hidden.

---

## Project structure

```
nids/
├── app.py                  entry point and sidebar navigation
├── theme.py                colour tokens and the global stylesheet
├── requirements.txt
├── run.bat                 Windows launcher
├── SETUP_WINDOWS.md        manual setup steps
│
├── core/
│   ├── schema.py           feature contract between training and serving
│   ├── engine.py           model loading and inference, simulation fallback
│   ├── capture.py          capture sources and the capture thread
│   ├── pipeline.py         scoring thread: drain, predict, store, publish
│   ├── livefile.py         writes static/panel.html and static/live.json
│   ├── store.py            process-level flow buffer and alert feed
│   ├── simulator.py        synthetic traffic generator
│   ├── db.py               SQLite detection log
│   └── state.py            cached resources and shared accessors
│
├── components/
│   ├── panel.py            the streaming live panel (canvas radar, table, charts)
│   ├── radar.py            in-page CSS radar, used on Overview
│   ├── cards.py            KPI cards, tables, alert feed
│   └── charts.py           themed Plotly charts
│
├── views/                  one module per screen
├── models/                 drop model.joblib etc. here
└── data/                   SQLite log and PCAP files
```

---

## Design notes

### Why black instead of the blue in the design document

The design document specifies dark slate with a teal accent. The palette here
keeps the teal accent and the green/amber/red status scheme, but the base is
near-black (`#05060A`) with layered surfaces above it.

The base is **not** pure `#000000`, and body text is **not** pure `#FFFFFF`. Pure
white on pure black measures 21:1 and causes halation, a glowing blur around
letterforms, for readers with astigmatism. Off-white `#E6EAF2` on the card
surface measures roughly 15:1: far above the WCAG AA minimum of 4.5:1 for normal
text, without the glare. Secondary text sits at about 7:1 and muted labels at
about 4.6:1.

Status colours are desaturated for the same reason. Fully saturated red and green
read badly on dark surfaces even when the measured ratio passes, so the palette
uses `#FF5C6C`, `#3FDD9B` and `#FFB454`.

Every status also carries a **text label and a shape glyph**, never colour alone
(WCAG 1.4.1), and all animation respects the OS reduced-motion setting.

### The radar

There are two, because the two pages have different needs.

Live Monitoring uses the canvas radar inside the streaming panel. It never
reruns, so it simply animates on requestAnimationFrame.

Overview uses an in-page CSS radar (`components/radar.py`). That page does not
auto-refresh, but it does re-render when the user interacts, and a fresh element
would restart its animation from zero. A negative `animation-delay` computed from
the server clock fixes that: an element rendered with `animation-delay: -1.2s`
starts 1.2 seconds into its cycle, so the sweep carries on from where it was.
Each blip's flash is delayed by its own bearing, so it lights up as the sweep
crosses it, with no JavaScript involved.

- **Bearing** is a hash of the source address, so the same attacker returns to
  the same part of the scope every time. This is what makes it readable rather
  than decorative.
- **Range** puts private addresses near the centre and remote addresses near the
  rim, nudged outward by model confidence.
- **Blips** brighten as the sweep passes over them, fade as they age out of the
  retention window, and draw a shockwave ring for fresh high-severity contacts.
- **Benign traffic is hidden by default.** Benign outnumbers attacks by roughly
  forty to one; drawing it buries the threats. Toggle it on in Settings.

### Simulation mode is labelled, not hidden

When there is no model, the sidebar says "Simulation mode" and the exported
report says so too. A dashboard that looks live while running on generated data
is worse than one that admits it, and it is the kind of thing an examiner will
ask about directly.

---

## Configuration

Everything is on the **Settings / About** page: refresh interval, alert
confidence threshold, radar retention and sweep period, simulated flow rate and
attack bias, model reload, and a diagnostics panel that reports exactly which
dependencies are present.

---

## Ethics

Only capture traffic on networks you own or administrate.
