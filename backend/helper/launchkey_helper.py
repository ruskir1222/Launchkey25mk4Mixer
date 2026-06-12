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


def set_mute(name: str, mute: bool) -> bool:
    """Set absolute mute state (used by 'while held' triggers)."""
    if not _HAS_PYCAW:
        return False
    found = 0
    try:
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower() == name.lower():
                s.SimpleAudioVolume.SetMute(1 if mute else 0, None)
                found += 1
        if found:
            print(f"[mute] {name}: {'MUTED' if mute else 'UNMUTED'} (held)")
        return found > 0
    except Exception as e:
        print(f"[mute] set_mute error: {e}")
        return False



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
# App launching / killing / shell / keystrokes
# ============================================================
import subprocess
import shlex
import webbrowser


def launch_app(path_or_cmd: str) -> bool:
    """Start an executable, document, or URL handler. Uses shell so .lnk shortcuts,
    Start-menu names, full paths and Windows app aliases (e.g. `notepad`, `code`,
    `spotify:`) all work."""
    if not path_or_cmd:
        print("[launch] no path/command provided")
        return False
    try:
        # os.startfile is the most permissive on Windows
        if sys.platform == "win32":
            import os as _os
            # If it looks like a URL or registered scheme, use startfile/webbrowser
            if "://" in path_or_cmd:
                webbrowser.open(path_or_cmd)
                print(f"[launch] URL: {path_or_cmd}")
                return True
            try:
                _os.startfile(path_or_cmd)  # type: ignore[attr-defined]
                print(f"[launch] started: {path_or_cmd}")
                return True
            except Exception:
                # Fall through to subprocess
                pass
        subprocess.Popen(path_or_cmd, shell=True)
        print(f"[launch] spawned: {path_or_cmd}")
        return True
    except Exception as e:
        print(f"[launch] error '{path_or_cmd}': {e}")
        return False


def kill_app(process_name: str) -> bool:
    """Force-close all processes with the given exe name (e.g. 'chrome.exe')."""
    if not process_name:
        return False
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["taskkill", "/F", "/IM", process_name],
                capture_output=True, text=True
            )
            ok = r.returncode == 0
            msg = (r.stdout or r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else ""
            print(f"[kill] {process_name}: {'OK' if ok else 'FAIL'} {msg}")
            return ok
        else:
            r = subprocess.run(["pkill", "-f", process_name], capture_output=True)
            return r.returncode == 0
    except Exception as e:
        print(f"[kill] error: {e}")
        return False


def open_url(url: str) -> bool:
    if not url:
        return False
    try:
        webbrowser.open(url)
        print(f"[url] opened: {url}")
        return True
    except Exception as e:
        print(f"[url] error: {e}")
        return False


def run_command(cmd: str) -> bool:
    """Run an arbitrary shell command (DETACHED). Use for power-user macros."""
    if not cmd:
        return False
    try:
        subprocess.Popen(cmd, shell=True)
        print(f"[cmd] ran: {cmd}")
        return True
    except Exception as e:
        print(f"[cmd] error: {e}")
        return False


# Keystroke combo. Format: "ctrl+shift+m" or "alt+f4" or "win+d" or "f5" or "cmd+`"
_SPECIAL_KEYS = {
    "ctrl": Key.ctrl if _kbd else None,
    "control": Key.ctrl if _kbd else None,
    "shift": Key.shift if _kbd else None,
    "alt": Key.alt if _kbd else None,
    "win": Key.cmd if _kbd else None,
    "cmd": Key.cmd if _kbd else None,
    "super": Key.cmd if _kbd else None,
    "esc": Key.esc if _kbd else None,
    "escape": Key.esc if _kbd else None,
    "enter": Key.enter if _kbd else None,
    "return": Key.enter if _kbd else None,
    "tab": Key.tab if _kbd else None,
    "space": Key.space if _kbd else None,
    "backspace": Key.backspace if _kbd else None,
    "delete": Key.delete if _kbd else None,
    "del": Key.delete if _kbd else None,
    "home": Key.home if _kbd else None,
    "end": Key.end if _kbd else None,
    "pageup": Key.page_up if _kbd else None,
    "pagedown": Key.page_down if _kbd else None,
    "up": Key.up if _kbd else None,
    "down": Key.down if _kbd else None,
    "left": Key.left if _kbd else None,
    "right": Key.right if _kbd else None,
    **{f"f{i}": getattr(Key, f"f{i}") if _kbd else None for i in range(1, 13)},
}


def send_keystroke(combo: str) -> bool:
    if _kbd is None:
        print("[keys] pynput unavailable")
        return False
    if not combo:
        return False
    try:
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        held = []
        last = None
        for p in parts:
            k = _SPECIAL_KEYS.get(p)
            if k is not None:
                held.append(k)
            elif len(p) == 1:
                last = p
            else:
                # Multi-char that isn't a known special — treat as literal sequence
                last = p
        # Press modifiers, tap last, release modifiers
        for k in held:
            _kbd.press(k)
        if last:
            if len(last) == 1:
                _kbd.press(last); _kbd.release(last)
            else:
                _kbd.type(last)
        for k in reversed(held):
            _kbd.release(k)
        print(f"[keys] {combo}")
        return True
    except Exception as e:
        print(f"[keys] error '{combo}': {e}")
        return False


# ============================================================
# MIDI OUTPUT (Windows winmm) — for RGB pad LED feedback
# ============================================================
class MidiOut:
    """Pure-ctypes MIDI output. Used to light pads on the Launchkey."""
    MMSYSERR_NOERROR = 0

    def __init__(self):
        self.winmm = ctypes.WinDLL("winmm") if sys.platform == "win32" else None
        self._handle = wintypes.HANDLE() if self.winmm else None
        self.opened = False

    def list_outputs(self) -> List[str]:
        if not self.winmm:
            return []
        n = self.winmm.midiOutGetNumDevs()
        out = []
        class MIDIOUTCAPSW(ctypes.Structure):
            _fields_ = [
                ("wMid", wintypes.WORD),
                ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.DWORD),
                ("szPname", wintypes.WCHAR * 32),
                ("wTechnology", wintypes.WORD),
                ("wVoices", wintypes.WORD),
                ("wNotes", wintypes.WORD),
                ("wChannelMask", wintypes.WORD),
                ("dwSupport", wintypes.DWORD),
            ]
        for i in range(n):
            caps = MIDIOUTCAPSW()
            if self.winmm.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                out.append(caps.szPname)
        return out

    def open(self, port_name_substring: str = "launchkey") -> bool:
        if not self.winmm:
            print("[LED] Not Windows — output disabled.")
            return False
        ports = self.list_outputs()
        print(f"[LED] Available MIDI OUT ports: {ports or '(none)'}")
        candidates = [p for p in ports if port_name_substring.lower() in p.lower()]
        if not candidates:
            print(f"[LED] No output port containing '{port_name_substring}'.")
            return False
        # Prefer DAW port for LEDs on MK3/MK4; fallback to main.
        chosen = None
        for needle in ("daw", "midiout2", "midiin2", "incontrol"):
            for p in candidates:
                if needle in p.lower():
                    chosen = p; break
            if chosen: break
        if not chosen:
            chosen = candidates[0]
        return self._open_index(chosen, ports)

    def _open_index(self, port_name: str, ports: List[str]) -> bool:
        idx = ports.index(port_name)
        h = wintypes.HANDLE()
        rc = self.winmm.midiOutOpen(ctypes.byref(h), idx, None, None, 0)
        if rc != self.MMSYSERR_NOERROR:
            print(f"[LED] midiOutOpen '{port_name}' failed code {rc}")
            return False
        self._handle = h
        self.opened = True
        print(f"[LED] Output opened: {port_name}")
        return True

    def close(self):
        if self.opened and self.winmm:
            try: self.winmm.midiOutClose(self._handle)
            except Exception: pass
        self.opened = False

    def send_short(self, status: int, data1: int, data2: int):
        if not self.opened or not self.winmm:
            return
        msg = (status & 0xFF) | ((data1 & 0xFF) << 8) | ((data2 & 0xFF) << 16)
        self.winmm.midiOutShortMsg(self._handle, ctypes.c_uint(msg))

    def send_sysex(self, data: bytes):
        """Send a SysEx message via midiOutLongMsg."""
        if not self.opened or not self.winmm:
            return
        class MIDIHDR(ctypes.Structure):
            _fields_ = [
                ("lpData", ctypes.c_char_p),
                ("dwBufferLength", wintypes.DWORD),
                ("dwBytesRecorded", wintypes.DWORD),
                ("dwUser", ctypes.c_void_p),
                ("dwFlags", wintypes.DWORD),
                ("lpNext", ctypes.c_void_p),
                ("reserved", ctypes.c_void_p),
                ("dwOffset", wintypes.DWORD),
                ("dwReserved", ctypes.c_void_p * 8),
            ]
        buf = ctypes.create_string_buffer(data, len(data))
        hdr = MIDIHDR()
        hdr.lpData = ctypes.cast(buf, ctypes.c_char_p)
        hdr.dwBufferLength = len(data)
        hdr.dwBytesRecorded = len(data)
        hdr.dwFlags = 0
        try:
            self.winmm.midiOutPrepareHeader(self._handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
            self.winmm.midiOutLongMsg(self._handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
            # midiOutLongMsg is async; small busy-wait so the buffer outlives the call
            import time as _t
            for _ in range(20):
                if hdr.dwFlags & 0x00000001:  # MHDR_DONE
                    break
                _t.sleep(0.005)
            self.winmm.midiOutUnprepareHeader(self._handle, ctypes.byref(hdr), ctypes.sizeof(hdr))
        except Exception as e:
            print(f"[LED] sysex error: {e}")

    def enter_daw_mode(self):
        """Tell the Launchkey to accept host-driven pad LED commands.
        Tries published SysEx for MK3, MK4, MK4 Mini. Harmless if device ignores it."""
        # Format: F0 00 20 29 02 <product> 10 <on=1/off=0> F7
        for product in (0x0F, 0x14, 0x13, 0x11, 0x12):
            self.send_sysex(bytes([0xF0, 0x00, 0x20, 0x29, 0x02, product, 0x10, 0x01, 0xF7]))
        print("[LED] Sent DAW-mode SysEx (MK3 / MK4 / Mini MK4 variants).")
        # Some MK4 Minis also want a "host mode" handshake — send the
        # generic Novation "enable host control" SysEx as well.
        self.send_sysex(bytes([0xF0, 0x00, 0x20, 0x29, 0x02, 0x13, 0x0A, 0x7F, 0x7F, 0xF7]))

    def exit_daw_mode(self):
        for product in (0x0F, 0x14, 0x13, 0x11, 0x12):
            self.send_sysex(bytes([0xF0, 0x00, 0x20, 0x29, 0x02, product, 0x10, 0x00, 0xF7]))

    def light_pad(self, midi_note: int, color: int, channel: int = 9):
        """Light a pad using ALL known protocols at once. Whichever the device
        listens to wins; the rest are ignored."""
        c = color & 0x7F
        n = midi_note & 0x7F
        # Note On — drum channel (MK3 / many MK4 modes)
        self.send_short(0x90 | (channel & 0x0F), n, c)
        # Note On — InControl channel 16 (idx 15) — used by some MK3 modes
        self.send_short(0x9F, n, c)
        # Note On — channel 1 (idx 0) — used by some MK4 Mini Custom modes
        self.send_short(0x90, n, c)
        # SysEx static color set — MK4 / MK4 Mini explicit
        # F0 00 20 29 02 <product> 03 <behaviour=0 static> <pad note> <color> F7
        for product in (0x14, 0x13, 0x0F):
            self.send_sysex(bytes([
                0xF0, 0x00, 0x20, 0x29, 0x02, product, 0x03, 0x00, n, c, 0xF7
            ]))


# Novation palette short-list (MK3 / MK4 friendly)
PAD_COLORS = {
    "off": 0, "white": 3, "red": 5, "orange": 9, "yellow": 13,
    "green": 21, "cyan": 33, "blue": 41, "purple": 49, "pink": 53,
}


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
        # Multiple ports can be open concurrently; we track their stop events here.
        self._port_stops: List[threading.Event] = []

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
        """Open the named MIDI input port and block until stop() is called.
        Safe to call concurrently for multiple ports — each call holds its
        own ctypes callback, handle and stop event in local variables."""
        # find device index by name
        device_idx = None
        for i, n in enumerate(self.list_inputs()):
            if n == port_name:
                device_idx = i
                break
        if device_idx is None:
            raise RuntimeError(f"winmm: device '{port_name}' not found in {self.list_inputs()}")

        stop = threading.Event()
        self._port_stops.append(stop)

        def proc(hmi, wMsg, dwInstance, dwParam1, dwParam2):
            try:
                if wMsg == self.MIM_DATA:
                    m = self._decode(int(dwParam1 or 0) & 0xFFFFFFFF)
                    if m is not None:
                        on_msg(m)
                elif wMsg == 0x3C5:   # MIM_ERROR
                    print(f"[winmm] MIM_ERROR raw={dwParam1:#x}")
            except Exception as e:
                print(f"[winmm cb err] {e}")

        cb_ref = self.MidiInProc(proc)  # local — keeps callback alive
        h = self.HMIDIIN()
        rc = self.winmm.midiInOpen(
            ctypes.byref(h), device_idx, cb_ref, None, self.CALLBACK_FUNCTION
        )
        if rc != self.MMSYSERR_NOERROR:
            buf = ctypes.create_unicode_buffer(256)
            self.winmm.midiInGetErrorTextW(rc, buf, 256)
            raise RuntimeError(
                f"midiInOpen('{port_name}') failed (code {rc}: {buf.value}). "
                "Port likely held by another app. Close DAW / Novation Components / browser MIDI tabs."
            )
        rc = self.winmm.midiInStart(h)
        if rc != self.MMSYSERR_NOERROR:
            self.winmm.midiInClose(h)
            buf = ctypes.create_unicode_buffer(256)
            self.winmm.midiInGetErrorTextW(rc, buf, 256)
            raise RuntimeError(f"midiInStart('{port_name}') failed: {buf.value}")

        try:
            while not stop.wait(0.25):
                pass
        finally:
            try: self.winmm.midiInStop(h)
            except Exception: pass
            try: self.winmm.midiInClose(h)
            except Exception: pass
            try: self._port_stops.remove(stop)
            except Exception: pass

    def stop(self):
        for ev in list(self._port_stops):
            ev.set()


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
        # Per-control press state. Used so velocity pads behave as clean
        # momentary switches (one event per press/release cycle).
        self._pressed: Dict[str, bool] = {}

    def update_mappings(self, mappings: List[Dict[str, Any]]):
        self.mappings = {m["control_id"]: m for m in mappings}

    def _press_edge(self, control_id: str, msg: Msg) -> Optional[str]:
        """Returns 'press', 'release', or None based on edge detection.
        Filters aftertouch repeats from velocity-sensitive pads."""
        if msg.type == "note_off":
            if self._pressed.get(control_id):
                self._pressed[control_id] = False
                return "release"
            return None
        if msg.type == "note_on":
            is_on = (msg.velocity or 0) > 0
            was = self._pressed.get(control_id, False)
            if is_on and not was:
                self._pressed[control_id] = True
                return "press"
            if not is_on and was:
                self._pressed[control_id] = False
                return "release"
            return None  # repeat / aftertouch — swallow
        if msg.type == "control_change":
            is_on = (msg.value or 0) > 0
            was = self._pressed.get(control_id, False)
            if is_on and not was:
                self._pressed[control_id] = True
                return "press"
            if not is_on and was:
                self._pressed[control_id] = False
                return "release"
            return None
        return None

    def handle(self, control_id: str, msg: Msg) -> bool:
        m = self.mappings.get(control_id)
        if not m:
            return False
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
                    return False
                if params.get("invert"):
                    vol = 1.0 - vol
                set_app_volume(target, vol)
                return True

            if action == "system_volume" and msg.type == "control_change":
                vol = msg.value / 127.0
                if params.get("invert"):
                    vol = 1.0 - vol
                set_master_volume(vol)
                return True

            # ---- Trigger actions (momentary-switch edge-detected) ----
            edge = self._press_edge(control_id, msg)
            trigger_on = (params.get("trigger_on") or "press").lower()  # press | release | while_held
            if edge is None:
                return False

            # while_held: fire action on press, fire the "opposite" on release.
            # Currently only toggle_mute has an obvious opposite; for other
            # actions while_held behaves the same as press.
            if trigger_on == "press" and edge != "press":
                return False
            if trigger_on == "release" and edge != "release":
                return False
            if trigger_on == "while_held":
                if edge not in ("press", "release"):
                    return False
                # For mute: press -> mute, release -> unmute
                if action == "toggle_mute" and target:
                    set_mute(target, edge == "press")
                    return True
                # For others, fall through to fire once on press, skip release
                if edge == "release":
                    return False

            if action == "toggle_mute" and target:
                toggle_app_mute(target); return True
            if action in ("media_play_pause", "media_next", "media_prev", "media_stop"):
                media_key(action); return True
            if action == "launch_app":
                launch_app(params.get("path") or target or ""); return True
            if action == "kill_app":
                kill_app(params.get("process") or target or ""); return True
            if action == "open_url":
                open_url(params.get("url") or target or ""); return True
            if action == "send_keystroke":
                send_keystroke(params.get("keys") or ""); return True
            if action == "run_command":
                run_command(params.get("command") or ""); return True
            if action == "volume_step_up" and target:
                step = float(params.get("step", 0.05))
                for s in list_sessions():
                    if s["process_name"].lower() == target.lower():
                        set_app_volume(target, s["volume"] + step); return True
                return False
            if action == "volume_step_down" and target:
                step = float(params.get("step", 0.05))
                for s in list_sessions():
                    if s["process_name"].lower() == target.lower():
                        set_app_volume(target, s["volume"] - step); return True
                return False
        except Exception as e:
            print(f"[WARN] dispatch: {e}")
            return False
        return False


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
        # MIDI output for RGB LED feedback (best-effort)
        self._midi_out = MidiOut()
        self._led_opened_once = False
        # Learned (channel, note) per control_id from incoming events, so LEDs
        # can be targeted at whatever notes the device is actually using right now.
        self._physical_pads: Dict[str, tuple] = {}

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

    def led_init_loop(self):
        """Dedicated thread: aggressively (re)opens MIDI out for LED feedback."""
        import time as _t
        attempts = 0
        # Wait briefly for midi_loop to discover the device
        _t.sleep(1.5)
        while not self.stop_evt.is_set():
            if not self._midi_out.opened:
                print(f"[LED] init attempt #{attempts + 1}…")
                ok = self._midi_out.open("launchkey")
                if ok:
                    self._midi_out.enter_daw_mode()
                    # Light all 16 pads briefly to verify
                    print("[LED] Running blink test on all 16 pads (cyan)…")
                    for n in range(36, 52):
                        self._midi_out.light_pad(n, 33)  # cyan
                    _t.sleep(0.8)
                    for n in range(36, 52):
                        self._midi_out.light_pad(n, 0)   # off
                    print("[LED] Blink test done. LEDs active.")
                else:
                    if attempts == 0:
                        print("[LED] Could not open MIDI output for LED feedback.")
                        print("[LED] Possible reasons: another app holds the DAW port, ")
                        print("[LED] device in non-Custom pad mode, or wrong product ID.")
                attempts += 1
            self.stop_evt.wait(15)   # retry every 15s

    def state_loop(self):
        prev_pad_state = {}
        while not self.stop_evt.is_set():
            data = self.get("/helper/state")
            if data and "mappings" in data:
                self.dispatcher.update_mappings(data["mappings"])
                if self._midi_out.opened:
                    self._refresh_pad_leds(data["mappings"], prev_pad_state)
            self.stop_evt.wait(POLL_INTERVAL)

    def _refresh_pad_leds(self, mappings, prev_state):
        """Light pads on the device to reflect their bound state.
        Handles both standard pad-N control IDs and synthetic note-chX-YY IDs
        (from MIDI Learn on non-drum pad modes)."""
        if not self._midi_out.opened:
            return
        # Each light command takes (channel, note, color). Build a list.
        commands = []  # list of (channel, note, color, dedupe_key)

        for m in mappings:
            cid = m.get("control_id") or ""
            ui_alias = m.get("ui_alias") or ""
            params = m.get("params") or {}
            act = m.get("action_type") or ""

            # Pick the color: user override wins
            user_color = params.get("led_color")
            if isinstance(user_color, int) and 0 <= user_color <= 127:
                color = user_color
            else:
                color = PAD_COLORS["orange"]
                if act in ("toggle_mute", "mute"): color = PAD_COLORS["red"]
                elif act == "set_volume": color = PAD_COLORS["green"]
                elif act == "launch_app": color = PAD_COLORS["blue"]
                elif act == "kill_app": color = PAD_COLORS["red"]
                elif act == "open_url": color = PAD_COLORS["cyan"]
                elif act == "send_keystroke": color = PAD_COLORS["purple"]
                elif act == "run_command": color = PAD_COLORS["yellow"]
                elif act.startswith("media_"): color = PAD_COLORS["pink"]

            # Source 1: standard pad-N (or via ui_alias)
            pad_idx = None
            for src in (cid, ui_alias):
                if src.startswith("pad-"):
                    try: pad_idx = int(src.split("-", 1)[1])
                    except: pass
                    break
            if pad_idx and 1 <= pad_idx <= 16:
                note = 43 + pad_idx if 1 <= pad_idx <= 8 else 35 + (pad_idx - 8)
                commands.append((9, note, color, f"pad-{pad_idx}"))
                # Also light any learned alternate note for this UI pad
                learned = self._physical_pads.get(f"pad-{pad_idx}")
                if learned and learned[1] != note:
                    commands.append((learned[0], learned[1], color, f"learned-pad-{pad_idx}"))
                continue

            # Source 2: synthetic note-chN-YY — light THAT note
            m_note = None
            for src in (cid, ui_alias):
                if src.startswith("note-ch"):
                    try:
                        parts = src.split("-")  # ['note','ch9','5']
                        ch = int(parts[1].replace("ch", ""))
                        note = int(parts[2])
                        m_note = (ch, note)
                    except Exception:
                        pass
                    break
            if m_note:
                commands.append((m_note[0], m_note[1], color, f"note-{m_note[0]}-{m_note[1]}"))

        # Diff against prev state
        wanted = {key: (ch, note, color) for ch, note, color, key in commands}
        # Turn OFF anything that was lit and is no longer wanted
        for key, prev in list(prev_state.items()):
            if key not in wanted:
                ch, note, _ = prev
                self._midi_out.send_short(0x90 | (ch & 0x0F), note & 0x7F, 0)
                del prev_state[key]
        # Apply/refresh wanted
        for key, (ch, note, color) in wanted.items():
            if prev_state.get(key) == (ch, note, color):
                continue
            prev_state[key] = (ch, note, color)
            self._midi_out.send_short(0x90 | (ch & 0x0F), note & 0x7F, color & 0x7F)
            # Belt-and-braces for MK4 Mini Custom modes:
            self._midi_out.send_short(0x90, note & 0x7F, color & 0x7F)
            self._midi_out.send_short(0x9F, note & 0x7F, color & 0x7F)
            print(f"[LED] -> ch{ch} note={note} color={color}")

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
        # Remember the (channel, note) any pad-ish event came on, so LEDs
        # can light THAT specific note even if the device is in Session/Scale
        # mode and sending non-standard notes.
        if msg.type in ("note_on", "note_off") and msg.note is not None:
            self._physical_pads[cid] = (msg.channel, msg.note)
        # 1) Dispatch the Windows action FIRST (instant, local)
        had_action = self.dispatcher.handle(cid, msg)
        # 2) Then queue an async report for the dashboard (never blocks)
        self._report(msg, cid)
        # 3) Print: triggers always, continuous only in debug
        if DEBUG or msg.type not in ("control_change", "pitchwheel"):
            self._log_msg(msg, cid, had_action)

    def _log_msg(self, msg: Msg, cid: str, had_action: bool = False):
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
        suffix = "" if had_action else "   (no mapping — use MIDI LEARN on dashboard)"
        print(f"[MIDI] {raw}  -> {cid}{suffix}")

    def _find_launchkey_ports(self) -> List[str]:
        """Returns ALL Launchkey-related ports — main MIDI port + DAW/InControl port.
        Listening to both means we catch knobs/pads/keys AND device-internal buttons
        (Capture, Quantise, Shift, Octave, pad-mode etc.) that travel on the DAW port."""
        try:
            names = self.backend.list_inputs()
        except Exception as e:
            print(f"[MIDI] list_inputs: {e}")
            return []
        return [n for n in names if "launchkey" in n.lower()]

    def midi_loop(self):
        """Spawns a worker thread per Launchkey port. Each worker reopens its
        port if it drops. The set of ports is rescanned every 3 s."""
        active: Dict[str, threading.Thread] = {}
        while not self.stop_evt.is_set():
            ports = self._find_launchkey_ports()
            if not ports:
                if self.device_connected:
                    print("[MIDI] All Launchkey ports disappeared.")
                self.device_connected = False
                self.midi_port_name = None
                try:
                    all_ports = self.backend.list_inputs()
                    print(f"[MIDI] Waiting for Launchkey. Available inputs: {all_ports or '(none)'}")
                except Exception:
                    pass
                self.stop_evt.wait(3)
                continue

            # Reflect connected state
            self.device_connected = True
            # Prefer to display the main MIDI port name (not the DAW one) in the dashboard
            main = next((p for p in ports if "midiin2" not in p.lower() and "incontrol" not in p.lower()), ports[0])
            self.midi_port_name = main

            # Start worker per port if not running
            for port in ports:
                if port in active and active[port].is_alive():
                    continue
                t = threading.Thread(target=self._port_worker, args=(port,), daemon=True, name=f"midi:{port}")
                active[port] = t
                t.start()

            # Tidy stale entries
            for port in list(active.keys()):
                if port not in ports and not active[port].is_alive():
                    del active[port]

            self.stop_evt.wait(3)

    def _port_worker(self, port: str):
        print(f"[MIDI] Listening: {port}")
        try:
            self.backend.open(port, self._on_msg)
        except Exception as e:
            print(f"[MIDI] {port}: {e}")
        print(f"[MIDI] Closed: {port}")

    def run(self):
        threads = [
            threading.Thread(target=self.heartbeat_loop, daemon=True),
            threading.Thread(target=self.sessions_loop, daemon=True),
            threading.Thread(target=self.state_loop, daemon=True),
            threading.Thread(target=self.midi_loop, daemon=True),
            threading.Thread(target=self.report_loop, daemon=True),
            threading.Thread(target=self.report_loop, daemon=True),  # 2 workers for snappier dashboard updates
            threading.Thread(target=self.led_init_loop, daemon=True),
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
            try:
                if self._midi_out.opened:
                    # Turn pad LEDs off
                    for n in range(36, 52):
                        self._midi_out.light_pad(n, 0)
                    self._midi_out.exit_daw_mode()
                    self._midi_out.close()
            except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=API_URL_DEFAULT, help="Dashboard base URL")
    ap.add_argument("--list-ports", action="store_true", help="List MIDI input + output ports and exit")
    ap.add_argument("--debug", action="store_true", help="Print every API call")
    args = ap.parse_args()
    global DEBUG
    DEBUG = args.debug
    print(f"[Launchkey Mixer] API URL: {args.api}")
    if "localhost" in args.api or "127.0.0.1" in args.api:
        print("[WARN] API URL is localhost — pass --api https://YOUR-APP.preview.emergentagent.com")
    backend = pick_backend()
    if args.list_ports:
        print("\nMIDI INPUT ports:")
        for n in backend.list_inputs():
            print(f"  - {n}")
        try:
            mo = MidiOut()
            print("\nMIDI OUTPUT ports:")
            for n in mo.list_outputs():
                print(f"  - {n}")
        except Exception as e:
            print(f"  (output enumeration failed: {e})")
        return
    HelperClient(args.api, backend).run()


if __name__ == "__main__":
    main()
