import asyncio, base64, json
import pytest
from datetime import datetime, timedelta, timezone
from starlette.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PUSH_LOOP", "false")
    from app.main import app
    from app.core.db import engine
    from app.models import Base
    async def mk():
        async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    asyncio.run(mk())
    with TestClient(app) as c:
        yield c


def login(c):
    r = c.post("/api/v1/auth/local-login", json={"username": "admin", "password": "Meeting$1"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_register_and_notify(client, monkeypatch):
    c = client; h = login(c)
    assert c.get("/api/v1/push/key").status_code in (401, 403)
    k = c.get("/api/v1/push/key", headers=h).json()
    assert len(base64.urlsafe_b64decode(k["key"] + "==")) == 65 and k["devices"] == 0          # an uncompressed P-256 point
    assert c.get("/api/v1/push/key", headers=h).json()["key"] == k["key"]                       # stable once made
    assert c.post("/api/v1/push/subscribe", json={"subscription": {"endpoint": "http://x", "keys": {}}}, headers=h).status_code == 400
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "BPk", "auth": "au"}}
    assert c.post("/api/v1/push/subscribe", json={"subscription": sub, "ua": "test"}, headers=h).status_code == 200
    assert c.get("/api/v1/push/key", headers=h).json()["devices"] == 1
    sent = []
    from app.services import push
    monkeypatch.setattr(push, "_send_one", lambda s, payload, pem: (sent.append(json.loads(payload)), 201)[1])
    assert c.post("/api/v1/push/test", headers=h).json() == {"sent": 1} and sent[0]["title"].startswith("iSift notifications")
    # an invitation alert is pushed too
    async def go():
        from app.core.db import SessionLocal
        from app.services import notify
        async with SessionLocal() as db: await notify.notify(db, "admin@isift.au", "invite", "Ann invited you", "Plan", "#/room/x", "ann")
    asyncio.run(go()); assert sent[-1]["title"] == "Ann invited you" and sent[-1]["url"] == "#/room/x"
    # a meeting starting in 3 minutes is announced once
    async def meet():
        from app.core.db import SessionLocal
        from app.models import Meeting, User
        from sqlalchemy import select
        async with SessionLocal() as db:
            u = (await db.execute(select(User).where(User.email == "admin@isift.au"))).scalar_one()
            now = datetime.now(timezone.utc)
            db.add(Meeting(owner_id=u.id, external_id="e1", title="Standup", start_at=now + timedelta(minutes=3), end_at=now + timedelta(minutes=33), join_url="https://isift.au/#/room/s"))
            await db.commit()
            n1 = await push.tick(db); n2 = await push.tick(db); return n1, n2
    before = len(sent); n1, n2 = asyncio.run(meet())
    soon = [s for s in sent[before:] if s["kind"] == "meeting"]; assert len(soon) == 1 and soon[0]["title"] == "Standup" and "3 min" in soon[0]["body"] and n1 == 1
    # a gone device (410) is forgotten
    monkeypatch.setattr(push, "_send_one", lambda s, payload, pem: 410)
    assert c.post("/api/v1/push/test", headers=h).status_code == 409 and c.get("/api/v1/push/key", headers=h).json()["devices"] == 0
