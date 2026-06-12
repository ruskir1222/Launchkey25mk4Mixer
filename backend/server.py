from fastapi import FastAPI, APIRouter, HTTPException, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Launchkey Mixer API")
api_router = APIRouter(prefix="/api")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- Models ----------
class Profile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    is_active: bool = False
    created_at: str = Field(default_factory=now_iso)


class ProfileCreate(BaseModel):
    name: str


class Mapping(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    profile_id: str
    control_id: str  # e.g. knob-1, pad-3, key-12, transport-play, mod-wheel
    action_type: str  # set_volume | toggle_mute | media_play_pause | media_next | media_prev | media_stop | system_volume | volume_step_up | volume_step_down | app_mute
    target_app: Optional[str] = None  # process name e.g. "chrome.exe", or "__focused__", or "__master__"
    params: Dict[str, Any] = Field(default_factory=dict)
    label: Optional[str] = None
    ui_alias: Optional[str] = None  # render this mapping at this UI position
    updated_at: str = Field(default_factory=now_iso)


class MappingUpsert(BaseModel):
    action_type: str
    target_app: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    label: Optional[str] = None
    ui_alias: Optional[str] = None


class AudioSession(BaseModel):
    process_name: str
    display_name: Optional[str] = None
    volume: float = 0.0  # 0..1
    muted: bool = False
    pid: Optional[int] = None


class SessionsReport(BaseModel):
    sessions: List[AudioSession]


class MidiEvent(BaseModel):
    control_id: str
    raw_type: Optional[str] = None  # cc | note_on | note_off | pitch | program
    channel: Optional[int] = None
    number: Optional[int] = None
    value: Optional[int] = None
    timestamp: str = Field(default_factory=now_iso)


class HelperHeartbeat(BaseModel):
    version: Optional[str] = None
    midi_port: Optional[str] = None
    device_connected: bool = False


# ---------- In-memory ephemeral state (helper telemetry) ----------
state: Dict[str, Any] = {
    "helper_last_seen": None,
    "helper_info": {},
    "sessions": [],
    "sessions_updated": None,
    "midi_events": [],  # ring buffer
}
MAX_EVENTS = 200


# ---------- Helpers ----------
async def ensure_default_profile():
    existing = await db.profiles.find_one({"is_active": True}, {"_id": 0})
    if existing:
        return existing
    any_p = await db.profiles.find_one({}, {"_id": 0})
    if any_p:
        await db.profiles.update_one({"id": any_p["id"]}, {"$set": {"is_active": True}})
        any_p["is_active"] = True
        return any_p
    p = Profile(name="Default", is_active=True)
    await db.profiles.insert_one(p.model_dump())
    return p.model_dump()


# ---------- Profile routes ----------
@api_router.get("/profiles", response_model=List[Profile])
async def list_profiles():
    await ensure_default_profile()
    docs = await db.profiles.find({}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    return docs


@api_router.post("/profiles", response_model=Profile)
async def create_profile(body: ProfileCreate):
    p = Profile(name=body.name)
    await db.profiles.insert_one(p.model_dump())
    return p


@api_router.post("/profiles/{profile_id}/activate", response_model=Profile)
async def activate_profile(profile_id: str):
    p = await db.profiles.find_one({"id": profile_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Profile not found")
    await db.profiles.update_many({}, {"$set": {"is_active": False}})
    await db.profiles.update_one({"id": profile_id}, {"$set": {"is_active": True}})
    p["is_active"] = True
    return p


@api_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    p = await db.profiles.find_one({"id": profile_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Profile not found")
    count = await db.profiles.count_documents({})
    if count <= 1:
        raise HTTPException(400, "Cannot delete last profile")
    await db.profiles.delete_one({"id": profile_id})
    await db.mappings.delete_many({"profile_id": profile_id})
    if p.get("is_active"):
        any_p = await db.profiles.find_one({}, {"_id": 0})
        if any_p:
            await db.profiles.update_one({"id": any_p["id"]}, {"$set": {"is_active": True}})
    return {"ok": True}


# ---------- Mapping routes ----------
@api_router.get("/profiles/{profile_id}/mappings", response_model=List[Mapping])
async def list_mappings(profile_id: str):
    docs = await db.mappings.find({"profile_id": profile_id}, {"_id": 0}).to_list(5000)
    return docs


@api_router.put("/profiles/{profile_id}/mappings/{control_id}", response_model=Mapping)
async def upsert_mapping(profile_id: str, control_id: str, body: MappingUpsert):
    p = await db.profiles.find_one({"id": profile_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Profile not found")
    existing = await db.mappings.find_one({"profile_id": profile_id, "control_id": control_id}, {"_id": 0})
    m = Mapping(
        id=existing["id"] if existing else str(uuid.uuid4()),
        profile_id=profile_id,
        control_id=control_id,
        action_type=body.action_type,
        target_app=body.target_app,
        params=body.params,
        label=body.label,
        ui_alias=body.ui_alias,
    )
    await db.mappings.update_one(
        {"profile_id": profile_id, "control_id": control_id},
        {"$set": m.model_dump()},
        upsert=True,
    )
    return m


@api_router.delete("/profiles/{profile_id}/mappings/{control_id}")
async def delete_mapping(profile_id: str, control_id: str):
    r = await db.mappings.delete_one({"profile_id": profile_id, "control_id": control_id})
    return {"ok": True, "deleted": r.deleted_count}


# ---------- Helper agent routes ----------
@api_router.post("/helper/heartbeat")
async def helper_heartbeat(body: HelperHeartbeat):
    state["helper_last_seen"] = now_iso()
    state["helper_info"] = body.model_dump()
    return {"ok": True, "server_time": now_iso()}


@api_router.get("/helper/status")
async def helper_status():
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


@api_router.get("/helper/state")
async def helper_state():
    """Helper polls this to know what to do."""
    profile = await db.profiles.find_one({"is_active": True}, {"_id": 0})
    if not profile:
        profile = await ensure_default_profile()
    mappings = await db.mappings.find({"profile_id": profile["id"]}, {"_id": 0}).to_list(5000)
    return {
        "active_profile": profile,
        "mappings": mappings,
        "server_time": now_iso(),
    }


@api_router.post("/helper/sessions")
async def report_sessions(body: SessionsReport):
    state["sessions"] = [s.model_dump() for s in body.sessions]
    state["sessions_updated"] = now_iso()
    return {"ok": True}


@api_router.get("/helper/sessions")
async def get_sessions():
    return {"sessions": state["sessions"], "updated": state["sessions_updated"]}


@api_router.post("/helper/midi-event")
async def report_midi_event(body: MidiEvent):
    state["midi_events"].append(body.model_dump())
    if len(state["midi_events"]) > MAX_EVENTS:
        state["midi_events"] = state["midi_events"][-MAX_EVENTS:]
    return {"ok": True}


@api_router.get("/helper/midi-events")
async def get_midi_events(since: Optional[str] = None, limit: int = 50):
    events = state["midi_events"]
    if since:
        events = [e for e in events if e["timestamp"] > since]
    return {"events": events[-limit:], "latest": events[-1] if events else None}


# ---------- Helper script download ----------
HELPER_SCRIPT_PATH = ROOT_DIR / "helper" / "launchkey_helper.py"


@api_router.get("/helper/script")
async def download_helper():
    if not HELPER_SCRIPT_PATH.exists():
        raise HTTPException(404, "Helper script not found")
    content = HELPER_SCRIPT_PATH.read_text()
    return Response(
        content=content,
        media_type="text/x-python",
        headers={"Content-Disposition": "attachment; filename=launchkey_helper.py"},
    )


@api_router.get("/helper/requirements")
async def download_requirements():
    path = ROOT_DIR / "helper" / "requirements.txt"
    if not path.exists():
        raise HTTPException(404, "requirements not found")
    return Response(
        content=path.read_text(),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=requirements.txt"},
    )


@api_router.get("/helper/install-script")
async def download_install_script():
    path = ROOT_DIR / "helper" / "install_windows.bat"
    if not path.exists():
        raise HTTPException(404, "install script not found")
    return Response(
        content=path.read_text(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=install_windows.bat"},
    )


# ---------- Root ----------
@api_router.get("/")
async def root():
    return {"service": "launchkey-mixer", "status": "ok"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    await ensure_default_profile()


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
