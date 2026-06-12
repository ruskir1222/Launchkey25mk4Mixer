"""
Launchkey Mixer — Windows Helper Agent
======================================

This script runs on your Windows PC. It:
  1. Connects to your Novation Launchkey 37 via MIDI (mido + python-rtmidi).
  2. Polls the Launchkey Mixer cloud dashboard for the active mapping profile.
  3. Reports the list of Windows audio sessions (per-app volumes) via pycaw.
  4. Reports incoming MIDI events to the dashboard (used for MIDI Learn).
  5. Applies actions to the OS: change per-app volume, mute/unmute,
     media keys, master volume, etc.

USAGE
-----
1. Install Python 3.10+ on Windows.
2. pip install mido python-rtmidi pycaw comtypes requests pynput
3. Set the dashboard URL (your Emergent app):
     setx LAUNCHKEY_API_URL "https://YOUR-APP.preview.emergentagent.com"
4. Run:
     python launchkey_helper.py
   (or:  python launchkey_helper.py --api https://YOUR-APP.preview.emergentagent.com)

Control IDs the dashboard uses
------------------------------
  knob-1 .. knob-8       (8 rotary pots, CC 21..28 by default on Launchkey MK3)
  pad-1  .. pad-16       (2 rows x 8 RGB pads, notes 40..47 / 48..55 in session mode)
  key-1  .. key-37       (the keyboard keys, MIDI notes 48..84 by default)
  mod-wheel, pitch-wheel
  transport-play, transport-stop, transport-record, transport-loop
  track-up, track-down, scene-up, scene-down

The helper translates incoming MIDI -> control_id via DEFAULT_MIDI_MAP below.
If your Launchkey sends different CC numbers / notes, edit MIDI_MAP_OVERRIDES.
"""

import argparse
import os
import sys
import time
import threading
from typing import Optional, Dict, Any, List

import requests

try:
    import mido
except ImportError:
    print("Please run:  pip install mido")
    sys.exit(1)

# Try to pick a working MIDI backend. python-rtmidi is the default but needs
# a C++ build on some setups. Fall back to pygame.midi (pure pre-built wheel).
_BACKEND = None
try:
    import rtmidi  # noqa: F401
    mido.set_backend("mido.backends.rtmidi")
    _BACKEND = "rtmidi"
except Exception:
    try:
        import pygame.midi  # noqa: F401
        mido.set_backend("mido.backends.pygame")
        _BACKEND = "pygame"
    except Exception:
        print("\n[FATAL] No MIDI backend available.")
        print("Install ONE of these (pre-built wheels, no C++ compile needed):")
        print("   pip install --only-binary=:all: python-rtmidi")
        print("   pip install pygame    # fallback backend")
        sys.exit(1)
print(f"[MIDI] Using backend: {_BACKEND}")

# Audio (Windows only)
try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, ISimpleAudioVolume
except Exception:
    AudioUtilities = None
    print("[WARN] pycaw not available — per-app volume control disabled.")
    print("       Run on Windows with:  pip install pycaw comtypes")

# Media keys
try:
    from pynput.keyboard import Controller, Key
    _kbd = Controller()
except Exception:
    _kbd = None


API_URL_DEFAULT = os.environ.get("LAUNCHKEY_API_URL", "http://localhost:8001")
POLL_INTERVAL = 1.5
HEARTBEAT_INTERVAL = 3.0
SESSIONS_INTERVAL = 2.0

# --- Default Novation Launchkey MK3 MIDI map ------------------------------
# Channel-15 (index 15) is the "InControl" channel used by knobs/pads.
DEFAULT_MIDI_MAP = {
    # CC -> control_id
    "cc": {
        21: "knob-1", 22: "knob-2", 23: "knob-3", 24: "knob-4",
        25: "knob-5", 26: "knob-6", 27: "knob-7", 28: "knob-8",
        1: "mod-wheel",
        102: "track-down", 103: "track-up",
        104: "scene-up", 105: "scene-down",
        115: "transport-play",
        116: "transport-stop",
        117: "transport-record",
        118: "transport-loop",
    },
    # notes for drum pads (top row 40..47, bottom 48..55) – MK3 InControl
    "note": {
        40: "pad-1", 41: "pad-2", 42: "pad-3", 43: "pad-4",
        44: "pad-5", 45: "pad-6", 46: "pad-7", 47: "pad-8",
        48: "pad-9", 49: "pad-10", 50: "pad-11", 51: "pad-12",
        52: "pad-13", 53: "pad-14", 54: "pad-15", 55: "pad-16",
    },
}
# Keys (37) — default MIDI notes 48..84 (C3..C6)
for n in range(48, 85):
    DEFAULT_MIDI_MAP["note"].setdefault(n, f"key-{n - 47}")

MIDI_MAP_OVERRIDES: Dict[str, Dict[int, str]] = {}


def control_id_from_message(msg) -> Optional[str]:
    if msg.type == "control_change":
        return MIDI_MAP_OVERRIDES.get("cc", {}).get(msg.control) or DEFAULT_MIDI_MAP["cc"].get(msg.control)
    if msg.type in ("note_on", "note_off"):
        return MIDI_MAP_OVERRIDES.get("note", {}).get(msg.note) or DEFAULT_MIDI_MAP["note"].get(msg.note)
    if msg.type == "pitchwheel":
        return "pitch-wheel"
    return None


# --- Audio control --------------------------------------------------------
def list_sessions() -> List[Dict[str, Any]]:
    if AudioUtilities is None:
        return []
    out = []
    try:
        sessions = AudioUtilities.GetAllSessions()
        for s in sessions:
            if not s.Process:
                # System sounds session
                vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                out.append({
                    "process_name": "System Sounds",
                    "display_name": "System Sounds",
                    "volume": float(vol.GetMasterVolume()),
                    "muted": bool(vol.GetMute()),
                    "pid": 0,
                })
                continue
            try:
                vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                out.append({
                    "process_name": s.Process.name(),
                    "display_name": s.DisplayName or s.Process.name(),
                    "volume": float(vol.GetMasterVolume()),
                    "muted": bool(vol.GetMute()),
                    "pid": s.Process.pid,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[WARN] list_sessions error: {e}")
    # de-duplicate by process_name (sum volumes shown as average)
    dedup: Dict[str, Dict[str, Any]] = {}
    for s in out:
        key = s["process_name"].lower()
        if key in dedup:
            continue
        dedup[key] = s
    return list(dedup.values())


def set_app_volume(process_name: str, volume: float):
    if AudioUtilities is None:
        return
    volume = max(0.0, min(1.0, volume))
    try:
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() == process_name.lower():
                v = s._ctl.QueryInterface(ISimpleAudioVolume)
                v.SetMasterVolume(volume, None)
    except Exception as e:
        print(f"[WARN] set_app_volume({process_name}): {e}")


def toggle_app_mute(process_name: str):
    if AudioUtilities is None:
        return
    try:
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() == process_name.lower():
                v = s._ctl.QueryInterface(ISimpleAudioVolume)
                v.SetMute(0 if v.GetMute() else 1, None)
    except Exception as e:
        print(f"[WARN] toggle_app_mute({process_name}): {e}")


def set_master_volume(volume: float):
    if AudioUtilities is None:
        return
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        endpoint = cast(interface, POINTER(IAudioEndpointVolume))
        endpoint.SetMasterVolumeLevelScalar(max(0.0, min(1.0, volume)), None)
    except Exception as e:
        print(f"[WARN] set_master_volume: {e}")


def media_key(action: str):
    if _kbd is None:
        return
    key_map = {
        "media_play_pause": Key.media_play_pause,
        "media_next": Key.media_next,
        "media_prev": Key.media_previous,
        "media_stop": Key.media_stop,
    }
    k = key_map.get(action)
    if k:
        _kbd.press(k)
        _kbd.release(k)


# --- Action dispatcher ----------------------------------------------------
class Dispatcher:
    def __init__(self):
        self.mappings: Dict[str, Dict[str, Any]] = {}  # control_id -> mapping

    def update_mappings(self, mappings: List[Dict[str, Any]]):
        self.mappings = {m["control_id"]: m for m in mappings}

    def handle(self, control_id: str, msg) -> Optional[Dict[str, Any]]:
        m = self.mappings.get(control_id)
        if not m:
            return None
        action = m.get("action_type")
        target = m.get("target_app")
        params = m.get("params") or {}

        value = None
        if msg.type == "control_change":
            value = msg.value  # 0..127
        elif msg.type in ("note_on", "note_off"):
            value = msg.velocity if msg.type == "note_on" else 0
        elif msg.type == "pitchwheel":
            value = msg.pitch  # -8192..8191

        try:
            if action == "set_volume" and target:
                if msg.type == "control_change":
                    vol = value / 127.0
                elif msg.type == "pitchwheel":
                    vol = (value + 8192) / 16383.0
                else:
                    return None
                if params.get("invert"):
                    vol = 1.0 - vol
                set_app_volume(target, vol)
                return {"applied": "set_volume", "target": target, "volume": vol}

            if action == "system_volume":
                if msg.type == "control_change":
                    vol = value / 127.0
                    if params.get("invert"):
                        vol = 1.0 - vol
                    set_master_volume(vol)
                    return {"applied": "system_volume", "volume": vol}

            # one-shot actions only on note_on with velocity>0 or cc>0
            is_trigger = (
                (msg.type == "note_on" and msg.velocity > 0)
                or (msg.type == "control_change" and msg.value > 0)
            )
            if not is_trigger:
                return None

            if action == "toggle_mute" and target:
                toggle_app_mute(target)
                return {"applied": "toggle_mute", "target": target}

            if action in ("media_play_pause", "media_next", "media_prev", "media_stop"):
                media_key(action)
                return {"applied": action}

            if action == "volume_step_up" and target:
                step = float(params.get("step", 0.05))
                # find current
                for s in list_sessions():
                    if s["process_name"].lower() == target.lower():
                        set_app_volume(target, s["volume"] + step)
                        return {"applied": "step_up", "target": target}
            if action == "volume_step_down" and target:
                step = float(params.get("step", 0.05))
                for s in list_sessions():
                    if s["process_name"].lower() == target.lower():
                        set_app_volume(target, s["volume"] - step)
                        return {"applied": "step_down", "target": target}

        except Exception as e:
            print(f"[WARN] dispatch error: {e}")
        return None


# --- Networking threads ---------------------------------------------------
class HelperClient:
    def __init__(self, api_url: str):
        self.api = api_url.rstrip("/")
        self.midi_port_name: Optional[str] = None
        self.device_connected = False
        self.dispatcher = Dispatcher()
        self.stop = False

    def post(self, path: str, json: dict):
        try:
            return requests.post(f"{self.api}/api{path}", json=json, timeout=4)
        except Exception as e:
            print(f"[NET] POST {path} failed: {e}")

    def get(self, path: str):
        try:
            return requests.get(f"{self.api}/api{path}", timeout=4).json()
        except Exception as e:
            print(f"[NET] GET {path} failed: {e}")
            return None

    def heartbeat_loop(self):
        while not self.stop:
            self.post("/helper/heartbeat", {
                "version": "1.0.0",
                "midi_port": self.midi_port_name,
                "device_connected": self.device_connected,
            })
            time.sleep(HEARTBEAT_INTERVAL)

    def sessions_loop(self):
        while not self.stop:
            sessions = list_sessions()
            self.post("/helper/sessions", {"sessions": sessions})
            time.sleep(SESSIONS_INTERVAL)

    def state_loop(self):
        while not self.stop:
            data = self.get("/helper/state")
            if data and "mappings" in data:
                self.dispatcher.update_mappings(data["mappings"])
            time.sleep(POLL_INTERVAL)

    def report_event(self, control_id: str, msg):
        payload = {
            "control_id": control_id,
            "raw_type": msg.type,
            "channel": getattr(msg, "channel", None),
            "number": getattr(msg, "control", None) or getattr(msg, "note", None),
            "value": getattr(msg, "value", None) or getattr(msg, "velocity", None) or getattr(msg, "pitch", None),
        }
        self.post("/helper/midi-event", payload)

    def midi_loop(self):
        while not self.stop:
            port_name = self._find_launchkey()
            if not port_name:
                self.device_connected = False
                self.midi_port_name = None
                print("[MIDI] Launchkey not found. Retrying in 3s...")
                time.sleep(3)
                continue
            self.midi_port_name = port_name
            self.device_connected = True
            print(f"[MIDI] Opening port: {port_name}")
            try:
                with mido.open_input(port_name) as port:
                    for msg in port:
                        if self.stop:
                            break
                        cid = control_id_from_message(msg)
                        if cid:
                            self.report_event(cid, msg)
                            self.dispatcher.handle(cid, msg)
            except Exception as e:
                print(f"[MIDI] error: {e}")
                self.device_connected = False
                time.sleep(2)

    def _find_launchkey(self) -> Optional[str]:
        try:
            for name in mido.get_input_names():
                low = name.lower()
                if "launchkey" in low and "incontrol" not in low and "midiin2" not in low:
                    return name
            # fallback to any port containing launchkey
            for name in mido.get_input_names():
                if "launchkey" in name.lower():
                    return name
        except Exception as e:
            print(f"[MIDI] list ports failed: {e}")
        return None

    def run(self):
        threads = [
            threading.Thread(target=self.heartbeat_loop, daemon=True),
            threading.Thread(target=self.sessions_loop, daemon=True),
            threading.Thread(target=self.state_loop, daemon=True),
            threading.Thread(target=self.midi_loop, daemon=True),
        ]
        for t in threads:
            t.start()
        print(f"[Launchkey Mixer] Helper running. Dashboard API: {self.api}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop = True
            print("Shutting down.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=API_URL_DEFAULT, help="Dashboard API base URL")
    args = ap.parse_args()
    HelperClient(args.api).run()


if __name__ == "__main__":
    main()
