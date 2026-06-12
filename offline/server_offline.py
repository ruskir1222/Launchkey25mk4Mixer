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

from fastapi import FastAPI, APIRouter, HTTPException, Response, Request
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
_log_handlers = [logging.StreamHandler()]
try:
    _log_handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
except Exception:
    pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_log_handlers,
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
}
MAX_EVENTS = 200


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


def run_with_tray(url: str):
    """Run uvicorn in a thread and a pystray icon on the main thread."""
    import pystray
    from pystray import MenuItem as Item, Menu

    icon_image = _build_tray_icon_image()

    server_thread = threading.Thread(
        target=lambda: uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning"),
        daemon=True,
        name="uvicorn-server",
    )
    server_thread.start()

    def on_open(icon, item):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def on_quit(icon, item):
        log.info("Tray quit requested — shutting down.")
        icon.stop()
        os._exit(0)  # daemon threads will be killed

    menu = Menu(
        Item("Open Dashboard", on_open, default=True),
        Item("Quit", on_quit),
    )
    icon = pystray.Icon("launchkey-mixer", icon_image, "Launchkey Mixer", menu)
    log.info("Running in system tray. Right-click the tray icon for options.")
    icon.run()  # blocks until on_quit


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
def main():
    init_db()
    ensure_default_profile()
    mount_static()

    url = f"http://127.0.0.1:{PORT}"
    log.info("Launchkey Mixer (offline) starting on %s", url)
    log.info("Data dir: %s", data_dir())

    # Open the browser shortly after the server is up
    def open_browser_later():
        import time
        time.sleep(1.0)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=open_browser_later, daemon=True).start()

    # Spawn the helper (MIDI + Windows audio). Safe no-op on non-Windows.
    start_helper_thread()

    # Prefer tray mode (windowed); fall back to plain console if pystray missing.
    try:
        import pystray  # noqa: F401
        import PIL  # noqa: F401
        run_with_tray(url)
        return
    except Exception as e:
        log.warning("Tray unavailable (%s) — running in console mode.", e)

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")


if __name__ == "__main__":
    main()
