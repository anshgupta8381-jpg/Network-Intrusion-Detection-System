# Windows setup guide

Everything you need to do by hand on your machine, in order. Steps 1 to 3 get
the dashboard running. Steps 4 onward are only needed when you want live capture
and the real model.

Verified against nfstream 6.6.0 (released February 2026) and Npcap as of
July 2026. If a link has moved, the tool name is still correct.

---

## Step 1 - Install Python

Skip if you already have Python 3.9 or newer.

1. Download Python 3.12 from <https://www.python.org/downloads/windows/>
2. Run the installer.
3. **Tick "Add python.exe to PATH" on the first screen.** This is the single
   most common thing people miss, and everything below fails without it.
4. Click "Install Now".

Check it worked. Open Command Prompt (press Win, type `cmd`, Enter):

```
python --version
```

You should see `Python 3.12.x`.

**Why 3.12:** nfstream ships prebuilt Windows wheels for CPython 3.9 through
3.14, so 3.12 is comfortably inside the supported range and every other package
here has stable wheels for it too. Do not use 3.14 yet unless you enjoy
troubleshooting.

---

## Step 2 - Install the project dependencies

1. Unzip the project folder somewhere without spaces in the path.
   `C:\projects\nids` is good. A path with spaces such as
   `C:\Users\Ansh\My Documents\final year\nids`
   will cause problems later.
2. Open Command Prompt in that folder. Easiest way: open the folder in File
   Explorer, click the address bar, type `cmd`, press Enter.
3. Run these one at a time:

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Your prompt should now start with `(.venv)`. That means the virtual environment
is active. You need to run `.venv\Scripts\activate` every time you open a new
terminal for this project.

**If nfstream fails to install here, that is expected and fine.** It needs Npcap
first (Step 4). Everything except live capture works without it. To get past the
error for now, open `requirements.txt`, put a `#` in front of the `nfstream`
line, and run the pip command again.

---

## Step 3 - Run the dashboard

```
streamlit run app.py
```

Your browser opens at `http://localhost:8501`. You should see the dashboard
already populated with simulated traffic.

Or just double-click **`run.bat`**, which creates the environment and installs
everything on first run.

To stop it: press `Ctrl+C` in the terminal.

At this point every screen works. The sidebar will say **"Simulation mode"**,
which is correct and honest: there is no trained model yet, so the app is showing
generated traffic. Go to Live Monitoring and press **Start** to watch the radar
sweep and the flow table fill up.

---

## Step 4 - Install Npcap (only for live capture)

nfstream does not bundle capture drivers on Windows because of licensing, so
Npcap has to be installed separately, and it must go in **before** nfstream.

**If you already have Wireshark installed, you already have Npcap. Skip to Step 5.**

1. Go to <https://npcap.com/#download>
2. Download the **Npcap installer** (the free one, not the OEM one).
3. Run it as administrator.
4. On the options screen, **tick "Install Npcap in WinPcap API-compatible Mode"**.
   Leave the other defaults alone.
5. Finish, then **restart your computer**. The driver will not load properly
   until you do.

Verify:

```
.venv\Scripts\activate
pip install nfstream scapy
python -c "from nfstream import NFStreamer; print('nfstream ready')"
```

`scapy` is installed alongside nfstream on purpose. On Windows the app uses it to
turn the friendly interface name ("Wi-Fi") into the Npcap device path
(`\Device\NPF_{GUID}`) that nfstream actually needs. Without scapy, live capture
fails with "please specify a valid network interface name" even though the
interface is fine.

If that prints `nfstream ready`, you are set.

---

## Step 5 - Run with capture privileges

Packet capture needs administrator rights on Windows. Without them nfstream will
open, find no interfaces, and fail with an unhelpful error.

1. Press Win, type `cmd`.
2. **Right-click "Command Prompt" and choose "Run as administrator".**
3. Then:

```
cd C:\projects\nids
.venv\Scripts\activate
streamlit run app.py
```

Or right-click `run.bat` and choose "Run as administrator".

Now on the **Live Monitoring** page, the **Capture source** dropdown will offer
"Live interface". Pick your adapter (usually "Wi-Fi" or "Ethernet"), press
**Start**.

Go to **Settings / About → Diagnostics** at any point. It tells you exactly what
is installed and what is missing, which is faster than reading a traceback.

### One thing to be realistic about

On an ordinary home Wi-Fi connection you will only see **your own** traffic. That
is not a bug in the app, it is how switched networks work: your laptop's network
card only receives packets addressed to your laptop. A real deployment sits on a
**mirror port** or **SPAN port** on a managed switch, where the switch is
configured to copy all traffic to one port.

For your project demo, you have three honest options:

1. **PCAP replay** - the best option for a viva. Download a capture file, put it
   in the `data/` folder, choose "PCAP file" as the source. It runs through the
   real nfstream flow extraction, so it exercises the whole pipeline, and it is
   reproducible. Sample captures: <https://www.netresec.com/?page=PcapFiles>
2. **Generate your own traffic** - run `nmap` against your own machine from
   another device on your network and watch PortScan detections appear. Only do
   this on your own network.
3. **Simulated source** - for when you just need the interface to look alive.

Say which one you are using when you present it. It reads as competence, not as
a shortcoming.

---

## Step 6 - Train the model and plug it in

The app never trains. It loads what your notebook exports.

### 6a. Get the dataset

CICIDS2017 from <https://www.unb.ca/cic/datasets/ids-2017.html>

Download the **MachineLearningCSV.zip** (the pre-computed flow features, roughly
1 GB unzipped). You do not need the raw PCAPs for training.

### 6b. Train in Colab

Your laptop will struggle with 2.8 million rows. Use Colab, upload the CSVs to
Drive, and train there.

The exact export code your notebook needs is on the **Model Performance** page of
the dashboard, in the expander at the bottom. Copy it from there so it stays in
sync with what the app reads.

Your notebook must produce these five files:

| File | What it is |
|---|---|
| `model.joblib` | the fitted classifier |
| `scaler.joblib` | the scaler fitted on the training features |
| `feature_columns.json` | the ordered feature names used at training |
| `label_encoder.joblib` | maps class numbers back to names (skip if you trained on string labels) |
| `metrics.json` | evaluation results for the Model Performance page |

### 6c. Plug it in

1. Download those files from Colab.
2. Drop them into the **`models\`** folder.
3. In the app, go to **Settings / About → Model → Reload model**.

The sidebar will change from "Simulation mode" to your model name, and every
prediction from that point is real. Nothing else changes: the radar, the alerts,
the tables and the exports all keep working exactly as they did.

**Watch the feature order.** If your notebook trains on a different feature set
than the 20 in `core/schema.py`, that is fine, just make sure
`feature_columns.json` reflects it. The app reads that file and aligns every
input to it. If the file is missing, it falls back to the built-in list, and a
mismatch there is the one bug that would silently produce nonsense predictions.
The scaler catches most of this for you: because the app passes column names
through, sklearn raises rather than scoring your columns in the wrong order.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Fatal Python error: _PySemaphore_Wakeup: parking_lot: ReleaseSemaphore failed` | An open CPython bug on Windows ([cpython#148820](https://github.com/python/cpython/issues/148820)), not a bug in this app. It fires when a session tears down and Streamlit joins the watchdog file-watcher thread. `.streamlit/config.toml` already sets `fileWatcherType = "none"` to remove that code path. If it still happens, use Python 3.12 instead of 3.13. |
| `ConnectionResetError: [WinError 10054]` or `_ProactorBasePipeTransport._call_connection_lost` | Cosmetic. The browser tab closed or refreshed and asyncio logged the dropped websocket during cleanup. Nothing to fix. |
| `'python' is not recognized` | PATH was not ticked during install. Reinstall Python, tick "Add python.exe to PATH". |
| `'streamlit' is not recognized` | The venv is not active. Run `.venv\Scripts\activate` first. Your prompt should show `(.venv)`. |
| `cannot be loaded because running scripts is disabled` | You are in PowerShell. Either use `cmd` instead, or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. |
| nfstream installs but no interfaces appear | Npcap missing, or you did not restart after installing it. Check Settings → Diagnostics. |
| `Could not open interface` | Not running as administrator. |
| Live capture shows nothing | You are probably on a normal switched port. See the note in Step 5. |
| Model loads but every prediction is wrong | Feature order mismatch. Check `feature_columns.json` against what your notebook trained on. |
| `InconsistentVersionWarning` when loading the model | The scikit-learn in Colab is a different version from the one on your laptop. Match them: check `sklearn.__version__` in Colab, then `pip install scikit-learn==<that version>`. |
| Port 8501 already in use | An old instance is still running. `streamlit run app.py --server.port 8502`, or close the other terminal. |
| Dashboard is slow with capture running | Raise the refresh interval on Settings → Capture. Three seconds is the design default; five is fine on a busy network. |

---

## Quick reference

```
:: every new terminal
cd C:\projects\nids
.venv\Scripts\activate

:: run
streamlit run app.py

:: run with live capture (administrator terminal)
streamlit run app.py

:: stop
Ctrl+C
```
