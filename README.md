# NIDS - Network Intrusion Detection Dashboard

A Streamlit application for a machine-learning network intrusion detection
system. It loads a classifier trained on CICIDS2017 and presents detections in a
dark security-operations interface with a live threat radar. It reads traffic
three ways: generated simulation traffic for demos, real live capture from your
own machine, and uploaded flow CSVs or packet captures.

The model is trained separately (see [Training the model](#training-the-model))
and dropped into `nids/models/`. Until then the app runs in simulation mode, so
the whole interface works before the model exists.

> **Quick links:** [Windows setup](SETUP_WINDOWS.md) &nbsp;·&nbsp; [Sample CSVs to try](https://drive.google.com/drive/folders/1ayxVxopzhZoTCF7kOJRQj1sQcG0SNL8o?usp=drive_link) &nbsp;·&nbsp; [Training notebook](NIDS_Training_CICIDS2017.ipynb) &nbsp;·&nbsp; [License](LICENSE)

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run nids/app.py
```

Run it from the repository root, not from inside `nids/`.

With no model present the dashboard runs in **simulation mode** with generated
attack traffic. Drop the five trained model files into `nids/models/` and, via
Settings, reload — every prediction becomes real with no code change.

---

## What works

| Feature | Status |
|---|---|
| All seven screens | Working |
| Threat radar, continuous sweep, no reset on refresh | Working |
| Simulation traffic with generated attacks | Working |
| Live capture from a real interface (nfstream + Npcap) | Working, Windows + Administrator |
| Packet-capture upload (.pcap / .pcapng), auto-converted to flows | Working, needs nfstream |
| Flow CSV upload, schema validation, batch scoring | Working |
| Trained RandomForest model, real predictions | Working with model in `nids/models/` |
| SHAP explainability export | Produced by the training notebook |
| Model Performance page: accuracy, confusion matrix, ROC, per-class | Working with model |
| SQLite detection log, filters, CSV export | Working |
| Alert feed and thresholds | Working |

The trained model reaches about **94.7% accuracy** on held-out CICIDS2017 data.
Per-class recall is strong for the well-represented attacks (DDoS, PortScan, DoS,
FTP-Patator) and weaker for the rare ones (Bot, SSH-Patator, Web Attack,
Infiltration), which is expected given the class imbalance and is reported
honestly on the Model Performance page rather than hidden behind the headline
number.

---

## Training the model

Training runs separately in Google Colab, not in this app. The notebook
`NIDS_Training_CICIDS2017.ipynb` downloads CICIDS2017, maps its columns onto the
twenty features the app uses, handles the class imbalance, trains and compares
XGBoost / RandomForest / DecisionTree, computes SHAP explanations, and exports
the five files the app loads:

```
model.joblib  scaler.joblib  label_encoder.joblib
feature_columns.json  metrics.json
```

Put those five in `nids/models/`, then Settings -> Reload model. The sidebar
changes from "Simulation mode" to the model name and predictions become real.

**Version note.** Train and run with the same scikit-learn version. A model
pickled under one version and loaded under another raises an
`InconsistentVersionWarning` and can misbehave; `requirements.txt` pins the
version so a fresh install matches.

---

## The three ways traffic gets in

- **Simulation** generates realistic attack traffic and needs no drivers. Best
  for a demo, because the radar and the counters are always full. Simulated
  flows keep their generated labels rather than being scored, since their
  feature values only approximate real attacks; scoring them would empty the
  radar for no gain.
- **Live capture** reads real traffic from your own interface through nfstream.
  It shows genuine flows, but what it reads depends entirely on where it runs.
  On a **home Wi-Fi** it will read almost everything as BENIGN, because nothing
  is actually attacking you — that is correct behaviour, not a bug. On a network
  that is **actually under attack** — an organisation being port-scanned, hit
  with a DoS, or probed — the same live capture would surface those attacks,
  because now the malicious flows are really passing through. In other words the
  tool only ever sees traffic through the machine it runs on, so a quiet network
  looks quiet and a targeted one does not.
- **Upload** takes either a flow CSV or a raw packet capture. This is the easiest
  way to analyse traffic you captured elsewhere: open **Wireshark**, capture for
  a while, and **File -> Save As** a `.pcap` or `.pcapng` (do *not* use
  Wireshark's "Export as CSV", which lists packets, not the flow features the
  model needs). Upload that file on the Upload & Analyze page and the app
  converts it into flow features automatically with nfstream — nothing to
  prepare by hand. As with live capture, attacks only show up if the capture
  actually contains attack traffic.

### Sample data to try

To see real detections on the **Upload & Analyze** page without capturing
anything yourself, use the CICIDS2017 flow CSVs here:

**[Sample CICIDS2017 CSVs (Google Drive)](https://drive.google.com/drive/folders/1ayxVxopzhZoTCF7kOJRQj1sQcG0SNL8o?usp=drive_link)**

Download one — for example the Friday PortScan or DDoS file — and upload it on
the Upload & Analyze page. Because these are the real attack flows the model was
trained on, it detects the attacks in them, unlike ordinary live traffic. The
files are large; the app extracts the twenty features it needs and ignores the
rest, so there is nothing to prepare.

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

### Real-time approach

    capture thread -> pipeline thread (scores) -> store -> SQLite
                                               -> Live Monitoring reads the store

Scoring runs on a background thread rather than in the render path, so
detections keep being logged while you are on another page or with no browser
open. In the original design, scoring only happened when the Live Monitoring
page happened to be rerunning, which quietly left holes in the log. Scored flows
live in `core/store.py` at process level, because a background thread cannot
touch session state.

The live page redraws through `st.fragment(run_every=...)`, so only the panel
reruns and the controls, header and sidebar are left alone. The counters, table
and charts update on that timer.

The radar is the exception, and deliberately so. It is a self-contained HTML
canvas (`components/radar_live.py`) that animates its sweep on
requestAnimationFrame *inside* the component, independent of Streamlit's reruns.
An earlier CSS radar restarted its sweep on every rerun, because Streamlit
replaced the element and a fresh element began its animation again; the sweep
visibly jumped. The canvas version anchors its sweep angle to the server clock,
so even when the page reruns around it the sweep runs continuously and never
resets. The charts are inline SVG rather than Plotly, which would rebuild its
JavaScript on every render.

The capture queue is bounded on purpose: if the pipeline falls behind, dropping
the oldest flows beats growing memory without limit, and the drop count is shown
on the live page rather than hidden.

### Live capture on Windows

Live capture goes through nfstream, which sits on the Npcap driver, and three
Windows-specific details matter, all handled in `core/capture.py`:

- nfstream needs the Npcap **device path** (`\Device\NPF_{GUID}`), not the
  friendly name "Wi-Fi". The friendly name is shown in the dropdown and resolved
  to the device path before capture.
- nfstream is run with **one meter** (`n_meters=1`). Its default spawns worker
  processes that need an `if __name__ == '__main__'` guard, which does not exist
  inside a Streamlit thread, so without this capture silently produces nothing.
- Timeouts are **short** (idle 2s, active 10s) so flows expire and reach the
  screen promptly, rather than being held for up to a minute as the library
  defaults would.

Capture also needs an **Administrator** terminal; Npcap will not open an
interface otherwise.

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
│   ├── store.py            process-level flow buffer and alert feed
│   ├── simulator.py        synthetic traffic generator
│   ├── db.py               SQLite detection log
│   └── state.py            cached resources and shared accessors
│
├── components/
│   ├── radar.py            in-page CSS radar (Overview)
│   ├── radar_live.py       self-animating canvas radar (Live Monitoring)
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

There are two radars, for two different situations.

**Overview** uses an in-page CSS radar (`components/radar.py`). No JavaScript:
the sweep and per-blip flash are CSS animations that survive the occasional
rerun through a negative `animation-delay` computed from the server clock, so a
fresh element picks the sweep up where the previous one left off. This page does
not refresh on a timer, so that is enough.

**Live Monitoring** uses a canvas radar (`components/radar_live.py`) because that
page *does* refresh on a timer, and the CSS trick is not enough there: every
rerun replaces the element, and the sweep visibly jumps. The canvas animates on
requestAnimationFrame inside the component, independent of Streamlit, and anchors
its angle to the server clock, so it runs continuously and never resets on
refresh.

Both position blips the same way:

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

There is a second, related point worth being explicit about. **Even when a model
is loaded, simulated flows are not scored by it** — they keep the label the
simulator generated. This is deliberate: the simulator's feature values only sit
in a plausible range for each class, not the true CICIDS distribution, so a
trained model would (correctly) read most of them as benign and the demo radar
would empty out. So simulation demonstrates the dashboard — real-time flow
handling, the radar, alerting, the charts — while the **actual model inference
happens on real inputs**: uploaded CSVs, uploaded packet captures, and live
capture. If you want to show the model detecting an attack, upload a CICIDS
attack CSV; that is real inference on real attack flows.

This is also why live capture on ordinary traffic reads benign, and why a live
`nmap` scan is usually not flagged: the model generalises poorly from the
CICIDS lab distribution to different live traffic. That is a known property of
models trained on a single dataset (dataset shift), not a preprocessing bug —
the pipeline does clean the infinities that zero-duration flows produce, in both
training and inference.

---

## Configuration

Everything is on the **Settings / About** page: refresh interval, alert
confidence threshold, radar retention and sweep period, simulated flow rate and
attack bias, model reload, and a diagnostics panel that reports exactly which
dependencies are present.

---

## Ethics

Only capture traffic on networks you own or administrate.

---

## License

Released under the MIT License. See [LICENSE](LICENSE).

