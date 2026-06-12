# Launchkey Mixer — PRD

## Problem Statement
> "I want an app that will allow me to use my Novation Launchkey 37 to control volume per in-use app on Windows."

## Architecture (user chose: HYBRID)
- **Web dashboard** (React + FastAPI + MongoDB on Emergent) — configuration UI, profile/macro storage.
- **Local Windows helper agent** (Python script — `/app/backend/helper/launchkey_helper.py`) — connects to the Launchkey 37 via MIDI (mido + python-rtmidi), reads Windows audio sessions with pycaw, and applies the mappings.
- Dashboard ↔ Helper communicate via REST polling: helper POSTs heartbeat/sessions/MIDI events, GETs the active profile + mappings.

## User Persona
Power-user musicians/streamers who own a Novation Launchkey 37 and want to use it as a tactile audio mixer for Windows apps (Spotify, Chrome, Discord, OBS, games).

## Core Requirements (static)
1. Manual mapping for every control: 8 knobs, 16 pads, 37 keys, transport buttons, mod-wheel, pitch-wheel, track/scene navigation.
2. Save macro / profile settings (named presets that can be switched).
3. Per-app Windows volume + mute control via the device.
4. Per-app volume bridge requires a local agent (architectural constraint of OS sandboxing).

## What's Been Implemented (as of 2026-02)
- ✅ FastAPI backend with full CRUD: `/api/profiles`, `/api/profiles/{id}/mappings/{control_id}`.
- ✅ Helper telemetry endpoints: `/api/helper/heartbeat`, `/helper/status`, `/helper/state`, `/helper/sessions`, `/helper/midi-event`, `/helper/midi-events`, `/helper/script` (downloadable Python agent).
- ✅ React dashboard with hardware-inspired control surface UI: 8 knobs, 16 pads, 37-key piano, transport, mod/pitch wheels — all clickable for mapping.
- ✅ Mapping dialog supporting actions: `set_volume`, `system_volume`, `toggle_mute`, `volume_step_up/down`, `media_play_pause`, `media_next`, `media_prev`, `media_stop`. With label, invert direction, target-app selection (from live sessions) or free-text process name.
- ✅ Profile manager (create / activate / delete) — Default profile auto-seeded.
- ✅ MIDI Learn mode — physically wiggle a control and the dialog auto-opens for that control.
- ✅ Live sessions panel (populated by helper) with volume meters.
- ✅ Live event log streaming MIDI activity.
- ✅ Setup page with 6-step Windows install guide and one-click `launchkey_helper.py` download.
- ✅ Helper Python script with full MIDI map for Launchkey MK3, pycaw integration, action dispatcher, heartbeat loop, polling loop, MIDI input loop.
- ✅ Backend tests: 10/10 passing (`/app/backend/tests/test_launchkey_api.py`).
- ✅ Frontend tests: 8/8 user flows verified end-to-end (iteration 3).

## Tech Stack
- Backend: FastAPI 0.110, Motor 3.3.1, Pydantic v2, MongoDB.
- Frontend: React 19, react-router-dom 7, shadcn/ui, Tailwind, Lucide, Sonner.
- Helper (Windows-side): Python 3.10+, mido, python-rtmidi, pycaw, comtypes, pynput, requests.

## Prioritized Backlog
### P0 — Done
- Core mapping CRUD, hardware visualizer, MIDI Learn, profile macros, downloadable helper.

### P1 (next)
- Helper script auto-update / version check.
- Pad-LED feedback: send MIDI back to light pads in colors that match assigned actions.
- "Currently focused window" pseudo-target so a knob can always control the active app.
- Drag-to-reorder profiles; profile import/export (JSON).

### P2 (nice-to-have)
- Browser Web-MIDI mode for users who don't want to install the helper (limited to media keys + browser audio).
- OAuth/shareable profile gallery so the community can publish macro sets.
- Multi-device support (Launchkey 49, Launchpad, etc.) via configurable MIDI maps.
- Helper agent as a signed Windows installer / system tray app.

## Files Map
- `/app/backend/server.py` — FastAPI app + routes.
- `/app/backend/helper/launchkey_helper.py` — Windows helper agent (downloadable).
- `/app/frontend/src/pages/Dashboard.jsx`, `/app/frontend/src/pages/Setup.jsx`.
- `/app/frontend/src/components/HardwareVisualizer.jsx`, `MappingDialog.jsx`, `SessionsPanel.jsx`, `ProfilesPanel.jsx`, `Header.jsx`, `EventLog.jsx`.
- `/app/frontend/src/constants/testIds/launchkey.js` — all data-testid values.
