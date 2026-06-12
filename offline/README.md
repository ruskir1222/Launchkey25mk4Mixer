# 🔌 Launchkey Mixer — Offline / Standalone Build

A single-file Windows `.exe` that runs the **entire** Launchkey Mixer locally — no cloud, no MongoDB, no separate helper process.

> The existing cloud setup (`backend/server.py` + downloaded helper) is untouched and still works. The offline build is an **alternative** packaging.

---

## What you get

`LaunchkeyMixer.exe` (single file) that, when double-clicked:

1. Starts a tiny FastAPI server on `http://127.0.0.1:8765`
2. Serves the React dashboard from inside the exe
3. Stores profiles/mappings in a local SQLite file at `%APPDATA%\LaunchkeyMixer\launchkey.db`
4. Spawns the MIDI + Windows-audio helper in the same process
5. Opens your browser to the dashboard

No internet, no cloud account, no extra installs once built.

---

## Building the exe (do this on your Windows PC)

### Prerequisites
- Python 3.10–3.12 ([python.org](https://www.python.org/downloads/)) — tick **"Add Python to PATH"** during install
- Node.js 18+ ([nodejs.org](https://nodejs.org)) — ships with `npm`, which is fine. Yarn is also supported if installed.

### Build steps
1. Clone the repo and open a terminal in the `offline/` folder.
2. Run:
   ```cmd
   build_windows.bat
   ```
3. When it finishes you'll have:
   ```
   offline\dist\LaunchkeyMixer.exe
   ```
4. Copy that `.exe` wherever you like (Desktop, `C:\Tools\`, USB drive…).

The build script:
- Compiles the React frontend with `REACT_APP_BACKEND_URL=` (empty, so it talks to same origin)
- Bundles the helper script + frontend build inside the exe
- Restores your normal `frontend/.env` afterwards (cloud build still works)

---

## Running the exe

Double-click `LaunchkeyMixer.exe`. The app starts **in your Windows system tray** (no console window) and opens the dashboard in your default browser at `http://127.0.0.1:8765`.

Right-click the tray icon for:
- **Open Dashboard** — re-open the browser tab if you closed it
- **Quit** — fully shut down the app (and the helper)

Closing the browser tab does **not** stop the app — it keeps running in the tray, so your Launchkey stays bound to actions.

Plug in your Launchkey Mini MK4 25 *before* launching for fastest detection.

### Logs
If something looks off, check the log file at:
```
%APPDATA%\LaunchkeyMixer\launchkey.log
```

### Optional flags
- Change port: `set LAUNCHKEY_PORT=9000 && LaunchkeyMixer.exe`
- Data dir lives at `%APPDATA%\LaunchkeyMixer\` — delete to reset everything.

### Auto-start on Windows login
1. Press `Win+R`, type `shell:startup`, press Enter
2. Right-click in the folder → New → Shortcut
3. Point it at your `LaunchkeyMixer.exe`

---

## When to use which mode

| Need | Use |
|---|---|
| Quick iteration, multiple computers, mobile config | **Cloud** (existing `backend/server.py`) |
| Travel, offline studio, privacy, no internet | **Offline** (this build) |
| Both | Run both — they don't conflict (different ports/DBs) |

---

## Troubleshooting

**"No MIDI input ports found"** — Plug in the Launchkey before launching, or hot-plug and restart the exe.

**Antivirus flags the exe** — PyInstaller bundles trigger heuristics. Either whitelist it or build it yourself; the source is right here.

**Port already in use** — Set `LAUNCHKEY_PORT=9000` env var before launching.

**python-rtmidi fails to install during build** — Handled automatically. The build script now installs it with `--only-binary=:all:` and skips on failure; the helper falls back to the built-in `winmm.dll` backend, which works fine for the Launchkey Mini MK4 25. If you ever want rtmidi, install Python 3.11 or 3.12 (best wheel coverage).

---

## File layout

```
offline/
├── server_offline.py        # FastAPI + SQLite + static + helper-thread launcher
├── LaunchkeyMixer.spec      # PyInstaller config
├── build_windows.bat        # One-click build
├── requirements.txt         # Python deps for the exe
└── README.md                # This file
```

At build time the script also creates:
- `offline/static/` — copy of `frontend/build/`
- `offline/helper/` — copy of `backend/helper/`
- `offline/dist/LaunchkeyMixer.exe` — the final standalone app
