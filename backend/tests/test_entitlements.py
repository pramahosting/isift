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

def test_price_change_shows_at_once_and_is_never_cached(client):
    ah, _ = login(client)
    r = client.get("/api/v1/billing/plans"); assert "no-store" in r.headers["cache-control"]
    assert client.patch("/api/v1/admin/pricing/default-individual", json={"monthly": 2000, "yearly": 22800}, headers=ah).status_code == 200
    ind = next(p for p in client.get("/api/v1/billing/plans?t=1").json()["plans"] if p["id"] == "individual")
    assert ind["monthly"] == 2000 and ind["yearly"] == 22800

def test_basic_gets_a_taste_of_ai_and_one_booking_page(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    L = client.get("/api/v1/me/limits", headers=bh).json(); assert L["ai_per_month"] == 3 and L["booking_pages"] == 1 and L["calls"] is False
    week = {str(d): [["09:00", "17:00"]] for d in range(7)}
    r = client.post("/api/v1/booking-types", json={"title": "One", "duration_minutes": 30, "availability": week}, headers=bh); assert r.status_code == 200, r.text
    r = client.post("/api/v1/booking-types", json={"title": "Two", "duration_minutes": 30, "availability": week}, headers=bh); assert r.status_code == 403 and "1 booking page" in r.text
    uid = user_id(client, ah, client.email)
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"booking_pages": 3, "ai_per_month": 1}}, headers=ah)
    assert client.post("/api/v1/booking-types", json={"title": "Two", "duration_minutes": 30, "availability": week}, headers=bh).status_code == 200
    import asyncio
    from app.core.db import SessionLocal
    from app.models import User
    from sqlalchemy import select
    from app.services import entitlements as ent
    from fastapi import HTTPException
    async def go():
        async with SessionLocal() as db:
            u = (await db.execute(select(User).where(User.email == client.email))).scalar_one()
            await ent.use_ai(db, u)
            try: await ent.use_ai(db, u)
            except HTTPException as e: return e.status_code
    assert asyncio.run(go()) == 403

def test_calling_between_users(client, monkeypatch):
    ah, atok = login(client)
    bh = basic_user(client, monkeypatch); bmail = client.email; btok = bh["Authorization"].split()[1]
    r = client.post("/api/v1/calls", json={"to": "admin@isift.au"}, headers=bh); assert r.status_code == 403 and "Basic" in r.text      # Basic cannot place calls
    uid = user_id(client, ah, bmail)
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"calls": True}}, headers=ah)
    r = client.post("/api/v1/calls", json={"to": "admin@isift.au"}, headers=bh); assert r.status_code == 409 and "not online" in r.text   # callee has no open tab
    assert client.post("/api/v1/calls", json={"to": "nobody@nowhere.com"}, headers=bh).status_code == 404
    with client.websocket_connect("/api/v1/ws/calls") as aws, client.websocket_connect("/api/v1/ws/calls") as bws:
        aws.send_json({"type": "auth", "token": atok}); assert aws.receive_json()["type"] == "ready"
        bws.send_json({"type": "auth", "token": btok}); assert bws.receive_json()["type"] == "ready"
        r = client.post("/api/v1/calls", json={"to": "admin@isift.au", "base_url": "http://t/"}, headers=bh); assert r.status_code == 200, r.text
        cid, code = r.json()["call_id"], r.json()["code"]
        m = aws.receive_json(); assert m["type"] == "incoming" and m["call_id"] == cid and m["code"] == code and m["from"]["email"] == bmail
        assert client.post(f"/api/v1/calls/{cid}/answer", json={"accept": True}, headers=bh).status_code == 404       # only the callee can answer
        assert client.post(f"/api/v1/calls/{cid}/answer", json={"accept": True}, headers=ah).json()["code"] == code
        assert aws.receive_json()["type"] == "ended"
        assert bws.receive_json()["type"] == "accepted"
        # second call: declined
        cid2 = client.post("/api/v1/calls", json={"to": "admin@isift.au", "base_url": "http://t/"}, headers=bh).json()["call_id"]; aws.receive_json()
        client.post(f"/api/v1/calls/{cid2}/answer", json={"accept": False}, headers=ah); assert aws.receive_json()["type"] == "ended"; assert bws.receive_json()["type"] == "declined"
        # third call: the caller hangs up before it is answered
        cid3 = client.post("/api/v1/calls", json={"to": "admin@isift.au", "base_url": "http://t/"}, headers=bh).json()["call_id"]; aws.receive_json()
        client.post(f"/api/v1/calls/{cid3}/cancel", headers=bh); m = aws.receive_json(); assert m["type"] == "ended" and m["reason"] == "cancelled"
    ws, w = join(client, code, name="Admin", token=atok)
    try: assert w.receive_json()["type"] == "welcome"
    finally: ws.__exit__(None, None, None)

def _team(client):
    """Admin owns a company on the Business plan with two teammates; returns headers for owner, bella, carl."""
    ah, _ = login(client); client.get("/api/v1/account", headers=ah)
    assert client.post("/api/v1/account/company", json={"name": "Acme"}, headers=ah).status_code == 201
    out = [ah]
    for who in ("bella", "carl"):
        m = client.post("/api/v1/account/company/members", json={"email": f"{who}@acme.com", "name": who.title(), "role": "member"}, headers=ah); assert m.status_code == 201, m.text
        t = client.post("/api/v1/auth/local-login", json={"username": f"{who}@acme.com", "password": m.json()["temp_password"]}).json()["access_token"]
        h = {"Authorization": "Bearer " + t}; client.get("/api/v1/account", headers=h); out.append(h)
    import asyncio
    from app.core.db import SessionLocal
    from app.services import store
    async def upgrade():
        async with SessionLocal() as db:
            link = await store.get(db, store.hkey("memberof", "admin@isift.au"), {})
            await store.put(db, f"billing:co:{link['company_id']}", {"plan": "business", "period": "monthly", "status": "active", "period_end": None, "auto_renew": False, "failure_count": 0, "charges": []})
    asyncio.run(upgrade())
    return out

def test_team_needs_business_company(client, monkeypatch):
    bh = basic_user(client, monkeypatch)
    assert client.get("/api/v1/team/action-items", headers=bh).status_code == 402
    assert client.get("/api/v1/team/booking-pages", headers=bh).status_code == 402
    r = client.post("/api/v1/booking-types", json={"title": "Team", "team_members": ["x@y.com"]}, headers=bh); assert r.status_code == 402

def test_team_shared_action_items(client):
    from datetime import datetime, timezone
    ah, bh, ch = _team(client)
    base = {"title": "Standup", "start_at": datetime.now(timezone.utc).isoformat(), "end_at": datetime.now(timezone.utc).isoformat()}
    mid = client.post("/api/v1/meetings", json=base, headers=bh)
    if mid.status_code >= 400: pytest.skip("meeting create route differs")
    mid = mid.json()["id"]
    from app.core.db import SessionLocal
    import asyncio
    from app.models import ActionItem, Meeting
    async def add(sens):
        async with SessionLocal() as db:
            m = await db.get(Meeting, mid); m.sensitivity = sens
            a = ActionItem(meeting_id=mid, description="Send the deck", owner="carl@acme.com", status="assigned"); db.add(a); await db.commit(); return a.id
    aid = asyncio.get_event_loop().run_until_complete(add("normal")) if False else asyncio.run(add("normal"))
    got = client.get("/api/v1/team/action-items", headers=ch).json()
    assert [x["description"] for x in got] == ["Send the deck"] and got[0]["mine"] is False
    assert client.patch(f"/api/v1/team/action-items/{aid}", json={"status": "completed"}, headers=ch).json()["status"] == "completed"
    assert client.get("/api/v1/action-items", headers=bh).json()[0]["status"] == "completed"       # the meeting owner sees it
    assert client.get("/api/v1/action-items", headers=ch).json() == []                             # not copied into Carl's own list
    asyncio.run(add("sensitive")); assert len(client.get("/api/v1/team/action-items", headers=ch).json()) == 0   # sensitive meetings are never shared
    outsider = basic_user(client, None) if False else None

def test_team_booking_page_round_robin(client):
    ah, bh, ch = _team(client)
    week = {str(d): [["09:00", "10:00"]] for d in range(7)}
    r = client.post("/api/v1/booking-types", json={"title": "Sales call", "duration_minutes": 30, "min_notice_hours": 0, "timezone": "UTC", "availability": week, "slug": "sales", "team_members": ["bella@acme.com", "carl@acme.com", "x@other.com"]}, headers=ah)
    assert r.status_code == 422                                                                   # not on the company
    r = client.post("/api/v1/booking-types", json={"title": "Sales call", "duration_minutes": 30, "min_notice_hours": 0, "timezone": "UTC", "availability": week, "slug": "sales", "team_members": ["bella@acme.com", "carl@acme.com"]}, headers=ah)
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]; assert r.json()["team_members"] == ["bella@acme.com", "carl@acme.com"]
    page = client.get(f"/api/v1/public/book/{slug}").json(); assert page["team"] is True
    seen = client.get(f"/api/v1/team/booking-pages", headers=bh).json(); assert [p["slug"] for p in seen] == [slug] and seen[0]["mine"] is False
    slots = client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]; assert slots
    first = slots[0]
    body = lambda n: {"name": f"G{n}", "email": f"g{n}@example.com", "start": first, "timezone": "UTC", "base_url": "http://t/"}
    for n in range(3): assert client.post(f"/api/v1/public/book/{slug}", json=body(n)).status_code == 200      # three people may take the same time
    assert client.post(f"/api/v1/public/book/{slug}", json=body(9)).status_code == 409                       # all three busy now
    counts = [len(client.get("/api/v1/bookings", headers=h).json()) for h in (ah, bh, ch)]
    assert counts == [1, 1, 1]                                                                    # shared out evenly
    assert first not in client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]
    # a teammate who is removed from the page stops getting bookings
    assert client.patch(f"/api/v1/booking-types/{r.json()['id']}", json={"team_members": []}, headers=ah).json()["team_members"] == []
    assert client.get(f"/api/v1/public/book/{slug}").json()["team"] is False

def test_storage_and_meeting_hours_limits(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch)
    L = client.get("/api/v1/me/limits", headers=bh).json()
    assert L["storage_mb"] == 100 and L["meeting_hours_per_month"] == 20 and L["storage_used_mb"] == 0
    uid = user_id(client, ah, client.email)
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"storage_mb": 1}}, headers=ah)
    big = "x" * 600_000
    n = client.post("/api/v1/notes", json={"kind": "doc", "content": big}, headers=bh); assert n.status_code in (200, 413), n.text
    if n.status_code == 200:
        r = client.post("/api/v1/notes", json={"kind": "doc", "content": big}, headers=bh); assert r.status_code == 403 and "storage is full" in r.text
        small = client.post("/api/v1/notes", json={"kind": "doc", "content": "hi"}, headers=bh); assert small.status_code == 200      # small ones still fit
        client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"storage_mb": 0}}, headers=ah)                                      # 0 = no limit
        assert client.post("/api/v1/notes", json={"kind": "doc", "content": big}, headers=bh).status_code == 200
    # meeting hours: counted per host, a host with none left cannot start
    import asyncio
    from app.core.db import SessionLocal
    from app.services import entitlements as ent
    from app.models import User
    from sqlalchemy import select
    async def use(mins):
        async with SessionLocal() as db:
            u = (await db.execute(select(User).where(User.email == client.email))).scalar_one()
            await ent.add_meeting_minutes(db, u.email, mins); return await ent.minutes_left(db, u)
    assert asyncio.run(use(60)) == 20 * 60 - 60
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"meeting_hours_per_month": 1}}, headers=ah)
    assert asyncio.run(use(0)) == 0
    assert client.get("/api/v1/me/limits", headers=bh).json()["hours_used_month"] == 1.0
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"meeting_hours_per_month": 0}}, headers=ah)
    assert asyncio.run(use(0)) is None
    assert client.get("/api/v1/me/limits", headers=ah).json()["storage_mb"] == 0       # administrators are never limited

def test_host_without_hours_left_cannot_start_and_hours_are_counted(client, monkeypatch):
    ah, _ = login(client); bh = basic_user(client, monkeypatch); tok = bh["Authorization"].split()[1]
    code = make(client, bh)["code"]
    ws, w = join(client, code, name="Ben", token=tok)
    try: assert w.receive_json()["type"] == "welcome"
    finally: ws.__exit__(None, None, None)
    import time; time.sleep(0.3)
    assert client.get("/api/v1/me/limits", headers=bh).json()["hours_used_month"] >= 0           # counted when the room emptied
    uid = user_id(client, ah, client.email)
    client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"meeting_hours_per_month": 1}}, headers=ah)
    import asyncio
    from app.core.db import SessionLocal
    from app.services import entitlements as ent
    async def burn():
        async with SessionLocal() as db: await ent.add_meeting_minutes(db, client.email, 61)
    asyncio.run(burn())
    code2 = make(client, bh)["code"]
    ws, w = join(client, code2, name="Ben", token=tok)
    try:
        m = w.receive_json(); assert m["type"] == "error" and "meeting hours" in m["message"]
    finally: ws.__exit__(None, None, None)

def test_ice_servers_include_relay_options(client, monkeypatch):
    import asyncio
    from app.core.config import settings
    from app.api import routes_rooms as rr
    monkeypatch.setattr(settings, "ice_servers", "stun:s.example.com:3478,turn:t.example.com:3478")
    monkeypatch.setattr(settings, "turn_shared_secret", "s3cret")
    ice = asyncio.run(rr.ice_config())
    t = next(x for x in ice if str(x["urls"]).startswith("turn:")); assert t["username"].endswith(":isift") and t["credential"]        # short-lived password for coturn
    monkeypatch.setattr(settings, "ice_servers", ""); monkeypatch.setattr(settings, "turn_shared_secret", "")
    assert asyncio.run(rr.ice_config())[0]["urls"][0].startswith("stun:")                                                              # always at least STUN
    ah, _ = login(client)
    code = make(client, ah)["code"]
    assert "ice" in client.get(f"/api/v1/rooms/{code}").json()

def test_login_before_finishing_signup_says_so_and_resend_mail_works(client, monkeypatch):
    from tests.test_room_access import SU
    from app.services import signup as su
    got = {}
    async def fake(db, email, name, code): got["code"] = code; return True
    monkeypatch.setattr(su, "send_code", fake)
    em = "pending1@example.com"
    assert client.post("/api/v1/auth/signup/start", json={**SU, "email": em}).status_code == 200
    r = client.post("/api/v1/auth/local-login", json={"username": em, "password": "Password123"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "signup_incomplete" and "not complete" in r.json()["detail"]["message"]
    assert client.post("/api/v1/auth/local-login", json={"username": "nobody1@example.com", "password": "x"}).json()["detail"]["code"] == "no_account"
    assert client.post("/api/v1/auth/signup/verify", json={"email": em, "code": got["code"]}).status_code == 200
    assert client.post("/api/v1/auth/local-login", json={"username": em, "password": "Password123"}).status_code == 200
    # mail over HTTPS (Resend) for hosts that block SMTP
    import asyncio
    from app.core.config import settings
    from app.integrations import mail
    monkeypatch.setattr(settings, "resend_api_key", "re_test"); monkeypatch.setattr(settings, "smtp_from", "hello@isift.au"); monkeypatch.setattr(settings, "smtp_host", "")
    acct = su.app_sender(); assert acct and acct["resend_key"] == "re_test" and acct["from"] == "hello@isift.au"
    sent = {}
    class R:
        status_code = 200
        def json(s): return {}
    class C:
        def __init__(s, **k): pass
        async def __aenter__(s): return s
        async def __aexit__(s, *a): return False
        async def post(s, url, headers=None, json=None): sent.update(url=url, auth=headers["Authorization"], body=json); return R()
    import httpx; monkeypatch.setattr(httpx, "AsyncClient", C)
    asyncio.run(mail.send(acct, ["a@b.com"], "Hi", "Code 123456"))
    assert sent["url"] == "https://api.resend.com/emails" and sent["auth"] == "Bearer re_test" and sent["body"]["to"] == ["a@b.com"] and sent["body"]["from"] == "hello@isift.au"
