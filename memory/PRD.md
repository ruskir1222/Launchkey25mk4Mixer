# Launchkey Mixer — PRD

## Problem Statement
> "I want an app that will allow me to use my Novation Launchkey Mini MK4 25 to control volume per in-use app on Windows."

## Architecture
Two coexisting modes — user chose to keep both:

### Mode A — Cloud + Local Helper (original)
- Web dashboard (React + FastAPI + MongoDB on Emergent cloud) — configuration UI, profile/macro storage.
- Local Windows helper agent (`/app/backend/helper/launchkey_helper.py`) — connects to Launchkey via MIDI, reads Windows audio sessions with pycaw, applies mappings.
- Dashboard ↔ Helper communicate via REST polling.

### Mode B — Standalone Windows Executable (new — Feb 2026)
- Single `LaunchkeyMixer.exe` produced by PyInstaller (`/app/offline/`).
- Bundles FastAPI + SQLite + React build + helper logic in one process.
- Runs offline; data in `%APPDATA%\LaunchkeyMixer\`.
- System tray icon with Open Dashboard / Quit menu.

## User Persona
Power-user musicians/streamers who own a Novation Launchkey Mini MK4 25 and want to use it as a tactile audio mixer for Windows apps (Spotify, Chrome, Discord, OBS, games).

## Core Requirements
1. Manual mapping for every control: 8 knobs, 16 pads, 25 mini-keys (2 octaves), transport, touch strips.
2. Save macro / profile settings (named presets that can be switched).
3. Per-app Windows volume + mute control via the device.
4. Per-app volume bridge requires a local agent (architectural constraint of OS sandboxing).
5. Optional offline mode (no cloud, no MongoDB).

## What's Been Implemented

### Phase 1 — Cloud Dashboard (DONE)
- FastAPI backend with full CRUD: `/api/profiles`, `/api/profiles/{id}/mappings/{control_id}`.
- Helper telemetry endpoints: `/helper/heartbeat`, `/helper/status`, `/helper/state`, `/helper/sessions`, `/helper/midi-event`, `/helper/midi-events`, `/helper/script`.
- React dashboard with hardware-inspired control surface UI (knobs, pads, 25 mini-keys, transport, touch strips).
- Mapping dialog supporting: set_volume, system_volume, toggle_mute, volume_step_up/down, media_play_pause/next/prev/stop, launch_app, kill_app, send_keystroke, open_url, run_command.
- Profile manager (create / activate / delete).
- MIDI Learn (target-first + Layout Wizard sequential mapping).
- Live sessions panel, live event log.
- Setup page with Windows install guide + script download.
- Helper Python script with MIDI map for Launchkey MK3 + MK4 + Mini, pycaw integration, action dispatcher, momentary-pad debouncing.

### Phase 2 — Polish & Docs (DONE)
- Polished README with screenshots (`/app/docs/dashboard.jpg`, `mapping-dialog.jpg`, `setup.jpg`).
- Project pushed to GitHub: https://github.com/ruskir1222/Launchkey25mk4Mixer.

### Phase 3 — Standalone Offline Build (DONE — Feb 2026)
- `/app/offline/server_offline.py` — FastAPI + SQLite + serves React build + spawns helper in background thread.
- `/app/offline/build_windows.bat` — auto-detects yarn/npm (installs yarn if missing), auto-detects python, fallback chains.
- `/app/offline/LaunchkeyMixer.spec` — PyInstaller spec with `collect_submodules('uvicorn')`, `collect_submodules('starlette')`, hidden imports for all helper deps + pystray.
- System tray icon (pystray + Pillow) with Open Dashboard / Quit menu — runs on background thread; uvicorn on main thread.
- Auto-generated tray icon (no asset file shipped).
- Dual logging: stdout + `%APPDATA%\LaunchkeyMixer\launchkey.log`.
- `os.startfile()` used on Windows for browser launch (more reliable than webbrowser.open from windowed exes).
- Skip StreamHandler when `sys.stderr` is None (windowed PyInstaller mode).

### Phase 4 — Releases (BLOCKED)
- `.github/workflows/release.yml` — GitHub Actions workflow to build Windows exe on tag push.
- v0.1.0 release **created** at https://github.com/ruskir1222/Launchkey25mk4Mixer/releases/tag/v0.1.0 (manual upload pending).
- ⚠️ **GitHub Actions automation blocked** — user's GitHub account is locked due to a billing issue. Once unlocked, future `git tag vX.Y.Z && git push origin vX.Y.Z` will auto-build + publish.

## Tech Stack
- Backend (cloud): FastAPI 0.110, Motor 3.3.1, Pydantic v2, MongoDB.
- Backend (offline): FastAPI + sqlite3 (stdlib) + pystray + Pillow + PyInstaller.
- Frontend: React 19, react-router-dom 7, shadcn/ui, Tailwind, Lucide, Sonner.
- Helper (Windows-side): Python 3.10–3.12, mido / python-rtmidi (with `winmm.dll` fallback), pycaw, comtypes, pynput, requests.

## Files of Reference
- `/app/backend/server.py` — FastAPI app + routes (cloud mode).
- `/app/backend/helper/launchkey_helper.py` — Windows helper agent (downloadable).
- `/app/offline/server_offline.py` — Standalone offline server.
- `/app/offline/LaunchkeyMixer.spec` — PyInstaller spec.
- `/app/offline/build_windows.bat` — Windows build script.
- `/app/.github/workflows/release.yml` — CI build & release.
- `/app/frontend/src/pages/Dashboard.jsx`, `/app/frontend/src/pages/Setup.jsx`.
- `/app/frontend/src/components/HardwareVisualizer.jsx`, `MappingDialog.jsx`, `LayoutWizard.jsx`, `SessionsPanel.jsx`, `ProfilesPanel.jsx`, `Header.jsx`, `EventLog.jsx`.

## Prioritized Backlog

### P0 — Done
- Core mapping CRUD, hardware visualizer, MIDI Learn, profile macros, downloadable helper.
- Standalone Windows exe with system tray.
- v0.1.0 release page on GitHub (manual upload pending).

### P1 — Pending
- ⏳ Upload `LaunchkeyMixer.exe` to v0.1.0 release page (manual until billing unlocked).
- ⏳ Resolve GitHub billing issue → unlock Actions → automated releases on tag push.

### P2 — Future
- Pad-LED feedback (needs SysEx packet-sniffing of Novation Components — MK4 Mini firmware blocks standard host-LED control).
- Rename internal control IDs `mod-wheel` / `pitch-wheel` → `mod-strip` / `pitch-strip` (cosmetic; would reset existing bindings).
- Hide tray icon behind a single-instance lock (prevent double-launch).
- Inno Setup installer wrapping the PyInstaller exe (Start menu shortcut, auto-start on login).
- Code-sign the exe to reduce Windows Defender false-positives.
- Profile import/export as JSON (sync between cloud + offline modes).
- "Currently focused window" pseudo-target so a knob always controls the active app.

## Known Limitations / Caveats for Next Agent
- **Hardware:** User has a **Launchkey Mini MK4 25** specifically — don't build for the Launchkey 37.
- **LED control:** Physical pad LED illumination was attempted multiple times but the MK4 Mini firmware rejects standard SysEx + Note-On color commands. Rolled back; UI-based LED visualizer works. Don't re-attempt without first packet-sniffing Novation Components.
- **Helper updates:** When `launchkey_helper.py` changes, cloud-mode users must re-download via `/setup` page. Offline-mode users must rebuild the exe.
- **Windowed PyInstaller mode:** `sys.stderr` is `None`. Always guard StreamHandler creation. Always wrap thread targets in try/except with `log.exception()` — otherwise crashes are silent.
- **Uvicorn threading:** Must run on the **main thread** in windowed mode; pystray works fine on a background thread on Windows.
- **YAML quirk in CI:** `--only-binary=:all:` MUST be inside a `run: |` block scalar, not a single-line `run:` (the colons confuse YAML's flow scalar parser).
- **GitHub Actions:** Blocked by user's billing issue as of Feb 2026. The workflow file is correct and ready; just needs the billing unlock.
