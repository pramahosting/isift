"""Plan limits: Basic vs paid vs administrator, and the administrator's per-person changes."""
import base64, io
import pytest
from tests.test_room_access import client, login, signed_up, make, join   # noqa: F401  (fixtures)

import itertools
_n = itertools.count(1)
def basic_user(c, mp):
    email = f"ben{next(_n)}@example.com"; c.email = email
    t = signed_up(c, mp, email, "Ben", "Hall")
    return {"Authorization": "Bearer " + t["access_token"]}

def user_id(c, ah, email):
    return next(u["id"] for u in c.get("/api/v1/admin/users", headers=ah).json() if u["email"] == email)

def pdf(pages):
    from reportlab.pdfgen import canvas
    b = io.BytesIO(); cv = canvas.Canvas(b)
    for i in range(pages): cv.drawString(72, 700, f"Page {i+1} text"); cv.showPage()
    cv.save(); return base64.b64encode(b.getvalue()).decode()

def test_admin_is_pramod_singh(client):
    ah, _ = login(client)
    assert client.get("/api/v1/account", headers=ah).json()["user"]["display_name"] == "Pramod Singh"
    assert client.get("/api/v1/me/pmi", headers=ah).status_code == 200

def test_open_room_only_admin_and_paid(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    r = client.post("/api/v1/rooms", json={"base_url": "http://t/", "options": {"open_room": True}}, headers=bh); assert r.status_code == 403, r.text
    assert client.patch("/api/v1/me/pmi", json={"open_room": True}, headers=bh).status_code == 403
    assert client.post("/api/v1/rooms", json={"base_url": "http://t/", "options": {"open_room": True}}, headers=ah).status_code == 200
    uid = user_id(client, ah, client.email)
    r = client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"open_room": True}}, headers=ah); assert r.status_code == 200, r.text
    assert r.json()["limits"]["open_room"] is True
    assert client.patch("/api/v1/me/pmi", json={"open_room": True}, headers=bh).status_code == 200

def test_five_documents_a_day_and_admin_can_raise(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    for k in ("doc", "board", "wp", "sheet", "deck"):
        assert client.post("/api/v1/notes", json={"kind": k}, headers=bh).status_code == 200
    r = client.post("/api/v1/notes", json={"kind": "board"}, headers=bh); assert r.status_code == 403 and "5 documents" in r.text.replace("5 new Docs", "5 documents") or r.status_code == 403
    assert client.get("/api/v1/me/limits", headers=bh).json()["docs_used_today"] == 5
    uid = user_id(client, ah, client.email)
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"docs_per_day": 7}}, headers=ah)
    assert client.post("/api/v1/notes", json={"kind": "doc"}, headers=bh).status_code == 200
    assert client.post("/api/v1/notes", json={"kind": "doc"}, headers=bh).status_code == 200
    assert client.post("/api/v1/notes", json={"kind": "doc"}, headers=bh).status_code == 403
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"docs_per_day": 0}}, headers=ah)     # 0 = no limit
    assert client.post("/api/v1/notes", json={"kind": "doc"}, headers=bh).status_code == 200
    for _ in range(7): assert client.post("/api/v1/notes", json={"kind": "doc"}, headers=ah).status_code == 200     # the administrator is never limited

def test_pdf_page_cap_for_basic(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    ok = client.post("/api/v1/docedit/inspect", json={"name": "a.pdf", "data": pdf(5), "count": True}, headers=bh); assert ok.status_code == 200, ok.text
    for _ in range(3): assert client.post("/api/v1/docedit/inspect", json={"name": "a.pdf", "data": pdf(5)}, headers=bh).status_code == 200     # re-reading is free
    assert client.get("/api/v1/me/limits", headers=bh).json()["docs_used_today"] == 1
    big = client.post("/api/v1/docedit/inspect", json={"name": "b.pdf", "data": pdf(6)}, headers=bh); assert big.status_code == 403 and "5 pages" in big.text
    assert client.post("/api/v1/docedit/inspect", json={"name": "b.pdf", "data": pdf(6)}, headers=ah).status_code == 200
    uid = user_id(client, ah, client.email)
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"pdf_pages": 8}}, headers=ah)
    assert client.post("/api/v1/docedit/inspect", json={"name": "b.pdf", "data": pdf(6)}, headers=bh).status_code == 200

def test_recording_not_for_basic(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    code = make(client, bh)["code"]
    ws, w = join(client, code, name="Ben", token=bh["Authorization"].split()[1])
    try:
        wel = w.receive_json(); assert wel["type"] == "welcome" and wel["can_record"] is False
        w.send_json({"type": "record", "on": True})
        got = [w.receive_json() for _ in range(1)][0]; assert got["type"] == "notice" and got["kind"] == "record"
    finally: ws.__exit__(None, None, None)
    r = client.post(f"/api/v1/rooms/{code}/recording", data={"consent_acknowledged": "true"}, files={"audio": ("a.webm", b"x")}, headers=bh); assert r.status_code == 403, r.text
    uid = user_id(client, ah, client.email)
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"recording": True}}, headers=ah)
    code2 = make(client, bh)["code"]
    ws, w = join(client, code2, name="Ben", token=bh["Authorization"].split()[1])
    try: assert w.receive_json()["can_record"] is True
    finally: ws.__exit__(None, None, None)

def test_basic_meeting_warns_then_ends(client, monkeypatch):
    from app.services import entitlements as ent
    monkeypatch.setitem(ent.BASIC, "meeting_minutes", 0.05); monkeypatch.setattr(ent, "WARN_MINUTES", 0.03)     # 3 s meeting, warning at 1.2 s
    bh = basic_user(client, monkeypatch); code = make(client, bh)["code"]
    ws, w = join(client, code, name="Ben", token=bh["Authorization"].split()[1])
    try:
        assert w.receive_json()["type"] == "welcome"
        seen = []
        while True:
            m = w.receive_json(); seen.append(m["type"] + ":" + str(m.get("kind", "")))
            if m["type"] == "ended": break
        assert "notice:ending" in seen and seen[-1] == "ended:"
    finally: ws.__exit__(None, None, None)

def test_paid_and_admin_have_no_limits(client, monkeypatch):
    import asyncio
    ah, _ = login(client); client.get("/api/v1/account", headers=ah)
    from app.core.db import SessionLocal
    from app.models import User
    from sqlalchemy import select
    from app.services import entitlements as ent
    async def go():
        async with SessionLocal() as db:
            u = (await db.execute(select(User).where(User.email == "admin@isift.au"))).scalar_one()
            return await ent.limits(db, u)
    L = asyncio.run(go()); assert L["recording"] and L["open_room"] and L["meeting_minutes"] == 0 and L["docs_per_day"] == 0

def test_old_personal_room_name_follows_the_host(client):
    import asyncio
    ah, _ = login(client); code = client.get("/api/v1/me/pmi", headers=ah).json()["code"]
    from app.core.db import SessionLocal
    from app.models import Room
    from sqlalchemy import select
    async def old():
        async with SessionLocal() as db:
            r = (await db.execute(select(Room).where(Room.code == code))).scalar_one(); r.title = "Administrator's Personal Meeting Room"; await db.commit()
    asyncio.run(old())
    assert client.get(f"/api/v1/rooms/{code}").json()["title"] == "Pramod Singh's Personal Meeting Room"

def test_built_in_admin_email_moves_to_isift_au(client):
    import asyncio
    from app.core.db import SessionLocal
    from app.models import User, Meeting
    from app.services import store, entitlements as ent
    from sqlalchemy import select
    from app import startup
    login(client)
    async def go():
        async with SessionLocal() as db:
            u = (await db.execute(select(User).where(User.entra_subject == "local-admin"))).scalar_one_or_none()
            if not u:
                u = User(entra_subject="local-admin", email="admin@example.test", display_name="Administrator", role="admin", role_override="admin"); db.add(u)
            u.email = "admin@example.test"; await db.commit()
            await store.put(db, store.hkey("profile", "admin@example.test"), {"limits": {"recording": True}})
            await startup._admin(db)
            u = (await db.execute(select(User).where(User.entra_subject == "local-admin"))).scalar_one()
            return u.email, u.display_name, await ent.overrides(db, "admin@isift.au")
    assert asyncio.run(go()) == ("admin@isift.au", "Pramod Singh", {"recording": True})

def test_commbox_not_for_basic_and_admin_table_has_plan_details(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    r = client.get("/api/v1/mailbox/accounts", headers=bh); assert r.status_code == 403 and "Commbox" in r.text
    assert client.get("/api/v1/mailbox/accounts", headers=ah).status_code == 200
    assert client.get("/api/v1/me/limits", headers=bh).json()["commbox"] is False
    row = next(u for u in client.get("/api/v1/admin/users", headers=ah).json() if u["email"] == client.email)
    assert row["plan_info"]["plan"] == "basic" and row["plan_info"]["paid"] is False and row["limits"]["commbox"] is False
    client.patch(f"/api/v1/admin/users/{row['id']}", json={"limits": {"commbox": True}}, headers=ah)      # a special permission overrides the plan
    assert client.get("/api/v1/mailbox/accounts", headers=bh).status_code == 200
    row = next(u for u in client.get("/api/v1/admin/users", headers=ah).json() if u["email"] == client.email)
    assert row["limits"]["custom"] == {"commbox": True}
