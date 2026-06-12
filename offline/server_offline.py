"""
Launchkey Mixer — Offline / Standalone Server
=============================================

Single-process app that does everything locally on your Windows PC:
  - FastAPI on http://localhost:8765
  - SQLite for profile/mapping storage (no MongoDB needed)
  - Serves the bundled React dashboard at /
  - Spawns the existing launchkey_helper logic in a background thread

Build into a one-file .exe with build_windows.bat (uses PyInstaller).
"""

import os
import sys
import json
import uuid
import sqlite3
import threading
import webbrowser
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, APIRouter, HTTPException, Response, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
import uvicorn

# These imports are not used directly here but ensure PyInstaller bundles them
# (launchkey_helper is loaded dynamically and its deps aren't statically visible).
import requests  # noqa: F401
try:
    import pycaw  # noqa: F401
    import pycaw.pycaw  # noqa: F401
    import comtypes  # noqa: F401
    import pynput  # noqa: F401
    import pynput.keyboard  # noqa: F401
except Exception:
    pass  # only needed at runtime on Windows; safe to skip on dev machines

# -----------------------------------------------------------------------------
# Resource resolution (works in dev AND inside a PyInstaller --onefile bundle)
# -----------------------------------------------------------------------------
def resource_path(*parts: str) -> Path:
    """Locate a bundled resource regardless of whether we're running from
    source or from a PyInstaller frozen exe."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base, *parts)
    return Path(__file__).parent.joinpath(*parts)


def data_dir() -> Path:
    """Persistent data dir for SQLite DB. Survives across exe runs."""
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home())) / "LaunchkeyMixer"
    else:
        root = Path.home() / ".launchkey-mixer"
    root.mkdir(parents=True, exist_ok=True)
    return root


PORT = int(os.environ.get("LAUNCHKEY_PORT", "8765"))
DB_PATH = data_dir() / "launchkey.db"
STATIC_DIR = resource_path("static")  # populated by build script (yarn build copied here)
HELPER_DIR = resource_path("helper")
LOG_PATH = data_dir() / "launchkey.log"

# Write logs to BOTH stdout (visible in console build) AND a file in %APPDATA%
# so users can debug even when the console is hidden (system-tray build).
# In windowed PyInstaller mode sys.stderr/sys.stdout can be None, so we skip
# StreamHandler entirely when that's the case (would otherwise crash logging).
_log_handlers = []
if sys.stderr is not None:
    _log_handlers.append(logging.StreamHandler())
try:
    _log_handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
except Exception:
    pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_log_handlers or None,
)
log = logging.getLogger("launchkey-offline")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -----------------------------------------------------------------------------
# SQLite storage
# -----------------------------------------------------------------------------
_db_lock = threading.RLock()


def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


CONN = db_conn()


def init_db():
    with _db_lock:
        CONN.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mappings (
                id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                control_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target_app TEXT,
                params TEXT NOT NULL DEFAULT '{}',
                label TEXT,
                ui_alias TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(profile_id, control_id)
            );
            """
        )


def ensure_default_profile() -> Dict[str, Any]:
    with _db_lock:
        row = CONN.execute("SELECT * FROM profiles WHERE is_active=1 LIMIT 1").fetchone()
        if row:
            return dict(row, is_active=bool(row["is_active"]))
        row = CONN.execute("SELECT * FROM profiles LIMIT 1").fetchone()
        if row:
            CONN.execute("UPDATE profiles SET is_active=1 WHERE id=?", (row["id"],))
            return dict(row, is_active=True)
        pid = str(uuid.uuid4())
        CONN.execute(
            "INSERT INTO profiles(id,name,is_active,created_at) VALUES(?,?,?,?)",
            (pid, "Default", 1, now_iso()),
        )
        return {"id": pid, "name": "Default", "is_active": True, "created_at": now_iso()}


def profile_row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": r["id"],
        "name": r["name"],
        "is_active": bool(r["is_active"]),
        "created_at": r["created_at"],
    }


def mapping_row_to_dict(r: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": r["id"],
        "profile_id": r["profile_id"],
        "control_id": r["control_id"],
        "action_type": r["action_type"],
        "target_app": r["target_app"],
        "params": json.loads(r["params"] or "{}"),
        "label": r["label"],
        "ui_alias": r["ui_alias"],
        "updated_at": r["updated_at"],
    }


# -----------------------------------------------------------------------------
# Pydantic models (mirror /app/backend/server.py exactly so the frontend works)
# -----------------------------------------------------------------------------
class ProfileCreate(BaseModel):
    name: str


class MappingUpsert(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action_type: str
    target_app: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    label: Optional[str] = None
    ui_alias: Optional[str] = None


class HelperHeartbeat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    version: Optional[str] = None
    midi_port: Optional[str] = None
    device_connected: bool = False


class AudioSession(BaseModel):
    process_name: str
    display_name: Optional[str] = None
    volume: float = 0.0
    muted: bool = False
    pid: Optional[int] = None


class SessionsReport(BaseModel):
    sessions: List[AudioSession]


class MidiEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    control_id: str
    raw_type: Optional[str] = None
    channel: Optional[int] = None
    number: Optional[int] = None
    value: Optional[int] = None
    timestamp: str = Field(default_factory=now_iso)


# -----------------------------------------------------------------------------
# In-memory ephemeral telemetry (same shape as cloud server)
# -----------------------------------------------------------------------------
state: Dict[str, Any] = {
    "helper_last_seen": None,
    "helper_info": {},
    "sessions": [],
    "sessions_updated": None,
    "midi_events": [],
    # Browser-extension state
    "browser_tabs": [],          # list of {tabId, title, url, audible, muted, windowId, favIconUrl}
    "browser_updated": None,
    "browser_connected": False,
}
MAX_EVENTS = 200

# Active browser WebSocket connections (one per extension instance)
_browser_ws: "List[WebSocket]" = []
_browser_lock = threading.Lock()


# -----------------------------------------------------------------------------
# FastAPI app & routes
# -----------------------------------------------------------------------------
app = FastAPI(title="Launchkey Mixer (Offline)")
api = APIRouter(prefix="/api")


# ---------- Profiles ----------
@api.get("/profiles")
def list_profiles():
    ensure_default_profile()
    with _db_lock:
        rows = CONN.execute("SELECT * FROM profiles ORDER BY created_at ASC").fetchall()
    return [profile_row_to_dict(r) for r in rows]


@api.post("/profiles")
def create_profile(body: ProfileCreate):
    p = {"id": str(uuid.uuid4()), "name": body.name, "is_active": False, "created_at": now_iso()}
    with _db_lock:
        CONN.execute(
            "INSERT INTO profiles(id,name,is_active,created_at) VALUES(?,?,?,?)",
            (p["id"], p["name"], 0, p["created_at"]),
        )
    return p


@api.post("/profiles/{profile_id}/activate")
def activate_profile(profile_id: str):
    with _db_lock:
        row = CONN.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Profile not found")
        CONN.execute("UPDATE profiles SET is_active=0")
        CONN.execute("UPDATE profiles SET is_active=1 WHERE id=?", (profile_id,))
        row = CONN.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
    return profile_row_to_dict(row)


@api.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str):
    with _db_lock:
        row = CONN.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Profile not found")
        count = CONN.execute("SELECT COUNT(*) as c FROM profiles").fetchone()["c"]
        if count <= 1:
            raise HTTPException(400, "Cannot delete last profile")
        CONN.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        CONN.execute("DELETE FROM mappings WHERE profile_id=?", (profile_id,))
        if row["is_active"]:
            other = CONN.execute("SELECT id FROM profiles LIMIT 1").fetchone()
            if other:
                CONN.execute("UPDATE profiles SET is_active=1 WHERE id=?", (other["id"],))
    return {"ok": True}


# ---------- Mappings ----------
@api.get("/profiles/{profile_id}/mappings")
def list_mappings(profile_id: str):
    with _db_lock:
        rows = CONN.execute("SELECT * FROM mappings WHERE profile_id=?", (profile_id,)).fetchall()
    return [mapping_row_to_dict(r) for r in rows]


@api.put("/profiles/{profile_id}/mappings/{control_id}")
def upsert_mapping(profile_id: str, control_id: str, body: MappingUpsert):
    with _db_lock:
        prof = CONN.execute("SELECT id FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if not prof:
            raise HTTPException(404, "Profile not found")
        existing = CONN.execute(
            "SELECT id FROM mappings WHERE profile_id=? AND control_id=?",
            (profile_id, control_id),
        ).fetchone()
        mid = existing["id"] if existing else str(uuid.uuid4())
        CONN.execute(
            """
            INSERT INTO mappings(id,profile_id,control_id,action_type,target_app,params,label,ui_alias,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id,control_id) DO UPDATE SET
                action_type=excluded.action_type,
                target_app=excluded.target_app,
                params=excluded.params,
                label=excluded.label,
                ui_alias=excluded.ui_alias,
                updated_at=excluded.updated_at
            """,
            (
                mid,
                profile_id,
                control_id,
                body.action_type,
                body.target_app,
                json.dumps(body.params or {}),
                body.label,
                body.ui_alias,
                now_iso(),
            ),
        )
        row = CONN.execute(
            "SELECT * FROM mappings WHERE profile_id=? AND control_id=?",
            (profile_id, control_id),
        ).fetchone()
    return mapping_row_to_dict(row)


@api.delete("/profiles/{profile_id}/mappings/{control_id}")
def delete_mapping(profile_id: str, control_id: str):
    with _db_lock:
        r = CONN.execute(
            "DELETE FROM mappings WHERE profile_id=? AND control_id=?",
            (profile_id, control_id),
        )
    return {"ok": True, "deleted": r.rowcount}


# ---------- Helper agent telemetry ----------
@api.post("/helper/heartbeat")
def helper_heartbeat(body: HelperHeartbeat):
    state["helper_last_seen"] = now_iso()
    state["helper_info"] = body.model_dump()
    return {"ok": True, "server_time": now_iso()}


@api.get("/helper/status")
def helper_status():
    last = state["helper_last_seen"]
    connected = False
    if last:
        try:
            dt = datetime.fromisoformat(last)
            connected = (datetime.now(timezone.utc) - dt).total_seconds() < 8
        except Exception:
            connected = False
    return {
        "helper_connected": connected,
        "helper_last_seen": last,
        "helper_info": state["helper_info"],
        "sessions_updated": state["sessions_updated"],
    }


@api.get("/helper/state")
def helper_state():
    profile = ensure_default_profile()
    with _db_lock:
        rows = CONN.execute(
            "SELECT * FROM mappings WHERE profile_id=?", (profile["id"],)
        ).fetchall()
    return {
        "active_profile": profile,
        "mappings": [mapping_row_to_dict(r) for r in rows],
        "server_time": now_iso(),
    }


@api.post("/helper/sessions")
def report_sessions(body: SessionsReport):
    state["sessions"] = [s.model_dump() for s in body.sessions]
    state["sessions_updated"] = now_iso()
    return {"ok": True}


@api.get("/helper/sessions")
def get_sessions():
    return {"sessions": state["sessions"], "updated": state["sessions_updated"]}


@api.post("/helper/midi-event")
def report_midi_event(body: MidiEvent):
    state["midi_events"].append(body.model_dump())
    if len(state["midi_events"]) > MAX_EVENTS:
        state["midi_events"] = state["midi_events"][-MAX_EVENTS:]
    return {"ok": True}


@api.get("/helper/midi-events")
def get_midi_events(since: Optional[str] = None, limit: int = 50):
    events = state["midi_events"]
    if since:
        events = [e for e in events if e["timestamp"] > since]
    return {"events": events[-limit:], "latest": events[-1] if events else None}


# ---------- Browser extension API ----------
@api.get("/browser/tabs")
def list_browser_tabs():
    """Return the latest list of tabs reported by the browser extension."""
    return {
        "connected": state["browser_connected"],
        "tabs": state["browser_tabs"],
        "updated": state["browser_updated"],
    }


@api.post("/browser/command")
async def queue_browser_command(payload: Dict[str, Any]):
    """Helper / dashboard calls this to send a command to all connected
    browser extensions. Payload examples:
        {"type": "mute_tab", "selector": "tab:123", "muted": true}
        {"type": "toggle_tab_mute", "selector": "regex:youtube"}
        {"type": "focus_tab", "selector": "tab:456"}
    """
    sent = 0
    dead = []
    for ws in list(_browser_ws):
        try:
            await ws.send_json(payload)
            sent += 1
        except Exception:
            dead.append(ws)
    if dead:
        with _browser_lock:
            for d in dead:
                if d in _browser_ws:
                    _browser_ws.remove(d)
        if not _browser_ws:
            state["browser_connected"] = False
    return {"ok": True, "sent_to": sent}


@app.websocket("/api/browser/ws")
async def browser_ws_endpoint(ws: WebSocket):
    """Persistent WebSocket the browser extension keeps open.
    Extension sends:  {"type":"tabs", "tabs":[...]}
    Server sends back:{"type":"mute_tab", "selector":"...", "muted":true} etc.
    """
    await ws.accept()
    with _browser_lock:
        _browser_ws.append(ws)
    state["browser_connected"] = True
    log.info("Browser extension connected (%d total).", len(_browser_ws))
    try:
        await ws.send_json({"type": "hello", "server": "launchkey-mixer-offline"})
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "tabs":
                state["browser_tabs"] = msg.get("tabs", [])
                state["browser_updated"] = now_iso()
            elif t == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("Browser WS error: %s", e)
    finally:
        with _browser_lock:
            if ws in _browser_ws:
                _browser_ws.remove(ws)
            if not _browser_ws:
                state["browser_connected"] = False
        log.info("Browser extension disconnected.")


# ---------- Helper-script downloads (kept for parity; mostly unused in offline mode) ----------
@api.get("/helper/script")
def download_helper():
    p = HELPER_DIR / "launchkey_helper.py"
    if not p.exists():
        raise HTTPException(404, "Helper script not found")
    return Response(
        content=p.read_text(encoding="utf-8"),
        media_type="text/x-python",
        headers={"Content-Disposition": "attachment; filename=launchkey_helper.py"},
    )


@api.get("/helper/requirements")
def download_requirements():
    p = HELPER_DIR / "requirements.txt"
    if not p.exists():
        raise HTTPException(404, "requirements not found")
    return Response(
        content=p.read_text(encoding="utf-8"),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=requirements.txt"},
    )


@api.get("/helper/install-script")
def download_install_script():
    p = HELPER_DIR / "install_windows.bat"
    if not p.exists():
        raise HTTPException(404, "install script not found")
    return Response(
        content=p.read_text(encoding="utf-8"),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=install_windows.bat"},
    )


@api.get("/")
def api_root():
    return {"service": "launchkey-mixer", "mode": "offline", "status": "ok"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Static frontend ----------
def mount_static():
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        # Serve sub-assets (JS/CSS) at /static, /assets etc. that CRA builds reference
        for sub in ("static", "assets"):
            d = STATIC_DIR / sub
            if d.is_dir():
                app.mount(f"/{sub}", StaticFiles(directory=str(d)), name=sub)

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str, request: Request):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = STATIC_DIR / full_path
            if candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(STATIC_DIR / "index.html"))
    else:
        @app.get("/")
        def no_ui():
            return JSONResponse(
                {
                    "error": "Frontend build not bundled.",
                    "hint": "Run build_windows.bat to build the React UI and package the exe.",
                },
                status_code=503,
            )


# -----------------------------------------------------------------------------
# Background MIDI / audio helper thread
# -----------------------------------------------------------------------------
def start_helper_thread():
    # Make sure we can import launchkey_helper from the bundled helper dir
    helper_dir = str(HELPER_DIR)
    if helper_dir not in sys.path:
        sys.path.insert(0, helper_dir)
    try:
        import launchkey_helper as lk  # noqa: E402
    except Exception as e:
        log.warning("Helper not available (%s) — UI will still work, hardware won't.", e)
        return

    def runner():
        try:
            backend = lk.pick_backend()
            log.info("Helper backend: %s", type(backend).__name__)
            lk.HelperClient(f"http://127.0.0.1:{PORT}", backend).run()
        except Exception as e:
            log.exception("Helper thread crashed: %s", e)

    t = threading.Thread(target=runner, daemon=True, name="launchkey-helper")
    t.start()


# -----------------------------------------------------------------------------
# System tray icon (optional — graceful no-op if pystray/Pillow missing)
# -----------------------------------------------------------------------------
def _build_tray_icon_image():
    """Generate a simple icon programmatically so we don't ship an image file."""
    from PIL import Image, ImageDraw
    size = 64
    img = Image.new("RGB", (size, size), (15, 15, 18))
    d = ImageDraw.Draw(img)
    # Orange "LK" badge on dark background — matches dashboard accent color.
    d.rectangle([6, 6, size - 6, size - 6], outline=(255, 102, 0), width=3)
    d.text((14, 14), "LK", fill=(255, 102, 0))
    # A second pass with bigger pseudo-font: draw a stylized knob shape
    d.ellipse([20, 22, 44, 46], outline=(255, 102, 0), width=2)
    d.line([32, 28, 32, 35], fill=(255, 102, 0), width=2)
    return img


def _open_browser(url: str):
    """Open the dashboard in the default browser. Uses os.startfile on Windows
    (more reliable than webbrowser.open from a windowed PyInstaller exe)."""
    try:
        if sys.platform == "win32":
            os.startfile(url)
        else:
            webbrowser.open(url)
    except Exception as e:
        log.warning("Failed to open browser: %s", e)


def run_with_tray(url: str):
    """Run a pystray icon in a background thread (so uvicorn can own the main
    thread for clean asyncio + signal handling on Windows)."""
    try:
        import pystray
        from pystray import MenuItem as Item, Menu
    except Exception as e:
        log.warning("pystray unavailable (%s) — no tray icon will be shown.", e)
        return None

    icon_image = _build_tray_icon_image()

    icon = pystray.Icon("launchkey-mixer", icon_image, "Launchkey Mixer")

    def on_open(icon_, item):
        _open_browser(url)

    def on_quit(icon_, item):
        log.info("Tray quit requested — shutting down.")
        icon_.stop()
        os._exit(0)

    icon.menu = Menu(
        Item("Open Dashboard", on_open, default=True),
        Item("Quit", on_quit),
    )

    t = threading.Thread(target=icon.run, daemon=True, name="systray")
    t.start()
    log.info("System-tray icon spawned in background.")
    return icon


# -----------------------------------------------------------------------------
# Single-instance lock
# -----------------------------------------------------------------------------
def acquire_single_instance(url: str) -> bool:
    """Try to bind the configured port. If it's already taken, assume another
    instance of Launchkey Mixer is running, open the dashboard tab on that
    one, and exit. Returns True if we acquired (we're first); False otherwise.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind(("127.0.0.1", PORT))
    except OSError:
        log.warning("Port %s already in use — another Launchkey Mixer instance "
                    "is probably running. Opening its dashboard.", PORT)
        _open_browser(url)
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass
    return True


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
def main():
    url = f"http://127.0.0.1:{PORT}"
    if not acquire_single_instance(url):
        sys.exit(0)

    init_db()
    ensure_default_profile()
    mount_static()

    log.info("Launchkey Mixer (offline) starting on %s", url)
    log.info("Data dir: %s", data_dir())

    # Open the browser shortly after the server is up
    def open_browser_later():
        import time
        # Wait long enough for uvicorn to bind the port (~2s is safe for cold start)
        time.sleep(2.0)
        _open_browser(url)

    threading.Thread(target=open_browser_later, daemon=True).start()

    # Spawn the helper (MIDI + Windows audio). Safe no-op on non-Windows.
    start_helper_thread()

    # Spawn tray icon in a background thread (doesn't block uvicorn).
    run_with_tray(url)

    # Run uvicorn on the main thread — keeps signal handling + asyncio happy.
    try:
        log.info("Uvicorn starting on 127.0.0.1:%s", PORT)
        # Pass log_config=None so uvicorn doesn't install its own handlers
        # (which would crash in windowed PyInstaller mode where sys.stderr=None).
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
            log_config=None,
            access_log=False,
        )
    except Exception as e:
        log.exception("Uvicorn crashed: %s", e)
        raise


if __name__ == "__main__":
    main()
