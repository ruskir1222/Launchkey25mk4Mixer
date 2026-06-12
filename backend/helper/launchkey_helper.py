"""
Launchkey Mixer — Windows Helper Agent
======================================

Python 3.x friendly (incl. 3.13 / 3.14): tries MIDI backends in this order:
    1. python-rtmidi  (fastest)
    2. pygame.midi    (pure pre-built wheel)
    3. winmm.dll      (pure ctypes — works on ANY Python with no install)

Only the third option requires NO extra packages, so even on the freshest
Python releases this script will run.

USAGE
-----
1. Install Python 3.10+ (3.12 recommended for best wheel coverage).
2. pip install requests pycaw comtypes pynput
   (optional speedups: pip install --only-binary=:all: python-rtmidi   OR   pip install pygame)
3. Set the dashboard URL once:
     setx LAUNCHKEY_API_URL "https://YOUR-APP.preview.emergentagent.com"
4. Run:
     python launchkey_helper.py
   (or:  python launchkey_helper.py --api https://YOUR-APP.preview.emergentagent.com)

The on-screen Launchkey on the dashboard will then react to your real device.
"""

import argparse
import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes
from typing import Optional, Dict, Any, List

import requests

API_URL_DEFAULT = os.environ.get("LAUNCHKEY_API_URL", "http://localhost:8001")
POLL_INTERVAL = 1.5
HEARTBEAT_INTERVAL = 3.0
SESSIONS_INTERVAL = 2.0
DEBUG = False


# --- Default Novation Launchkey MIDI map (MK3 + MK4 + Mini) ---------------
# Strategy: knobs match by CC number alone (channel-agnostic).
# Pads are matched by (channel, note) on the drum channel (commonly ch 9
# zero-indexed = "channel 10" in 1-indexed terms). Keys are anything on a
# non-drum channel and are auto-numbered relative to the lowest note seen.

CC_MAP: Dict[int, str] = {
    21: "knob-1", 22: "knob-2", 23: "knob-3", 24: "knob-4",
    25: "knob-5", 26: "knob-6", 27: "knob-7", 28: "knob-8",
    1: "mod-wheel",
    102: "track-down", 103: "track-up",
    104: "scene-up", 105: "scene-down",
    115: "transport-play",
    116: "transport-stop",
    117: "transport-record",
    118: "transport-loop",
}

# Pads. Different Launchkey models use different note ranges. We accept BOTH
# the MK3 range (40..55) and the MK4 range (36..51) on channel 9.
PAD_NOTES: Dict[int, str] = {}
# MK4 / standard drum layout: bottom row 36..43, top row 44..51
for i, n in enumerate(range(36, 44)):
    PAD_NOTES[n] = f"pad-{i + 9}"   # bottom physical row -> pads 9..16
for i, n in enumerate(range(44, 52)):
    PAD_NOTES[n] = f"pad-{i + 1}"   # top physical row -> pads 1..8
# MK3 InControl extras (won't clash because they're outside 36..51)
for i, n in enumerate(range(40, 48)):
    PAD_NOTES.setdefault(n, f"pad-{i + 1}")
for i, n in enumerate(range(48, 56)):
    PAD_NOTES.setdefault(n, f"pad-{i + 9}")

PAD_CHANNELS = {9, 15}   # 9 = standard drum / MK4 ; 15 = MK3 InControl
DRUM_CHANNELS = PAD_CHANNELS

# Keys: anything on non-drum channels. Mapped to key-1, key-2, ... by
# subtracting the configured base note. Default base = lowest C below E3 (48).
KEY_BASE_NOTE = 36  # C2 — covers 25/37/49/61-key models comfortably

# Optional user overrides
MIDI_MAP_OVERRIDES: Dict[str, Dict] = {"cc": {}, "note": {}}


def control_id_from_msg(msg: "Msg") -> Optional[str]:
    if msg.type == "control_change":
        cid = MIDI_MAP_OVERRIDES["cc"].get(msg.control) or CC_MAP.get(msg.control)
        # Synthetic id for unmapped CCs — lets the dashboard MIDI-Learn ANY knob/slider.
        return cid or f"cc-ch{msg.channel}-{msg.control}"
    if msg.type in ("note_on", "note_off"):
        ov = MIDI_MAP_OVERRIDES["note"].get(msg.note)
        if ov:
            return ov
        if msg.channel in DRUM_CHANNELS and msg.note in PAD_NOTES:
            return PAD_NOTES[msg.note]
        idx = msg.note - KEY_BASE_NOTE + 1
        if 1 <= idx <= 88 and msg.channel not in DRUM_CHANNELS:
            return f"key-{idx}"
        # synthetic fallback
        return f"note-ch{msg.channel}-{msg.note}"
    if msg.type == "pitchwheel":
        return "pitch-wheel"
    return None


# Lightweight Msg shim so all 3 backends produce the same object shape
class Msg:
    __slots__ = ("type", "channel", "control", "note", "value", "velocity", "pitch")

    def __init__(self, type, channel=None, control=None, note=None, value=None, velocity=None, pitch=None):
        self.type = type
        self.channel = channel
        self.control = control
        self.note = note
        self.value = value
        self.velocity = velocity
        self.pitch = pitch


# ============================================================
# AUDIO (Windows) — pycaw if available, else stubbed
# ============================================================
try:
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, ISimpleAudioVolume
    _HAS_PYCAW = True
except Exception:
    _HAS_PYCAW = False
    print("[WARN] pycaw not available — per-app volume disabled.")
    print("       pip install pycaw comtypes")

# media keys
try:
    from pynput.keyboard import Controller, Key
    _kbd = Controller()
except Exception:
    _kbd = None


def list_sessions() -> List[Dict[str, Any]]:
    if not _HAS_PYCAW:
        return []
    out = []
    try:
        for s in AudioUtilities.GetAllSessions():
            try:
                vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                if s.Process:
                    out.append({
                        "process_name": s.Process.name(),
                        "display_name": s.DisplayName or s.Process.name(),
                        "volume": float(vol.GetMasterVolume()),
                        "muted": bool(vol.GetMute()),
                        "pid": s.Process.pid,
                    })
                else:
                    out.append({
                        "process_name": "System Sounds",
                        "display_name": "System Sounds",
                        "volume": float(vol.GetMasterVolume()),
                        "muted": bool(vol.GetMute()),
                        "pid": 0,
                    })
            except Exception:
                continue
    except Exception as e:
        print(f"[WARN] list_sessions: {e}")
    seen, dedup = set(), []
    for s in out:
        k = s["process_name"].lower()
        if k in seen:
            continue
        seen.add(k); dedup.append(s)
    return dedup


def set_app_volume(name: str, volume: float) -> bool:
    if not _HAS_PYCAW:
        return False
    volume = max(0.0, min(1.0, volume))
    try:
        v = _get_cached_volume(name)
        if v is not None:
            v.SetMasterVolume(volume, None)
            return True
        # cache miss — slow path
        found = 0
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() == name.lower():
                iface = s.SimpleAudioVolume
                _SESSION_CACHE[name.lower()] = iface
                iface.SetMasterVolume(volume, None)
                found += 1
        if found == 0:
            sessions = AudioUtilities.GetAllSessions()
            avail = sorted({s.Process.name() for s in sessions if s.Process})
            print(f"[vol] no audio session for '{name}'. Active apps: {avail}")
            return False
        return True
    except Exception as e:
        _SESSION_CACHE.pop(name.lower(), None)
        print(f"[vol] error on '{name}': {e}")
        return False


# Cache ISimpleAudioVolume interfaces per process name so we don't enumerate
# every audio session on every MIDI tick. Cache TTL is short — sessions can
# disappear when apps close.
_SESSION_CACHE: Dict[str, Any] = {}
_SESSION_CACHE_REFRESH = 0.0
_SESSION_CACHE_TTL = 4.0  # seconds


def _get_cached_volume(name: str):
    import time as _t
    global _SESSION_CACHE_REFRESH
    if (_t.time() - _SESSION_CACHE_REFRESH) > _SESSION_CACHE_TTL:
        _SESSION_CACHE.clear()
        _SESSION_CACHE_REFRESH = _t.time()
    return _SESSION_CACHE.get(name.lower())


def toggle_app_mute(name: str) -> bool:
    if not _HAS_PYCAW:
        print("[mute] pycaw unavailable")
        return False
    found = 0
    new_state = None
    try:
        sessions = AudioUtilities.GetAllSessions()
        for s in sessions:
            if not s.Process:
                continue
            pname = s.Process.name()
            if pname.lower() == name.lower():
                v = s.SimpleAudioVolume
                cur = bool(v.GetMute())
                want = 0 if cur else 1
                v.SetMute(want, None)
                new_state = bool(want)
                found += 1
        if found == 0:
            avail = sorted({s.Process.name() for s in sessions if s.Process})
            print(f"[mute] no audio session for '{name}'. Active apps with audio right now: {avail}")
            return False
        print(f"[mute] {name}: {'MUTED' if new_state else 'UNMUTED'} ({found} session(s))")
        return True
    except Exception as e:
        print(f"[mute] error on '{name}': {e}")
        return False


def set_master_volume(volume: float):
    if not _HAS_PYCAW:
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
    m = {
        "media_play_pause": Key.media_play_pause,
        "media_next": Key.media_next,
        "media_prev": Key.media_previous,
        "media_stop": Key.media_stop,
    }
    k = m.get(action)
    if k:
        _kbd.press(k); _kbd.release(k)


# ============================================================
# MIDI BACKENDS
# ============================================================
class MidiBackend:
    name = "abstract"

    def list_inputs(self) -> List[str]:
        raise NotImplementedError

    def open(self, port_name: str, on_msg) -> bool:
        """Open input port, run blocking; call on_msg(Msg) for each event. Returns when port closes."""
        raise NotImplementedError


# -- A) python-rtmidi via mido ----------------------------------
class MidoBackend(MidiBackend):
    def __init__(self, sub):
        import mido
        self.mido = mido
        mido.set_backend(f"mido.backends.{sub}")
        self.name = sub

    def list_inputs(self):
        return list(self.mido.get_input_names())

    def open(self, port_name, on_msg):
        with self.mido.open_input(port_name) as port:
            for msg in port:
                m = self._convert(msg)
                if m is not None:
                    on_msg(m)

    def _convert(self, m):
        if m.type == "control_change":
            return Msg("control_change", channel=m.channel, control=m.control, value=m.value)
        if m.type == "note_on":
            return Msg("note_on", channel=m.channel, note=m.note, velocity=m.velocity)
        if m.type == "note_off":
            return Msg("note_off", channel=m.channel, note=m.note, velocity=m.velocity)
        if m.type == "pitchwheel":
            return Msg("pitchwheel", channel=m.channel, pitch=m.pitch)
        return None


# -- B) Pure-Python winmm.dll backend ---------------------------
class WinmmBackend(MidiBackend):
    """
    Pure-ctypes MIDI input using Windows multimedia API. Needs nothing installed.
    """
    name = "winmm"
    MIM_DATA = 0x3C3
    MMSYSERR_NOERROR = 0
    CALLBACK_FUNCTION = 0x00030000

    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("winmm backend is Windows-only")
        self.winmm = ctypes.WinDLL("winmm")
        self.HMIDIIN = wintypes.HANDLE

        class MIDIINCAPSW(ctypes.Structure):
            _fields_ = [
                ("wMid", wintypes.WORD),
                ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.DWORD),
                ("szPname", wintypes.WCHAR * 32),
                ("dwSupport", wintypes.DWORD),
            ]
        self.MIDIINCAPSW = MIDIINCAPSW

        self.MidiInProc = ctypes.WINFUNCTYPE(
            None, self.HMIDIIN, ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t
        )
        self._cb_ref = None  # keep callback alive
        self._handle = None
        self._stop = threading.Event()
        self._on_msg = None

    def _err(self, code, ctx=""):
        if code != self.MMSYSERR_NOERROR:
            buf = ctypes.create_unicode_buffer(256)
            self.winmm.midiInGetErrorTextW(code, buf, 256)
            raise RuntimeError(f"winmm {ctx} err {code}: {buf.value}")

    def list_inputs(self) -> List[str]:
        n = self.winmm.midiInGetNumDevs()
        out = []
        for i in range(n):
            caps = self.MIDIINCAPSW()
            self._err(self.winmm.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)), "GetDevCaps")
            out.append(caps.szPname)
        return out

    def _decode(self, dw_param1: int) -> Optional[Msg]:
        status = dw_param1 & 0xFF
        d1 = (dw_param1 >> 8) & 0xFF
        d2 = (dw_param1 >> 16) & 0xFF
        kind = status & 0xF0
        ch = status & 0x0F
        if kind == 0x90:  # note on
            if d2 == 0:
                return Msg("note_off", channel=ch, note=d1, velocity=0)
            return Msg("note_on", channel=ch, note=d1, velocity=d2)
        if kind == 0x80:  # note off
            return Msg("note_off", channel=ch, note=d1, velocity=d2)
        if kind == 0xB0:  # control change
            return Msg("control_change", channel=ch, control=d1, value=d2)
        if kind == 0xE0:  # pitch wheel
            pitch = ((d2 << 7) | d1) - 8192
            return Msg("pitchwheel", channel=ch, pitch=pitch)
        return None

    def open(self, port_name: str, on_msg):
        # Reset stop flag in case the backend was used before
        self._stop.clear()
        # find device index by name
        device_idx = None
        for i, n in enumerate(self.list_inputs()):
            if n == port_name:
                device_idx = i
                break
        if device_idx is None:
            raise RuntimeError(f"winmm: device '{port_name}' not found in {self.list_inputs()}")

        self._on_msg = on_msg

        def proc(hmi, wMsg, dwInstance, dwParam1, dwParam2):
            try:
                if wMsg == self.MIM_DATA:
                    m = self._decode(int(dwParam1 or 0) & 0xFFFFFFFF)
                    if m is not None and self._on_msg:
                        self._on_msg(m)
                elif wMsg == 0x3C1:   # MIM_OPEN
                    print("[winmm] MIM_OPEN (device acknowledged open)")
                elif wMsg == 0x3C2:   # MIM_CLOSE — informational only, do NOT stop
                    print("[winmm] MIM_CLOSE (informational — ignored)")
                elif wMsg == 0x3C5:   # MIM_ERROR
                    print(f"[winmm] MIM_ERROR raw={dwParam1:#x}")
            except Exception as e:
                print(f"[winmm cb err] {e}")

        self._cb_ref = self.MidiInProc(proc)
        h = self.HMIDIIN()
        rc = self.winmm.midiInOpen(
            ctypes.byref(h), device_idx, self._cb_ref, None, self.CALLBACK_FUNCTION
        )
        if rc != self.MMSYSERR_NOERROR:
            buf = ctypes.create_unicode_buffer(256)
            self.winmm.midiInGetErrorTextW(rc, buf, 256)
            raise RuntimeError(
                f"midiInOpen failed (code {rc}: {buf.value}). "
                "The Launchkey is likely held by another app (Novation Components, DAW, browser MIDI tab). "
                "Close it and try again."
            )
        self._handle = h
        rc = self.winmm.midiInStart(h)
        if rc != self.MMSYSERR_NOERROR:
            self.winmm.midiInClose(h)
            buf = ctypes.create_unicode_buffer(256)
            self.winmm.midiInGetErrorTextW(rc, buf, 256)
            raise RuntimeError(f"midiInStart failed: {buf.value}")

        # Block until stop is set
        import time as _t
        opened_at = _t.time()
        try:
            while not self._stop.wait(0.25):
                pass
            print(f"[winmm] open() returning normally after {_t.time()-opened_at:.1f}s — _stop was set")
        finally:
            try: self.winmm.midiInStop(h)
            except Exception: pass
            try: self.winmm.midiInClose(h)
            except Exception: pass
            self._handle = None

    def stop(self):
        self._stop.set()


def pick_backend() -> MidiBackend:
    # 1) python-rtmidi via mido
    try:
        import rtmidi  # noqa: F401
        import mido  # noqa: F401
        b = MidoBackend("rtmidi")
        print("[MIDI] Backend: python-rtmidi (via mido)")
        return b
    except Exception:
        pass
    # 2) pygame.midi via mido
    try:
        import pygame.midi  # noqa: F401
        import mido  # noqa: F401
        b = MidoBackend("pygame")
        print("[MIDI] Backend: pygame.midi (via mido)")
        return b
    except Exception:
        pass
    # 3) pure ctypes winmm
    if sys.platform == "win32":
        b = WinmmBackend()
        print("[MIDI] Backend: winmm (pure ctypes, no install needed)")
        return b
    print("[FATAL] No MIDI backend available. Install python-rtmidi or pygame, or run on Windows.")
    sys.exit(1)


# ============================================================
# Dispatcher
# ============================================================
class Dispatcher:
    def __init__(self):
        self.mappings: Dict[str, Dict[str, Any]] = {}

    def update_mappings(self, mappings: List[Dict[str, Any]]):
        self.mappings = {m["control_id"]: m for m in mappings}

    def handle(self, control_id: str, msg: Msg):
        m = self.mappings.get(control_id)
        if not m:
            return
        action = m.get("action_type")
        target = m.get("target_app")
        params = m.get("params") or {}

        try:
            if action == "set_volume" and target:
                if msg.type == "control_change":
                    vol = msg.value / 127.0
                elif msg.type == "pitchwheel":
                    vol = (msg.pitch + 8192) / 16383.0
                else:
                    return
                if params.get("invert"):
                    vol = 1.0 - vol
                set_app_volume(target, vol)
                return

            if action == "system_volume" and msg.type == "control_change":
                vol = msg.value / 127.0
                if params.get("invert"):
                    vol = 1.0 - vol
                set_master_volume(vol)
                return

            is_trigger = (
                (msg.type == "note_on" and (msg.velocity or 0) > 0)
                or (msg.type == "control_change" and (msg.value or 0) > 0)
            )
            if not is_trigger:
                return

            if action == "toggle_mute" and target:
                toggle_app_mute(target); return
            if action in ("media_play_pause", "media_next", "media_prev", "media_stop"):
                media_key(action); return
            if action == "volume_step_up" and target:
                step = float(params.get("step", 0.05))
                for s in list_sessions():
                    if s["process_name"].lower() == target.lower():
                        set_app_volume(target, s["volume"] + step); return
            if action == "volume_step_down" and target:
                step = float(params.get("step", 0.05))
                for s in list_sessions():
                    if s["process_name"].lower() == target.lower():
                        set_app_volume(target, s["volume"] - step); return
        except Exception as e:
            print(f"[WARN] dispatch: {e}")


import queue


# ============================================================
# Network client
# ============================================================
class HelperClient:
    def __init__(self, api_url: str, backend: MidiBackend):
        self.api = api_url.rstrip("/")
        self.backend = backend
        self.midi_port_name: Optional[str] = None
        self.device_connected = False
        self.dispatcher = Dispatcher()
        self.stop_evt = threading.Event()
        # Async report pipeline so MIDI events never block on HTTP
        self._report_q: "queue.Queue[dict]" = queue.Queue(maxsize=64)
        # Last value per control (for throttling continuous CCs)
        self._last_sent_at: Dict[str, float] = {}
        # Reusable HTTP session — keep-alive cuts ~50-100ms per request
        self._http = requests.Session()
        self._http.headers.update({"Connection": "keep-alive"})

    def post(self, path, body):
        try:
            r = self._http.post(f"{self.api}/api{path}", json=body, timeout=4)
            if DEBUG:
                print(f"[NET] POST {path} -> {r.status_code}")
            if r.status_code >= 400:
                print(f"[NET] POST {path} HTTP {r.status_code}: {r.text[:200]}")
            return r
        except Exception as e:
            print(f"[NET] POST {path} FAILED: {e}")

    def get(self, path):
        try:
            r = self._http.get(f"{self.api}/api{path}", timeout=4)
            if DEBUG:
                print(f"[NET] GET {path} -> {r.status_code}")
            return r.json()
        except Exception as e:
            print(f"[NET] GET {path} FAILED: {e}")
            return None

    def heartbeat_loop(self):
        first = True
        while not self.stop_evt.is_set():
            r = self.post("/helper/heartbeat", {
                "version": "1.1.0", "midi_port": self.midi_port_name,
                "device_connected": self.device_connected,
            })
            if first and r is not None and r.status_code < 400:
                print(f"[OK] Dashboard reachable: {self.api}")
                first = False
            self.stop_evt.wait(HEARTBEAT_INTERVAL)

    def sessions_loop(self):
        while not self.stop_evt.is_set():
            self.post("/helper/sessions", {"sessions": list_sessions()})
            self.stop_evt.wait(SESSIONS_INTERVAL)

    def state_loop(self):
        while not self.stop_evt.is_set():
            data = self.get("/helper/state")
            if data and "mappings" in data:
                self.dispatcher.update_mappings(data["mappings"])
            self.stop_evt.wait(POLL_INTERVAL)

    def _report(self, msg: Msg, cid: str):
        """Throttled async report — never blocks the MIDI callback."""
        import time as _t
        # Throttle continuous CC / pitch events to max 1 per 50ms per control
        is_continuous = msg.type in ("control_change", "pitchwheel")
        if is_continuous:
            last = self._last_sent_at.get(cid, 0.0)
            if (_t.time() - last) < 0.05:
                return
            self._last_sent_at[cid] = _t.time()
        try:
            self._report_q.put_nowait({
                "control_id": cid, "raw_type": msg.type,
                "channel": msg.channel,
                "number": msg.control if msg.control is not None else msg.note,
                "value": msg.value if msg.value is not None else (msg.velocity if msg.velocity is not None else msg.pitch),
            })
        except queue.Full:
            pass  # drop the report — local action still happened

    def report_loop(self):
        """Drains the report queue in a background thread, never blocks MIDI."""
        while not self.stop_evt.is_set():
            try:
                payload = self._report_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.post("/helper/midi-event", payload)

    def _on_msg(self, msg: Msg):
        cid = control_id_from_msg(msg)
        if not cid:
            return
        # 1) Dispatch the Windows action FIRST (instant, local)
        self.dispatcher.handle(cid, msg)
        # 2) Then queue an async report for the dashboard (never blocks)
        self._report(msg, cid)
        # 3) Print only if not throttled (continuous CCs are noisy)
        if DEBUG or msg.type not in ("control_change", "pitchwheel"):
            self._log_msg(msg, cid)

    def _log_msg(self, msg: Msg, cid: str):
        if msg.type == "control_change":
            raw = f"CC ch={msg.channel} #{msg.control}={msg.value}"
        elif msg.type == "note_on":
            raw = f"NoteOn ch={msg.channel} note={msg.note} vel={msg.velocity}"
        elif msg.type == "note_off":
            raw = f"NoteOff ch={msg.channel} note={msg.note}"
        elif msg.type == "pitchwheel":
            raw = f"Pitch ch={msg.channel} val={msg.pitch}"
        else:
            raw = msg.type
        print(f"[MIDI] {raw}  -> {cid}")

    def _find_launchkey(self) -> Optional[str]:
        try:
            names = self.backend.list_inputs()
        except Exception as e:
            print(f"[MIDI] list_inputs: {e}")
            return None
        # prefer non-DAW port
        for n in names:
            low = n.lower()
            if "launchkey" in low and "incontrol" not in low and "midiin2" not in low:
                return n
        for n in names:
            if "launchkey" in n.lower():
                return n
        # fall back: anything with "midi" if device list is short
        return None

    def midi_loop(self):
        last_port = None
        connect_count = 0
        while not self.stop_evt.is_set():
            port = self._find_launchkey()
            if not port:
                if self.device_connected:
                    print("[MIDI] Launchkey disappeared from device list.")
                self.device_connected = False
                self.midi_port_name = None
                # On first miss, dump all available ports so user can see what's there
                if connect_count == 0:
                    try:
                        all_ports = self.backend.list_inputs()
                        print(f"[MIDI] No Launchkey found. Available MIDI inputs: {all_ports or '(none)'}")
                    except Exception as e:
                        print(f"[MIDI] Could not list ports: {e}")
                self.stop_evt.wait(3)
                continue
            self.midi_port_name = port
            self.device_connected = True
            connect_count += 1
            if port != last_port:
                print(f"[MIDI] Opening: {port}")
                last_port = port
            else:
                print(f"[MIDI] Reopening ({connect_count}): {port}")
            try:
                self.backend.open(port, self._on_msg)
                # If open() returned cleanly without stop being set, that means the
                # device went away or another app took it.
                if not self.stop_evt.is_set():
                    print("[MIDI] Port closed unexpectedly (device unplugged or claimed by another app).")
            except Exception as e:
                print(f"[MIDI] Open failed: {e}")
            self.device_connected = False
            if not self.stop_evt.is_set():
                self.stop_evt.wait(2)

    def run(self):
        threads = [
            threading.Thread(target=self.heartbeat_loop, daemon=True),
            threading.Thread(target=self.sessions_loop, daemon=True),
            threading.Thread(target=self.state_loop, daemon=True),
            threading.Thread(target=self.midi_loop, daemon=True),
            threading.Thread(target=self.report_loop, daemon=True),
            threading.Thread(target=self.report_loop, daemon=True),  # 2 workers for snappier dashboard updates
        ]
        for t in threads:
            t.start()
        print(f"[Launchkey Mixer] Helper running. Dashboard: {self.api}")
        try:
            while not self.stop_evt.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down.")
            self.stop_evt.set()
            if isinstance(self.backend, WinmmBackend):
                self.backend.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=API_URL_DEFAULT, help="Dashboard base URL")
    ap.add_argument("--list-ports", action="store_true", help="List MIDI input ports and exit")
    ap.add_argument("--debug", action="store_true", help="Print every API call")
    args = ap.parse_args()
    global DEBUG
    DEBUG = args.debug
    print(f"[Launchkey Mixer] API URL: {args.api}")
    if "localhost" in args.api or "127.0.0.1" in args.api:
        print("[WARN] API URL is localhost — pass --api https://YOUR-APP.preview.emergentagent.com")
    backend = pick_backend()
    if args.list_ports:
        print("\nMIDI input ports:")
        for n in backend.list_inputs():
            print(f"  - {n}")
        return
    HelperClient(args.api, backend).run()


if __name__ == "__main__":
    main()
