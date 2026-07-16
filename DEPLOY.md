# Deploying

Two things to know before you start.

**Live capture will not work on any hosted platform.** A host has no packet
capture drivers and no access to your network, so nfstream is deliberately left
out of `requirements.txt`. On a deployed app the capture source dropdown offers
Simulated only. That is the honest behaviour, and it is also what you want for a
client demo: simulated traffic fills the radar, the alerts and the charts.

**The live panel does work on a host,** because it travels over Streamlit's own
port. It is served from `nids/static/panel.html` at `/app/static/panel.html` and
polls `/app/static/live.json`, both on the same origin as the app. An earlier
version ran its own server on a second port; that was fine locally and would
have come up blank on a host, since a browser resolves `127.0.0.1` to the
viewer's own machine and Community Cloud only exposes the one port anyway.

**Simulated traffic starts by itself.** A visitor opening the link lands on a
dashboard that is already alive: the radar sweeping, red contacts on it, the
alert feed filling. Without that, they would find the radar parked on STANDBY
and would have to know to press Start. It fires once per process and never
overrides a capture that is already running, so pressing Stop is respected. Set
`NIDS_AUTOSTART=0` in the environment to turn it off.

The sidebar still says **"Simulation mode"** the whole time, and the exported
report says so too. A dashboard that looks live while running on generated data
is worse than one that admits it, and it is the first thing anyone technical
will ask about.

---

## Repository layout

This layout is not accidental. Community Cloud reads `.streamlit/config.toml`
only from the repository root, and Streamlit serves the static folder from
beside the entrypoint script. Both constraints are satisfied below.

```
<repo root>
├── .streamlit/config.toml     read by Community Cloud (root only)
├── requirements.txt           read by Community Cloud (root only)
├── run.bat                    local Windows launcher
├── README.md
├── SETUP_WINDOWS.md
└── nids/
    ├── app.py                 the entrypoint you point Cloud at
    ├── static/                served at /app/static/  (generated at runtime)
    ├── core/  views/  components/
    ├── models/                drop the trained model here
    └── data/                  SQLite log
```

Do not move `app.py` out of `nids/`, or `static/` stops being served from the
right place.

---

## Step 1 - Push to GitHub

From the repository root:

```
git init
git add .
git commit -m "NIDS dashboard"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo>.git
git push -u origin main
```

`.gitignore` already excludes `.venv`, `__pycache__`, the SQLite log, the
generated panel files and any model artefacts.

Make the repo **public**. A private repo works, but Community Cloud then needs
the broader `repo` OAuth scope from GitHub and creates a deploy key.

---

## Step 2 - Deploy

1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **New app** → pick your repository and the `main` branch.
3. **Main file path:** `nids/app.py`

   This is the one field people get wrong. It is not `app.py`.
4. Deploy. First build takes a few minutes.

The **Deploy** button in your local app opens the same flow.

---

## What works where

| | Local | Deployed |
|---|---|---|
| All seven pages | Yes | Yes |
| Live panel, radar, no blink | Yes | Yes |
| Simulated traffic | Yes | Yes |
| CSV upload and analyze | Yes | Yes |
| Live capture (nfstream + Npcap) | Yes, with setup | **No** |
| PCAP replay | Yes, with nfstream | **No** |
| SQLite detection log | Persists | Resets on restart |

The log resetting is worth knowing before a demo: Community Cloud containers are
ephemeral, so anything written to disk disappears when the app sleeps or
redeploys. Everything the client sees is rebuilt from live simulated traffic
anyway, so it does not matter for a demo, and it would matter a great deal for a
real deployment.

---

## Adding the model later

Once the training notebook exports the five files, put them in `nids/models/`
and push:

```
git add -f nids/models/model.joblib nids/models/scaler.joblib \
           nids/models/feature_columns.json nids/models/label_encoder.joblib \
           nids/models/metrics.json
git commit -m "Add trained model"
git push
```

The `-f` is needed because `.gitignore` excludes model files by default, which
keeps large binaries out of the repo until you actually want one in.

Community Cloud redeploys on push. The sidebar will change from "Simulation
mode" to your model name, and Model Performance will fill in.

If `model.joblib` is larger than about 100 MB, GitHub will reject it. A Random
Forest trained on CICIDS2017 can easily get there. Options, in order of
preference: cap `n_estimators` and `max_depth` at training time, use
`joblib.dump(model, path, compress=3)`, or switch to XGBoost, whose models are
far smaller. Git LFS also works but Community Cloud does not fetch LFS files, so
it is not a real option here.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| App loads, Live Monitoring panel is blank | The static route is not serving. Check `enableStaticServing = true` is in the **root** `.streamlit/config.toml`, and that the main file path is `nids/app.py`. |
| `ModuleNotFoundError: nids` | Main file path is wrong. It must be `nids/app.py`, and `nids/__init__.py` must be committed. |
| Build fails on nfstream | Something re-added it to `requirements.txt`. It does not belong there. |
| App is slow or gets killed | Community Cloud has a memory limit. Lower the simulated flow rate on Settings, or reduce `BUFFER_SIZE` in `core/store.py`. |
| Panel says DISCONNECTED | The app went to sleep or restarted. Reload the page. |
