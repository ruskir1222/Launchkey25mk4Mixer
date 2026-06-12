# 🎹 Launchkey Mixer

> A hybrid web + local-helper app that turns your **Novation Launchkey Mini MK4 25** into a tactile Windows control surface — per-app volume mixing, mute toggles, app launching, keystrokes, URLs, and shell macros.

![Status](https://img.shields.io/badge/status-stable-success)
![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Stack](https://img.shields.io/badge/stack-React%20%7C%20FastAPI%20%7C%20MongoDB-orange)

---

## ✨ What it does

Move a knob on your Launchkey → a specific Windows app's volume slider moves with it.
Tap a pad → Discord mutes, Spotify launches, OBS scene-switches, or any keystroke / URL / shell command fires.

Every physical control on the MK4 Mini 25 — **8 knobs, 16 pads, 25 keys, mod wheel, transport buttons** — is individually mappable via a visual dashboard.

---

## 🏗️ Architecture

Two halves working together:

```
┌──────────────────────────┐         ┌──────────────────────────┐
│  Web Dashboard (cloud)   │ ◄────── │  launchkey_helper.py     │
│  React + FastAPI + Mongo │  HTTP   │  (runs on your Windows)  │
│  • Mapping UI            │ ──────► │  • Reads MIDI in         │
│  • Profile storage       │         │  • Controls Windows audio│
│  • MIDI Learn            │         │  • Fires actions locally │
└──────────────────────────┘         └──────────────────────────┘
```

**Why hybrid?** Per-app Windows volume + raw MIDI access can't be done from a browser sandbox. The cloud dashboard handles UX and config; the local Python script handles hardware + OS APIs.

---

## 🎯 Supported Actions

| Action | Description |
|---|---|
| **App Volume** | Knob/slider controls a specific app's volume (Spotify, Chrome, Discord, etc.) |
| **System Volume** | Master Windows volume |
| **Toggle Mute** | Pad mutes/unmutes an app |
| **Launch App** | Open an executable or shortcut |
| **Kill App** | Terminate a running process |
| **Keystroke** | Send any key combo (e.g. `ctrl+shift+m`) |
| **Open URL** | Launch a website in the default browser |
| **Shell Command** | Run any custom shell command |
| **Media Keys** | Play/Pause, Next, Previous, Stop |

---

## 🚀 Quick Start

### 1. Deploy the Dashboard (Cloud)

The dashboard is a standard React + FastAPI + MongoDB app. Set these env vars:

**`backend/.env`**
```
MONGO_URL=mongodb://localhost:27017
DB_NAME=launchkey_mixer
CORS_ORIGINS=*
```

**`frontend/.env`**
```
REACT_APP_BACKEND_URL=https://your-dashboard-url.com
```

Then:
```bash
# Backend
cd backend && pip install -r requirements.txt && uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend
cd frontend && yarn install && yarn start
```

### 2. Install the Local Helper (Windows)

1. Open the dashboard → click **Setup** → **Download `launchkey_helper.py`**
2. Install Python 3.10+ ([python.org](https://www.python.org/downloads/))
3. Install dependencies:
   ```cmd
   pip install requests pycaw comtypes pynput python-rtmidi
   ```
4. Point the helper at your dashboard:
   ```cmd
   setx LAUNCHKEY_API_URL "https://your-dashboard-url.com"
   ```
5. Plug in your Launchkey Mini MK4 25 and run:
   ```cmd
   python launchkey_helper.py
   ```

The on-screen Launchkey visualizer will start reacting to your physical device. ✨

### 3. Start Mapping

- Click any knob/pad/key on the visualizer → choose an action → save
- Or use **MIDI Learn**: click "Learn" then wiggle the physical control
- Or use the **Layout Wizard**: step through every control sequentially

---

## 🎛️ Hardware Profile

This project is built for the **Novation Launchkey Mini MK4 25**:

- 8 rotary knobs (CC-mapped)
- 2×8 velocity pads (treated as momentary switches via debouncing)
- 25 mini-keys (2 octaves)
- Mod wheel, transport buttons, octave/track buttons

The default MIDI map auto-detects MK3 / MK4 / Mini variants — should work with most Launchkey models, but UI is tuned for the 25-key Mini.

---

## 📂 Project Structure

```
.
├── backend/
│   ├── server.py                    # FastAPI app
│   ├── helper/
│   │   ├── launchkey_helper.py      # The Windows local agent
│   │   ├── install_windows.bat
│   │   └── requirements.txt
│   └── tests/
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.jsx        # Main mapping UI
│       │   └── Setup.jsx            # Helper install guide
│       └── components/
│           ├── HardwareVisualizer.jsx  # On-screen Launchkey
│           ├── MappingDialog.jsx       # Action config
│           ├── LayoutWizard.jsx        # Sequential map flow
│           ├── SessionsPanel.jsx       # Live audio sessions
│           └── EventLog.jsx
└── memory/
    └── PRD.md
```

---

## ⚙️ Tech Stack

- **Backend**: FastAPI · Motor · Pydantic v2 · MongoDB
- **Frontend**: React 19 · Tailwind · shadcn/ui · Lucide · Sonner
- **Helper**: Python 3.10+ · mido / python-rtmidi (with `winmm` fallback) · pycaw · pynput · comtypes

---

## 🐛 Known Limitations

- **Physical pad LED colors**: The MK4 Mini firmware locks host-LED SysEx control without undocumented commands. UI-based LED visualizer works perfectly; physical pad illumination is on the backlog (would need Novation Components packet sniffing).
- **Windows only**: pycaw is Windows-specific. macOS/Linux would need different audio APIs.

---

## 📋 Roadmap

- [ ] Physical MK4 pad LED illumination
- [ ] Profile import/export (JSON)
- [ ] "Currently focused window" pseudo-target
- [ ] Helper auto-update / version check
- [ ] System tray app installer for the helper

---

## 📜 License

MIT — do whatever you want with it.

---

Built with ❤️ and a Launchkey Mini MK4 25.
