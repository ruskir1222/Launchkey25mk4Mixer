"""Backend API tests for Launchkey Mixer."""
import os
import time
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Profiles ----------
class TestProfiles:
    def test_default_profile_seeded(self, s):
        r = s.get(f"{API}/profiles")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(p["is_active"] for p in data)

    def test_create_activate_delete(self, s):
        r = s.post(f"{API}/profiles", json={"name": "TEST_profile_A"})
        assert r.status_code == 200
        pa = r.json()
        assert pa["name"] == "TEST_profile_A"
        assert "id" in pa

        r2 = s.post(f"{API}/profiles", json={"name": "TEST_profile_B"})
        pb = r2.json()

        r3 = s.post(f"{API}/profiles/{pa['id']}/activate")
        assert r3.status_code == 200
        assert r3.json()["is_active"] is True

        # only one active
        profiles = s.get(f"{API}/profiles").json()
        active = [p for p in profiles if p["is_active"]]
        assert len(active) == 1
        assert active[0]["id"] == pa["id"]

        # delete pb
        rd = s.delete(f"{API}/profiles/{pb['id']}")
        assert rd.status_code == 200
        # cleanup pa
        s.delete(f"{API}/profiles/{pa['id']}")

    def test_cannot_delete_last_profile(self, s):
        # delete all except one
        profiles = s.get(f"{API}/profiles").json()
        for p in profiles[1:]:
            s.delete(f"{API}/profiles/{p['id']}")
        profiles = s.get(f"{API}/profiles").json()
        assert len(profiles) == 1
        r = s.delete(f"{API}/profiles/{profiles[0]['id']}")
        assert r.status_code == 400


# ---------- Mappings ----------
class TestMappings:
    @pytest.fixture
    def profile(self, s):
        r = s.post(f"{API}/profiles", json={"name": "TEST_mapprofile"})
        p = r.json()
        yield p
        s.delete(f"{API}/profiles/{p['id']}")

    def test_upsert_get_delete_mapping(self, s, profile):
        pid = profile["id"]
        payload = {"action_type": "set_volume", "target_app": "chrome.exe", "label": "Chrome", "params": {}}
        r = s.put(f"{API}/profiles/{pid}/mappings/knob-1", json=payload)
        assert r.status_code == 200
        m = r.json()
        assert m["control_id"] == "knob-1"
        assert m["action_type"] == "set_volume"
        assert m["target_app"] == "chrome.exe"

        # GET
        rg = s.get(f"{API}/profiles/{pid}/mappings")
        assert rg.status_code == 200
        ms = rg.json()
        assert len(ms) == 1 and ms[0]["control_id"] == "knob-1"

        # upsert again (update)
        payload2 = {"action_type": "toggle_mute", "target_app": "spotify.exe", "label": "Spot", "params": {}}
        r2 = s.put(f"{API}/profiles/{pid}/mappings/knob-1", json=payload2)
        assert r2.json()["action_type"] == "toggle_mute"
        ms2 = s.get(f"{API}/profiles/{pid}/mappings").json()
        assert len(ms2) == 1  # not duplicated

        # delete
        rd = s.delete(f"{API}/profiles/{pid}/mappings/knob-1")
        assert rd.status_code == 200
        assert rd.json()["deleted"] == 1
        assert s.get(f"{API}/profiles/{pid}/mappings").json() == []

    def test_mapping_cascade_on_profile_delete(self, s):
        # create profile + extra profile (so we don't fail last-profile rule)
        p = s.post(f"{API}/profiles", json={"name": "TEST_cascade"}).json()
        s.put(f"{API}/profiles/{p['id']}/mappings/pad-1",
              json={"action_type": "media_play_pause", "params": {}}).status_code
        s.delete(f"{API}/profiles/{p['id']}")
        ms = s.get(f"{API}/profiles/{p['id']}/mappings").json()
        assert ms == []


# ---------- Helper telemetry ----------
class TestHelper:
    def test_heartbeat_then_status(self, s):
        r = s.post(f"{API}/helper/heartbeat",
                   json={"version": "1.0.0", "midi_port": "Launchkey 37", "device_connected": True})
        assert r.status_code == 200
        time.sleep(0.5)
        st = s.get(f"{API}/helper/status").json()
        assert st["helper_connected"] is True
        assert st["helper_info"].get("midi_port") == "Launchkey 37"

    def test_sessions_roundtrip(self, s):
        body = {"sessions": [
            {"process_name": "chrome.exe", "display_name": "Chrome", "volume": 0.5, "muted": False, "pid": 1234}
        ]}
        r = s.post(f"{API}/helper/sessions", json=body)
        assert r.status_code == 200
        g = s.get(f"{API}/helper/sessions").json()
        assert len(g["sessions"]) >= 1
        assert any(x["process_name"] == "chrome.exe" for x in g["sessions"])

    def test_midi_event_roundtrip_and_since(self, s):
        from datetime import datetime, timezone
        marker = datetime.now(timezone.utc).isoformat()
        time.sleep(0.05)
        r = s.post(f"{API}/helper/midi-event",
                   json={"control_id": "knob-3", "raw_type": "cc", "channel": 0, "number": 23, "value": 64})
        assert r.status_code == 200
        ev = s.get(f"{API}/helper/midi-events", params={"since": marker}).json()
        assert ev["latest"]["control_id"] == "knob-3"
        assert any(e["control_id"] == "knob-3" for e in ev["events"])

    def test_helper_state(self, s):
        st = s.get(f"{API}/helper/state").json()
        assert "active_profile" in st and st["active_profile"] is not None
        assert "mappings" in st and isinstance(st["mappings"], list)

    def test_helper_script_download(self, s):
        r = s.get(f"{API}/helper/script")
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert "launchkey_helper.py" in cd
        assert b"Launchkey" in r.content[:500] or b"launchkey" in r.content[:1000]
