"""Admin usage report: real meetings (when and for how long), not calendar entries."""
import time
from tests.test_room_access import client, login   # noqa: F401  (fixtures)

def test_usage_report_empty_then_with_a_logged_meeting(client):
    ah, _ = login(client)
    r = client.get("/api/v1/admin/usage", headers=ah); assert r.status_code == 200, r.text
    j = r.json(); assert j["summary"]["meetings_30d"] == 0 and j["recent"] == []
    assert any(p["email"] == "admin@isift.au" for p in j["people"])

    from app.core.db import SessionLocal
    from app.services import meeting_log as ml
    async def add():
        async with SessionLocal() as db:
            now = time.time()
            await ml.record(db, title="Client call", host_email="Admin@isift.au", started_ts=now - 1800, ended_ts=now)
            await ml.record(db, title="oops", host_email="admin@isift.au", started_ts=now - 2, ended_ts=now)     # too short to count
    client.portal.call(add)                                            # on the app's own event loop, like a real request

    j = client.get("/api/v1/admin/usage", headers=ah).json()
    assert j["summary"]["meetings_30d"] == 1 and j["summary"]["hosts_30d"] == 1
    assert j["recent"][0]["title"] == "Client call" and 29 <= j["recent"][0]["minutes"] <= 31
    assert "code" not in j["recent"][0]                                # the room code is a secret and is never listed
    csv = client.get("/api/v1/admin/usage/export", headers=ah); assert csv.status_code == 200
    assert csv.text.splitlines()[0].startswith("started_at_utc") and "Client call" in csv.text

def test_usage_report_is_admin_only(client):
    assert client.get("/api/v1/admin/usage").status_code in (401, 403)
