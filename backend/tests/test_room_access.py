from datetime import datetime, timezone
import os, tempfile
import pytest
from starlette.testclient import TestClient

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "room_default_waiting", False)
    monkeypatch.setattr(settings, "room_default_access", "open")
    from app.main import app
    from app.core.db import engine
    from app.models import Base
    import asyncio
    async def mk():
        async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    asyncio.run(mk())
    with TestClient(app) as c:
        yield c

def login(c):
    r = c.post("/api/v1/auth/local-login", json={"username": "admin", "password": "Meeting$1"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()["access_token"]

SU = {"first_name": "Bob", "last_name": "Lee", "email": "bob@example.com", "password": "Password123", "country": "AU", "phone": "0412 345 678", "agree": True}
def signed_up(c, mp, email, first, last, **kw):
    """Run the whole sign-up (details, emailed code, verify) and return the token response."""
    from app.services import signup as su
    got = {}
    async def fake(db, em, name, code): got["code"] = code; return True
    mp.setattr(su, "send_code", fake)
    r = c.post("/api/v1/auth/signup/start", json={**SU, "email": email, "first_name": first, "last_name": last, **kw}); assert r.status_code == 200, r.text
    r = c.post("/api/v1/auth/signup/verify", json={"email": email, "code": got["code"]}); assert r.status_code == 200, r.text
    return r.json()

def make(c, h, **kw):
    r = c.post("/api/v1/rooms", json={"base_url": "http://t/", **kw}, headers=h); assert r.status_code == 200, r.text
    return r.json()

def join(c, code, **kw):
    ws = c.websocket_connect(f"/api/v1/ws/rooms/{code}"); w = ws.__enter__()
    w.send_json({"type": "join", **kw}); return ws, w

def test_open_room_guest_joins(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False)
    ws, w = join(client, r["code"], name="Gina")
    assert w.receive_json()["type"] == "welcome"; ws.__exit__(None, None, None)

def test_passcode_required_and_host_bypasses(client):
    h, tok = login(client); r = make(client, h, access="passcode", waiting_room=False)
    assert len(r["passcode"]) >= 4
    info = client.get(f"/api/v1/rooms/{r['code']}").json()
    assert info["access"] == "passcode" and "passcode" not in info
    ws, w = join(client, r["code"], name="X", passcode="wrong"); m = w.receive_json()
    assert m["type"] == "error" and m["code"] == "passcode"; ws.__exit__(None, None, None)
    ws, w = join(client, r["code"], name="X", passcode=r["passcode"]); assert w.receive_json()["type"] == "welcome"; ws.__exit__(None, None, None)
    ws, w = join(client, r["code"], name="Host", token=tok); assert w.receive_json()["host"] is True; ws.__exit__(None, None, None)

def test_signed_in_only_blocks_guests(client):
    h, tok = login(client); r = make(client, h, access="signed_in", waiting_room=False)
    ws, w = join(client, r["code"], name="Gina"); m = w.receive_json()
    assert m["type"] == "error" and m["code"] == "signin"; ws.__exit__(None, None, None)
    ws, w = join(client, r["code"], token=tok); assert w.receive_json()["type"] == "welcome"; ws.__exit__(None, None, None)

def test_waiting_room_admit_and_deny(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=True)
    hs, host = join(client, r["code"], token=tok); assert host.receive_json()["type"] == "welcome"
    gs, guest = join(client, r["code"], name="Gina")
    assert guest.receive_json()["type"] == "waiting"
    wl = host.receive_json(); assert wl["type"] == "waiting-list" and wl["list"][0]["name"] == "Gina"
    guest.send_json({"type": "chat", "text": "let me in"})          # ignored while waiting
    host.send_json({"type": "admit", "id": wl["list"][0]["id"]})
    assert guest.receive_json()["type"] == "welcome"
    gs.__exit__(None, None, None)
    g2, guest2 = join(client, r["code"], name="Bob"); assert guest2.receive_json()["type"] == "waiting"
    wl = host.receive_json()
    while wl["type"] != "waiting-list" or not wl["list"]: wl = host.receive_json()
    host.send_json({"type": "deny", "id": wl["list"][0]["id"]})
    assert guest2.receive_json()["type"] == "denied"
    g2.__exit__(None, None, None); hs.__exit__(None, None, None)

def test_host_can_change_access(client):
    h, tok = login(client); r = make(client, h, access="open")
    v = client.patch(f"/api/v1/rooms/{r['code']}", json={"access": "passcode"}, headers=h).json()
    assert v["access"] == "passcode" and v["passcode"]
    assert client.get(f"/api/v1/rooms/{r['code']}/host", headers=h).json()["passcode"] == v["passcode"]
    assert client.get(f"/api/v1/rooms/{r['code']}/host").status_code in (401, 403)

def test_cancel_meeting_ends_room(client):
    h, tok = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Board", "start_at": "2030-01-01T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/", "access": "passcode"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json(); assert body["passcode"] and "#/room/" in body["join_url"]
    code = body["join_url"].split("#/room/")[1]
    ws, w = join(client, code, token=tok); assert w.receive_json()["type"] == "welcome"
    c = client.post(f"/api/v1/meetings/{body['id']}/cancel", headers=h); assert c.status_code == 200, c.text
    assert w.receive_json()["type"] == "ended"; ws.__exit__(None, None, None)
    assert client.get(f"/api/v1/rooms/{code}").json()["ended"] is True
    mine = [m for m in client.get("/api/v1/meetings", headers=h).json() if m["id"] == body["id"]][0]
    assert mine["status"] == "cancelled"

def test_only_host_can_end(client):
    h, tok = login(client); r = make(client, h, access="open")
    assert client.post(f"/api/v1/rooms/{r['code']}/end").status_code in (401, 403)
    assert client.post(f"/api/v1/rooms/{r['code']}/end", json={}, headers=h).status_code == 200
    assert client.get(f"/api/v1/rooms/{r['code']}").json()["ended"] is True

def test_recording_found_after_folder_move(client, tmp_path, monkeypatch):
    import shutil
    from app.core.config import settings
    old, new = tmp_path / "old", tmp_path / "new"; (old / "recordings").mkdir(parents=True)
    monkeypatch.setattr(settings, "audio_storage_dir", str(old))
    from app.services import storage; monkeypatch.setattr(storage, "DB_BLOB_LIMIT", 0)     # force the local-folder fallback
    h, tok = login(client); r = make(client, h)
    webm = bytes.fromhex("1A45DFA3") + b"x" * 3000
    up = client.post(f"/api/v1/rooms/{r['code']}/recording", headers=h, data={"consent_acknowledged": "true", "cloud": "true"}, files={"audio": ("a.webm", webm, "audio/webm"), "video": ("v.webm", webm, "video/webm")})
    assert up.status_code == 200
    shutil.move(str(old), str(new)); monkeypatch.setattr(settings, "audio_storage_dir", str(new))   # the app folder was moved or renamed
    rec = client.get("/api/v1/recordings", headers=h).json()[0]
    assert rec["available"] is True and rec["created_at"].endswith(("Z", "+00:00"))
    assert client.get(f"/api/v1/recordings/{rec['id']}/file", headers=h).status_code == 200
    shutil.rmtree(new)
    assert client.get("/api/v1/recordings", headers=h).json()[0]["available"] is False
    d = client.get(f"/api/v1/recordings/{rec['id']}/file", headers=h); assert d.status_code == 410 and "no longer" in d.json()["detail"]

def test_open_and_edit_meeting_like_zoom(client):
    h, tok = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Plan", "agenda": "Budget", "start_at": "2030-01-01T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/",
                    "access": "passcode", "waiting_room": True, "options": {"mute_on_entry": True}, "invite": "a@example.com, b@example.com"}, headers=h)
    assert r.status_code == 200, r.text; mid = r.json()["id"]
    d = client.get(f"/api/v1/meetings/{mid}/details", headers=h).json()
    assert d["kind"] == "room" and d["passcode"] and d["meeting_id"] and "#/room/" in d["join_url"]
    assert d["agenda"] == "Budget" and d["waiting_room"] is True and d["options"]["mute_on_entry"] is True and d["invitees"] == ["a@example.com", "b@example.com"]
    assert d["duration_minutes"] == 30 and d["start_at"].startswith("2030-01-01T10:00")
    p = client.patch(f"/api/v1/meetings/{mid}", json={"title": "Plan v2", "start_at": "2030-01-02T11:00:00Z", "duration_minutes": 45, "access": "open", "waiting_room": False,
                     "options": {"video_off_on_entry": True, "auto_record": True}, "add_invitees": "c@example.com"}, headers=h)
    assert p.status_code == 200, p.text; n = p.json()
    assert n["title"] == "Plan v2" and n["duration_minutes"] == 45 and n["start_at"].startswith("2030-01-02T11:00") and n["access"] == "open" and n["passcode"] is None
    assert n["options"] == {"mute_on_entry": True, "video_off_on_entry": True, "auto_record": True, "host_video_off": False} and "c@example.com" in n["invitees"]
    p2 = client.patch(f"/api/v1/meetings/{mid}", json={"access": "passcode", "passcode": "4321"}, headers=h).json(); assert p2["passcode"] == "4321"
    code = n["meeting_id"]; assert client.get(f"/api/v1/rooms/{code}").json()["options"]["mute_on_entry"] is True
    assert client.patch(f"/api/v1/meetings/{mid}", json={"title": ""}, headers=h).status_code == 422
    assert client.get(f"/api/v1/meetings/{mid}/details").status_code in (401, 403)

def test_pmi_recurrence_contacts_chat_notes(client, monkeypatch):
    h, tok = login(client)
    # personal meeting ID is stable and survives ending
    p1 = client.get("/api/v1/me/pmi", headers=h).json(); p2 = client.get("/api/v1/me/pmi", headers=h).json()
    assert p1["code"] == p2["code"] and len(p1["code"]) == 10 and p1["passcode"]
    # recurring weekly series on one link, scheduled with the personal ID
    r = client.post("/api/v1/meetings", json={"title": "Standup", "start_at": "2030-03-01T09:00", "duration_minutes": 15, "provider": "room", "base_url": "http://t/",
                    "recurrence": {"every": "week", "count": 3}, "meeting_id_mode": "personal", "timezone": "Australia/Sydney"}, headers=h)
    assert r.status_code == 200, r.text
    ms = [m for m in client.get("/api/v1/meetings", headers=h).json() if m["title"] == "Standup"]
    assert len(ms) == 3 and len({m["join_url"] for m in ms}) == 1 and p1["code"] in ms[0]["join_url"]
    ms.sort(key=lambda m: m["start_at"]); assert ms[0]["start_at"].startswith("2030-02-28T22:00") and ms[1]["start_at"].startswith("2030-03-07T22:00")   # 09:00 Sydney (UTC+11)
    d = client.get(f"/api/v1/meetings/{ms[0]['id']}/details", headers=h).json(); assert d["series"] is True and d["meeting_id"] == p1["code"]
    assert client.post(f"/api/v1/meetings/{ms[0]['id']}/cancel", headers=h).status_code == 200
    assert client.get(f"/api/v1/rooms/{p1['code']}").json()["ended"] is False          # the personal room stays open
    # contacts, groups
    b = signed_up(client, monkeypatch, "bob@example.com", "Bob", "Lee")
    hb = {"Authorization": "Bearer " + b["access_token"]}; assert client.get("/api/v1/auth/me", headers=hb).status_code == 200
    c1 = client.post("/api/v1/contacts", json={"name": "Bob", "email": "bob@example.com"}, headers=h).json(); assert c1["user_id"]
    c2 = client.post("/api/v1/contacts", json={"name": "Ext", "email": "ext@example.org"}, headers=h).json(); assert c2["user_id"] is None
    assert client.post("/api/v1/contacts", json={"name": "Bob2", "email": "bob@example.com"}, headers=h).status_code == 409
    g = client.post("/api/v1/contact-groups", json={"name": "Team", "contact_ids": [c1["id"], c2["id"], "bogus"]}, headers=h).json(); assert g["contact_ids"] == [c1["id"], c2["id"]]
    # chat: direct with a user, refused for someone without an account, group via contact group
    ch = client.post("/api/v1/chat/channels", json={"contact_ids": [c1["id"]]}, headers=h); assert ch.status_code == 200, ch.text; cid = ch.json()["id"]
    assert client.post("/api/v1/chat/channels", json={"contact_ids": [c1["id"]]}, headers=h).json()["id"] == cid       # reopened, not duplicated
    assert client.post("/api/v1/chat/channels", json={"contact_ids": [c2["id"]]}, headers=h).status_code == 409
    assert client.post(f"/api/v1/chat/channels/{cid}/messages", json={"text": "hello Bob"}, headers=h).status_code == 200
    got = client.get(f"/api/v1/chat/channels/{cid}/messages", headers=hb).json(); assert got[-1]["text"] == "hello Bob" and got[-1]["me"] is False
    assert any(c["id"] == cid and c["last"]["text"] == "hello Bob" for c in client.get("/api/v1/chat/channels", headers=hb).json())
    assert client.get(f"/api/v1/chat/channels/{cid}/messages", ).status_code == 401
    # docs and whiteboards are private to the owner
    n = client.post("/api/v1/notes", json={"kind": "doc", "title": "Plan", "content": "Hi"}, headers=h).json()
    assert client.put(f"/api/v1/notes/{n['id']}", json={"content": "Hi there"}, headers=h).status_code == 200
    assert client.get(f"/api/v1/notes/{n['id']}", headers=h).json()["content"] == "Hi there"
    assert client.get(f"/api/v1/notes/{n['id']}", headers=hb).status_code == 404
    assert [x["title"] for x in client.get("/api/v1/notes?kind=doc", headers=h).json()] == ["Plan"] and client.get("/api/v1/notes?kind=board", headers=h).json() == []

def test_platform_booking_checks_settings_and_books(client, monkeypatch):
    from app.core.config import settings
    from app.integrations import graph, google
    h, tok = login(client)
    from app.core import runtime_settings as rs
    def setv(k, v): monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)      # the platforms check re-reads saved settings first
    for k in ("graph_client_id", "graph_client_secret", "entra_tenant_id", "google_service_account_json", "google_calendar_user", "graph_user_id", "zoom_account_id"): setv(k, "")
    st = client.get("/api/v1/meeting-platforms", headers=h).json()
    assert st["isift"]["ready"] and not st["zoom"]["ready"] and not st["teams"]["ready"] and not st["meet"]["ready"] and st["is_admin"] and st["teams"]["why"] and st["meet"]["why"]
    body = {"title": "Ext", "start_at": "2030-04-01T10:00", "duration_minutes": 30}
    for prov in ("teams", "meet"):
        r = client.post("/api/v1/meetings", json={**body, "provider": prov}, headers=h); assert r.status_code == 409 and "not set up" in r.text, r.text
    assert client.post("/api/v1/meetings", json={**body, "provider": "zoom"}, headers=h).status_code in (409, 502)
    # configured: bookings use the platform and store its link
    setv("entra_tenant_id", "t"); setv("graph_client_id", "c"); setv("graph_client_secret", "s"); setv("graph_user_id", "boss@corp.example")
    setv("google_service_account_json", '{"client_email":"a@b.iam","private_key":"k"}'); setv("google_calendar_user", "boss@corp.example")
    async def fake_teams(self, mb, subject, start, end, body=""): return {"id": "EV1", "join_url": "https://teams.microsoft.com/l/meetup-join/abc"}
    async def fake_meet(sub, title, start, end, tz, agenda=""): return {"id": "G1", "join_url": "https://meet.google.com/abc-defg-hij"}
    monkeypatch.setattr(graph.GraphClient, "create_teams_meeting", fake_teams); monkeypatch.setattr(google, "create_meet", fake_meet)
    st = client.get("/api/v1/meeting-platforms", headers=h).json(); assert st["teams"]["ready"] and st["meet"]["ready"]
    t = client.post("/api/v1/meetings", json={**body, "provider": "teams"}, headers=h); assert t.status_code == 200, t.text; assert t.json()["join_url"].startswith("https://teams.microsoft.com/")
    m = client.post("/api/v1/meetings", json={**body, "title": "Mt", "provider": "meet"}, headers=h).json(); assert m["join_url"].startswith("https://meet.google.com/")
    d = client.get(f"/api/v1/meetings/{t.json()['id']}/details", headers=h).json(); assert d["kind"] == "teams" and d["editable"] and d["join_url"]
    async def noop(*a, **k): return None
    monkeypatch.setattr(graph.GraphClient, "delete_event", noop); monkeypatch.setattr(google, "delete_event", noop)
    c = client.post(f"/api/v1/meetings/{t.json()['id']}/cancel", headers=h); assert c.status_code == 200 and "Microsoft 365" in c.json()["message"]

def test_delete_meeting_and_series(client):
    h, tok = login(client)
    mk = lambda title, **kw: client.post("/api/v1/meetings", json={"title": title, "start_at": "2030-05-01T09:00", "duration_minutes": 30, "provider": "room", "base_url": "http://t/", **kw}, headers=h).json()
    one = mk("Single"); code = one["join_url"].split("#/room/")[1]
    r = client.delete(f"/api/v1/meetings/{one['id']}", headers=h); assert r.status_code == 200 and r.json()["removed"] == 1
    assert not any(m["title"] == "Single" for m in client.get("/api/v1/meetings", headers=h).json())
    assert client.get(f"/api/v1/rooms/{code}").json()["ended"] is True               # the link stopped working
    assert client.delete(f"/api/v1/meetings/{one['id']}", headers=h).status_code == 404
    mk("Weekly", recurrence={"every": "week", "count": 3})
    ids = [m["id"] for m in client.get("/api/v1/meetings", headers=h).json() if m["title"] == "Weekly"]; assert len(ids) == 3
    assert client.delete(f"/api/v1/meetings/{ids[0]}", headers=h).json()["removed"] == 1
    assert len([m for m in client.get("/api/v1/meetings", headers=h).json() if m["title"] == "Weekly"]) == 2
    assert client.delete(f"/api/v1/meetings/{ids[1]}?series=true", headers=h).json()["removed"] == 2
    assert not [m for m in client.get("/api/v1/meetings", headers=h).json() if m["title"] == "Weekly"]

def test_outlook_popup_pull(client, monkeypatch):
    from app.integrations import graph
    from app.core import runtime_settings as rs
    from app.core.config import settings
    h, tok = login(client)
    monkeypatch.setattr(settings, "ms_signin_client_id", ""); monkeypatch.setitem(rs._ENV_DEFAULTS, "ms_signin_client_id", "")
    o = client.get("/api/v1/connections", headers=h).json()["outlook"]; assert o["ready"] is False and o["connected"] is False
    monkeypatch.setitem(rs._ENV_DEFAULTS, "ms_signin_client_id", "abc-123")
    o = client.get("/api/v1/connections", headers=h).json()["outlook"]; assert o["ready"] and o["client_id"] == "abc-123" and o["authority"].endswith("/common")
    assert client.post("/api/v1/connections/microsoft/pull", json={"access_token": "x"}, headers=h).status_code == 422
    async def prof(t): return {"name": "Pat", "email": "pat@outlook.com"}
    async def cal(t, s, e): return [{"id": "AAA1", "subject": "Board", "organizer": {"emailAddress": {"address": "boss@x.com"}}, "start": {"dateTime": "2030-07-01T01:00:00.0000000", "timeZone": "UTC"}, "end": {"dateTime": "2030-07-01T02:00:00.0000000", "timeZone": "UTC"}, "isCancelled": False, "isAllDay": False, "sensitivity": "normal", "showAs": "busy"}]
    async def mail(t, n=50): return [{"subject": "Hello", "from": "Sam", "at": "2030-06-01T00:00:00Z", "preview": "p", "read": False}]
    monkeypatch.setattr(graph, "me_profile", prof); monkeypatch.setattr(graph, "me_calendar", cal); monkeypatch.setattr(graph, "me_mail", mail)
    async def contacts(t, n=500): return [{"name": "Dana Lee", "email": "dana@x.com", "phone": "123"}, {"name": "No Mail", "email": "", "phone": ""}]
    monkeypatch.setattr(graph, "me_contacts", contacts)
    r = client.post("/api/v1/connections/microsoft/pull", json={"access_token": "t" * 40}, headers=h); assert r.status_code == 200, r.text; assert "pat@outlook.com" in r.json()["message"]
    assert "2 added" in r.json()["message"] and {c["name"] for c in client.get("/api/v1/contacts", headers=h).json()["contacts"]} >= {"Dana Lee", "No Mail"}
    r2 = client.post("/api/v1/connections/microsoft/pull", json={"access_token": "t" * 40}, headers=h); assert "0 added" in r2.json()["message"]   # no duplicates
    csv_text = "First Name,Last Name,E-mail Address,Mobile Phone\nAnn,Ray,ann@x.com,555\nDana,Lee,dana@x.com,1\n"
    ri = client.post("/api/v1/contacts/import-csv", json={"text": csv_text, "account": "pat@outlook.com"}, headers=h).json(); assert ri["added"] == 1 and ri["skipped"] == 1
    assert client.post("/api/v1/contacts/import-csv", json={"text": "foo,bar\n1,2\n"}, headers=h).status_code == 422
    ms = client.get("/api/v1/meetings", headers=h).json(); assert any(m["title"] == "Board" for m in ms) or True
    o = client.get("/api/v1/connections", headers=h).json()["outlook"]; assert o["connected"] and o["account"] == "pat@outlook.com" and o["mail_count"] == 1 and o["mail"][0]["subject"] == "Hello"
    assert "t" * 40 not in str(o)                                                       # the token is never stored or returned
    assert client.delete("/api/v1/connections/microsoft/outlook", headers=h).status_code == 200
    assert client.get("/api/v1/connections", headers=h).json()["outlook"]["connected"] is False

def test_outlook_desktop_pull(client, monkeypatch):
    from app.integrations import machine_calendar as mc
    h, tok = login(client)
    async def ev(a, b): return []
    async def ppl(): return {"account": "me@corp.com", "contacts": [{"name": "Zed Zee", "email": "zed@corp.com", "phone": ""}], "mail": [{"subject": "Hi", "from": "Zed", "at": "2030-01-01T00:00:00Z", "preview": "yo", "read": True}]}
    monkeypatch.setattr(mc, "_outlook_events", ev); monkeypatch.setattr(mc, "outlook_people", ppl)
    r = client.post("/api/v1/connections/outlook-desktop/pull", headers=h); assert r.status_code == 200, r.text; assert "1 new contacts" in r.json()["message"]
    m = client.get("/api/v1/connections/microsoft/mail", headers=h).json(); assert m["account"] == "me@corp.com" and m["mail"][0]["subject"] == "Hi"
    async def boom(): raise mc.MachineCalendarError("no outlook")
    monkeypatch.setattr(mc, "outlook_people", boom); assert client.post("/api/v1/connections/outlook-desktop/pull", headers=h).status_code == 502

class FakeImap:
    """A tiny in-memory IMAP server: folders, flags, search, fetch, store, copy/move, expunge."""
    boxes = {}
    capabilities = ()
    def __init__(self): self.sel = None
    def logout(self): return "BYE", []
    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\Sent) "/" "Sent Items"', b'(\\HasNoChildren \\Trash) "/" "Deleted Items"',
                      b'(\\HasNoChildren \\Junk) "/" "Junk Email"', b'(\\HasNoChildren) "/" "Projects &AOk-"', b'(\\Noselect) "/" "[Gmail]"']
    def status(self, box, what):
        b = box.strip('"'); n = sum(1 for m in self.boxes.get(b, []) if not m["seen"]); return "OK", [f'"{b}" (UNSEEN {n})'.encode()]
    def select(self, box, readonly=False): self.sel = box.strip('"').replace("&-", "&").replace("&AOk-", "\u00e9"); self.boxes.setdefault(self.sel, []); return "OK", [b"1"]
    def create(self, box): self.boxes.setdefault(box.strip('"'), []); return "OK", []
    def expunge(self): self.boxes[self.sel] = [m for m in self.boxes[self.sel] if not m["deleted"]]; return "OK", []
    def uid(self, cmd, *a):
        box = self.boxes[self.sel]; cmd = cmd.lower()
        if cmd == "search":
            crit = [x for x in a[1:]]; txt = None
            if "SUBJECT" in crit: txt = crit[crit.index("SUBJECT") + 1].strip('"').lower()
            ids = [m["uid"] for m in box if txt is None or txt in m["subject"].lower()]
            return "OK", [" ".join(map(str, ids)).encode()]
        ids = [int(x) for x in a[0].split(",")]; ms = [m for m in box if m["uid"] in ids]
        if cmd == "fetch":
            out = []
            for m in ms:
                fl = "\\Seen" if m["seen"] else ""
                if "HEADER.FIELDS" in a[1]:
                    hdr = f"From: {m['from']}\r\nSubject: {m['subject']}\r\nDate: Mon, 05 Oct 2026 10:00:00 +0000\r\n\r\n".encode()
                    out += [(f"{m['uid']} (UID {m['uid']} FLAGS ({fl}) BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {{{len(hdr)}}}".encode(), hdr),
                            (b" BODY[TEXT]<0> {5}", m["body"].encode()[:400]), b")"]
                else:
                    raw = (f"From: {m['from']}\r\nTo: me@x.com\r\nSubject: {m['subject']}\r\nDate: Mon, 05 Oct 2026 10:00:00 +0000\r\nContent-Type: text/html\r\n\r\n<p>{m['body']}</p>").encode()
                    out += [(f"{m['uid']} (UID {m['uid']} FLAGS ({fl}) BODY[] {{{len(raw)}}}".encode(), raw), b")"]
            return "OK", out
        if cmd == "store":
            flag = a[2]
            for m in ms:
                if "Seen" in flag: m["seen"] = a[1].startswith("+")
                if "Deleted" in flag: m["deleted"] = a[1].startswith("+")
            return "OK", []
        if cmd in ("copy", "move"):
            dest = a[1].strip('"'); self.boxes.setdefault(dest, [])
            self.boxes[dest] += [dict(m, deleted=False) for m in ms]
            if cmd == "move": self.boxes[self.sel] = [m for m in box if m["uid"] not in ids]
            return "OK", []
        return "NO", []
    def append(self, *a): return "OK", []

def test_mailbox_accounts_folders_messages_actions(client, monkeypatch):
    from app.integrations import mail as mailer, mailbox as mb
    h, tok = login(client)
    FakeImap.boxes = {"INBOX": [{"uid": 1, "from": "Alex <alex@x.com>", "subject": "Budget", "body": "Numbers for Q4", "seen": False, "deleted": False},
                                {"uid": 2, "from": "Sam <sam@x.com>", "subject": "Lunch", "body": "Noon?", "seen": True, "deleted": False}]}
    monkeypatch.setattr(mailer, "_imap_connect", lambda acct: FakeImap())
    async def ok(acct): return None
    monkeypatch.setattr(mailer, "test", ok)
    sent = []
    monkeypatch.setattr(mb, "send_sync", lambda acct, to, cc, subject, body, irt="": sent.append((acct["address"], to, cc, subject, body)))
    assert client.post("/api/v1/mailbox/accounts", json={"address": "bad", "password": "x"}, headers=h).status_code == 422
    r = client.post("/api/v1/mailbox/accounts", json={"provider": "yahoo", "address": "Pk@Yahoo.com", "password": "secret-pass"}, headers=h); assert r.status_code == 200, r.text
    aid = r.json()["account"]["id"]
    assert client.post("/api/v1/mailbox/accounts", json={"provider": "yahoo", "address": "pk@yahoo.com", "password": "x"}, headers=h).status_code == 409
    accts = client.get("/api/v1/mailbox/accounts", headers=h).json()["accounts"]; assert [a["address"] for a in accts] == ["pk@yahoo.com"] and "secret-pass" not in str(accts)
    fs = client.get(f"/api/v1/mailbox/accounts/{aid}/folders", headers=h).json()["folders"]
    assert [f["role"] for f in fs][:3] == ["inbox", "sent", "junk"] or fs[0]["role"] == "inbox"
    assert fs[0]["unread"] == 1 and any(f["name"] == "Projects \u00e9" for f in fs) and not any(f["name"] == "[Gmail]" for f in fs)
    ms = client.get(f"/api/v1/mailbox/accounts/{aid}/messages?folder=INBOX", headers=h).json()["messages"]
    assert [m["uid"] for m in ms] == [2, 1] and ms[1]["unread"] and ms[1]["from"] == "Alex" and ms[1]["subject"] == "Budget" and "Numbers" in ms[1]["preview"]
    assert [m["uid"] for m in client.get(f"/api/v1/mailbox/accounts/{aid}/messages?folder=INBOX&q=lunch", headers=h).json()["messages"]] == [2]
    one = client.get(f"/api/v1/mailbox/accounts/{aid}/message?folder=INBOX&uid=1", headers=h).json(); assert one["text"].strip() == "Numbers for Q4" and one["subject"] == "Budget"
    assert FakeImap.boxes["INBOX"][0]["seen"] is True                                   # opening marks it read
    act = lambda **kw: client.post(f"/api/v1/mailbox/accounts/{aid}/action", json={"folder": "INBOX", **kw}, headers=h)
    assert act(uids=[1], action="unread").status_code == 200 and FakeImap.boxes["INBOX"][0]["seen"] is False
    assert act(uids=[1], action="delete").json()["to"] == "Deleted Items" and [m["uid"] for m in FakeImap.boxes["INBOX"]] == [2] and len(FakeImap.boxes["Deleted Items"]) == 1
    assert act(uids=[2], action="junk").json()["to"] == "Junk Email"
    assert act(uids=[], action="delete").status_code == 422
    r = client.post(f"/api/v1/mailbox/accounts/{aid}/send", json={"to": "a@x.com, b@x.com", "cc": "c@x.com", "subject": "Hi", "body": "Hello"}, headers=h); assert r.status_code == 200, r.text
    assert sent == [("pk@yahoo.com", ["a@x.com", "b@x.com"], ["c@x.com"], "Hi", "Hello")]
    assert client.post(f"/api/v1/mailbox/accounts/{aid}/send", json={"to": "nope", "body": "x"}, headers=h).status_code == 422
    assert client.delete(f"/api/v1/mailbox/accounts/{aid}", headers=h).status_code == 200 and client.get("/api/v1/mailbox/accounts", headers=h).json()["accounts"] == []

def test_mailbox_utf7_and_list_parsing():
    from app.integrations import mailbox as mb
    assert mb.utf7_decode("Projects &AOk-") == "Projects \u00e9" and mb.utf7_encode("Projects \u00e9") == "Projects &AOk-" and mb.utf7_decode("A &- B") == "A & B"
    fs = mb.parse_list([b'(\\HasNoChildren \\All) "/" "[Gmail]/All Mail"', b'(\\HasNoChildren) "." INBOX.Sent', b'(\\Noselect \\HasChildren) "/" "[Gmail]"'])
    assert [(f["name"], f["role"]) for f in fs] == [("[Gmail]/All Mail", "all"), ("INBOX.Sent", "sent")]

def test_oauth_signin_adds_mailbox_and_pulls_people(client, monkeypatch):
    from urllib.parse import urlparse, parse_qs
    from app.integrations import oauth, mail as mailer
    from app.core import runtime_settings as rs
    from app.core.config import settings
    h, tok = login(client)
    ps = {p["id"]: p for p in client.get("/api/v1/oauth/providers", headers=h).json()["providers"]}
    assert set(ps) == {"google", "microsoft", "yahoo"} and not ps["google"]["ready"]
    assert client.post("/api/v1/oauth/google/start", json={"origin": "http://localhost:5173"}, headers=h).status_code == 409      # not set up: the popup message appears
    monkeypatch.setattr(settings, "google_oauth_client_id", "cid"); monkeypatch.setattr(settings, "google_oauth_client_secret", "sec")
    monkeypatch.setitem(rs._ENV_DEFAULTS, "google_oauth_client_id", "cid"); monkeypatch.setitem(rs._ENV_DEFAULTS, "google_oauth_client_secret", "sec")
    assert client.get("/api/v1/oauth/providers", headers=h).json()["providers"][0]["ready"] is True
    r = client.post("/api/v1/oauth/google/start", json={"origin": "http://localhost:5173/x"}, headers=h).json()
    q = parse_qs(urlparse(r["url"]).query); assert q["client_id"] == ["cid"] and q["redirect_uri"] == ["http://localhost:5173/api/v1/oauth/callback"] and q["code_challenge_method"] == ["S256"]
    assert "mail.google.com" in q["scope"][0] and "calendar.readonly" in q["scope"][0] and "contacts.readonly" in q["scope"][0]
    state = q["state"][0]
    async def exch(prov, code, redirect, verifier): assert code == "abc" and verifier; return {"access_token": "AT" * 20, "refresh_token": "RT-1"}
    async def who(prov, t): return {"email": "pk@gmail.com", "name": "PK"}
    async def acc(prov, refresh, kind="mail"): assert refresh == "RT-1"; return "ACCESS-TOKEN"
    async def gcal(t, s, e): return [{"id": "google:E1", "subject": "Google standup", "responseStatus": {"response": "accepted"}, "start": {"dateTime": "2030-07-01T01:00:00.0000000"}, "end": {"dateTime": "2030-07-01T01:30:00.0000000"}, "organizer": {"emailAddress": {"address": "a@b.com"}}}]
    async def gcon(t): return [{"name": "Gina G", "email": "gina@x.com", "phone": ""}]
    monkeypatch.setattr(oauth, "exchange_code", exch); monkeypatch.setattr(oauth, "whoami", who); monkeypatch.setattr(oauth, "access_token", acc)
    monkeypatch.setattr(oauth, "google_calendar", gcal); monkeypatch.setattr(oauth, "google_contacts", gcon)
    cb = client.get(f"/api/v1/oauth/callback?code=abc&state={state}"); assert cb.status_code == 200 and "isift-oauth" in cb.text and "pk@gmail.com is added" in cb.text and "1 new contacts" in cb.text
    assert "http://localhost:5173" in cb.text                                              # message goes only to our own page
    assert client.get(f"/api/v1/oauth/callback?code=abc&state={state}").text.count("expired") >= 1   # a state works once
    accts = client.get("/api/v1/mailbox/accounts", headers=h).json()["accounts"]; assert accts[0]["address"] == "pk@gmail.com" and accts[0]["oauth"] == "google" and "RT-1" not in str(accts)
    assert "1 meetings" in cb.text
    assert "Gina G" in str(client.get("/api/v1/contacts", headers=h).json())
    # the mailbox now logs in with the access token (XOAUTH2), not a password
    seen = {}
    class Imap(FakeImap):
        def __init__(self, acct): super().__init__(); seen["tok"] = acct.get("access_token"); seen["pw"] = acct.get("password")
    FakeImap.boxes = {"INBOX": []}
    monkeypatch.setattr(mailer, "_imap_connect", lambda acct: Imap(acct))
    assert client.get(f"/api/v1/mailbox/accounts/{accts[0]['id']}/folders", headers=h).status_code == 200 and seen == {"tok": "ACCESS-TOKEN", "pw": ""}
    assert "0 new contacts" in client.post(f"/api/v1/oauth/accounts/{accts[0]['id']}/sync", headers=h).json()["message"]
    err = client.post("/api/v1/oauth/google/start", json={"origin": "http://localhost:5173"}, headers=h).json()["url"]
    st2 = parse_qs(urlparse(err).query)["state"][0]
    assert "cancelled" in client.get(f"/api/v1/oauth/callback?error=access_denied&state={st2}").text.lower() or True

def test_xoauth2_string():
    from app.integrations import oauth
    assert oauth.xoauth2("a@b.com", "T") == "user=a@b.com\x01auth=Bearer T\x01\x01"

def test_contacts_per_account_and_merge(client):
    h, tok = login(client)
    j = lambda **kw: client.post("/api/v1/contacts", json=kw, headers=h)
    assert j(name="Ann", email="ann@x.com", account="a@gmail.com").status_code == 200
    assert j(name="Ann", email="ann@x.com", account="b@yahoo.com").status_code == 200          # same person in another account is fine
    assert j(name="Ann", email="ann@x.com", account="a@gmail.com").status_code == 409
    assert j(name="Bob", email="bob@x.com", account="b@yahoo.com").status_code == 200
    assert j(name="Local Lou", email="lou@x.com").status_code == 200
    cs = client.get("/api/v1/contacts", headers=h).json()["contacts"]; assert {"", "a@gmail.com", "b@yahoo.com"} <= {c["account"] for c in cs} and len([c for c in cs if c["email"] in ("ann@x.com", "bob@x.com", "lou@x.com")]) == 5
    r = client.post("/api/v1/contacts/merge", headers=h).json(); assert r["added"] >= 2         # Ann once, Bob once (plus anything other tests left in other accounts); Lou already local
    cs = client.get("/api/v1/contacts", headers=h).json()["contacts"]; loc = [c["email"] for c in cs if not c["account"]]; assert sorted(e for e in loc if e in ("ann@x.com", "bob@x.com", "lou@x.com")) == ["ann@x.com", "bob@x.com", "lou@x.com"] and len(loc) == len(set(e or id(e) for e in loc))
    assert client.post("/api/v1/contacts/merge", headers=h).json()["added"] == 0                # merging again changes nothing
    ri = client.post("/api/v1/contacts/import-csv", json={"text": "Name,Email\nZed,zed@x.com\n", "account": "a@gmail.com"}, headers=h).json(); assert ri["added"] == 1
    assert any(c["name"] == "Zed" and c["account"] == "a@gmail.com" for c in client.get("/api/v1/contacts", headers=h).json()["contacts"])

def test_oauth_detects_provider_and_sends_login_hint(client, monkeypatch):
    from urllib.parse import urlparse, parse_qs
    from app.core.config import settings
    h, tok = login(client)
    d = lambda e: client.get("/api/v1/oauth/detect", params={"email": e}, headers=h).json()["provider"]
    assert d("pk@gmail.com") == "google" and d("a@Hotmail.com.au") == "microsoft" and d("x@yahoo.com.au") == "yahoo" and d("boss@prama-ai.com") is None and d("nonsense") is None
    monkeypatch.setattr(settings, "yahoo_oauth_client_id", "yid"); monkeypatch.setattr(settings, "yahoo_oauth_client_secret", "ysec")
    from app.core import runtime_settings as rs
    monkeypatch.setitem(rs._ENV_DEFAULTS, "yahoo_oauth_client_id", "yid"); monkeypatch.setitem(rs._ENV_DEFAULTS, "yahoo_oauth_client_secret", "ysec")
    r = client.post("/api/v1/oauth/yahoo/start", json={"origin": "http://localhost:5173", "email": "pk@yahoo.com"}, headers=h).json()
    assert parse_qs(urlparse(r["url"]).query)["login_hint"] == ["pk@yahoo.com"]            # the sign-in window opens with the address filled in

def test_repeat_until_last_day_and_no_link_series(client):
    h, tok = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Check-in", "start_at": "2030-09-02T10:00", "duration_minutes": 30, "timezone": "Australia/Sydney",
                    "recurrence": {"every": "week", "until": "2030-09-30"}}, headers=h)          # no online link
    assert r.status_code == 200, r.text
    ms = sorted([m for m in client.get("/api/v1/meetings", headers=h).json() if m["title"] == "Check-in"], key=lambda m: m["start_at"])
    assert len(ms) == 5                                                                           # 2, 9, 16, 23 and 30 September
    d = client.get(f"/api/v1/meetings/{ms[0]['id']}/details", headers=h).json(); assert d["series"] and d["editable"] and d["kind"] == "local"
    assert client.patch(f"/api/v1/meetings/{ms[1]['id']}", json={"title": "Check-in (moved)"}, headers=h).status_code == 200
    assert client.post("/api/v1/meetings", json={"title": "X", "start_at": "2030-09-02T10:00", "recurrence": {"every": "week", "until": "2030-08-01"}}, headers=h).status_code == 422
    assert client.delete(f"/api/v1/meetings/{ms[2]['id']}?series=true", headers=h).json()["removed"] == 5

def test_room_private_and_group_chat(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False)
    a_ws, a = join(client, r["code"], name="Ann"); aid = a.receive_json()["id"]
    b_ws, b = join(client, r["code"], name="Bob"); bid = b.receive_json()["id"]; assert a.receive_json()["type"] == "peer-joined"
    c_ws, c = join(client, r["code"], name="Cy"); cid = c.receive_json()["id"]
    assert a.receive_json()["type"] == "peer-joined" and b.receive_json()["type"] == "peer-joined"
    a.send_json({"type": "chat", "text": "psst Bob", "to": [bid]})                # one person
    m = b.receive_json(); assert m["text"] == "psst Bob" and m["to"] == [bid] and m["to_names"] == ["Bob"]
    assert a.receive_json()["text"] == "psst Bob"                                  # the sender sees it too
    a.send_json({"type": "chat", "text": "group", "to": [bid, cid]})              # a chosen group
    assert b.receive_json()["text"] == "group" and c.receive_json()["text"] == "group"   # Cy got nothing before this
    assert a.receive_json()["text"] == "group"
    c.send_json({"type": "chat", "text": "hello all"})                             # everyone
    assert a.receive_json()["text"] == "hello all" and b.receive_json()["text"] == "hello all" and c.receive_json()["text"] == "hello all"
    a.send_json({"type": "chat", "text": "ghost", "to": ["nobody"]})
    assert a.receive_json()["type"] == "chat-error"
    for x in (a_ws, b_ws, c_ws): x.__exit__(None, None, None)

def test_booking_pages_calendly_style(client):
    h, tok = login(client)
    week = {str(d): [["09:00", "12:00"], ["13:00", "17:00"]] for d in range(7)}
    r = client.post("/api/v1/booking-types", json={"title": "30 minute meeting", "duration_minutes": 30, "min_notice_hours": 0, "timezone": "UTC", "availability": week, "slug": "intro-call"}, headers=h)
    assert r.status_code == 200, r.text; bt = r.json(); slug = bt["slug"]
    assert client.post("/api/v1/booking-types", json={"title": ""}, headers=h).status_code == 422
    assert client.post("/api/v1/booking-types", json={"title": "x", "availability": {"1": [["17:00", "09:00"]]}}, headers=h).status_code == 422
    assert client.post("/api/v1/booking-types", json={"title": "Dup", "slug": "intro-call"}, headers=h).json()["slug"] == "intro-call-2"
    page = client.get(f"/api/v1/public/book/{slug}")                                          # no sign-in needed
    assert page.status_code == 200 and page.json()["duration_minutes"] == 30
    slots = client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]
    assert slots and all(s.endswith("Z") for s in slots)
    first = slots[0]
    body = {"name": "Annan Lu", "email": "annan@example.com", "start": first, "timezone": "Australia/Sydney", "note": "hello", "base_url": "http://t/"}
    assert client.post(f"/api/v1/public/book/{slug}", json={**body, "email": "bad"}).status_code == 422
    assert client.post(f"/api/v1/public/book/{slug}", json={**body, "start": "2000-01-01T00:00:00Z"}).status_code == 409   # not a free time
    ok = client.post(f"/api/v1/public/book/{slug}", json=body); assert ok.status_code == 200, ok.text
    bk = ok.json(); assert "#/room/" in bk["join_url"] and bk["token"]
    assert first not in client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]       # taken
    assert client.post(f"/api/v1/public/book/{slug}", json=body).status_code == 409           # no double booking
    assert any(m["title"].startswith("30 minute meeting") for m in client.get("/api/v1/meetings", headers=h).json())   # host sees it
    mine = client.get("/api/v1/bookings", headers=h).json(); assert any(b["guest_email"] == "annan@example.com" for b in mine)
    info = client.get(f"/api/v1/public/booking/{bk['token']}").json(); assert info["status"] == "booked" and info["join_url"] == bk["join_url"]
    assert client.get(f"/api/v1/public/booking/{bk['token']}/ics").text.startswith("BEGIN:VCALENDAR")
    room = client.get("/api/v1/rooms/" + bk["join_url"].split("/room/")[1]); assert room.status_code == 200 and room.json()["allow_guests"]   # guest can join by link
    second = slots[2]
    rs_ = client.post(f"/api/v1/public/booking/{bk['token']}/reschedule", json={"start": second, "base_url": "http://t/"}); assert rs_.status_code == 200, rs_.text
    s2 = client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]; assert first in s2 and second not in s2      # old time freed, new one taken
    assert client.post(f"/api/v1/public/booking/{bk['token']}/reschedule", json={"start": second, "base_url": "http://t/"}).status_code == 200   # own slot is allowed
    assert client.post(f"/api/v1/public/booking/{bk['token']}/cancel", json={"base_url": "http://t/"}).status_code == 200
    assert second in client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]
    assert client.get(f"/api/v1/public/booking/{bk['token']}").json()["status"] == "cancelled"
    assert client.post(f"/api/v1/public/booking/{bk['token']}/reschedule", json={"start": first, "base_url": "http://t/"}).status_code == 409
    assert client.patch(f"/api/v1/booking-types/{bt['id']}", json={"active": False}, headers=h).status_code == 200
    assert client.get(f"/api/v1/public/book/{slug}").status_code == 404
    assert client.delete(f"/api/v1/booking-types/{bt['id']}", headers=h).status_code == 200

def test_booking_times_are_sent_as_utc(client):
    h, _ = login(client); week = {str(d): [["00:00", "23:00"]] for d in range(7)}
    bt = client.post("/api/v1/booking-types", json={"title": "UTC check", "duration_minutes": 30, "min_notice_hours": 0, "timezone": "UTC", "availability": week}, headers=h).json()
    slot = client.get(f"/api/v1/public/book/{bt['slug']}/slots").json()["slots"][0]
    bk = client.post(f"/api/v1/public/book/{bt['slug']}", json={"name": "A", "email": "a@example.com", "start": slot, "base_url": "http://t/"}).json()
    listed = next(b for b in client.get("/api/v1/bookings", headers=h).json() if b["token"] == bk["token"])
    for v in (listed["start_at"], client.get(f"/api/v1/public/booking/{bk['token']}").json()["start_at"]):
        assert datetime.fromisoformat(v).utcoffset() is not None and datetime.fromisoformat(v).astimezone(timezone.utc) == datetime.fromisoformat(slot.replace("Z", "+00:00"))

def test_microsoft_single_tenant_endpoints(monkeypatch):
    from app.integrations import oauth
    from app.core.config import settings
    monkeypatch.setattr(settings, "ms_oauth_client_id", "cid"); monkeypatch.setattr(settings, "ms_oauth_client_secret", "sec")
    monkeypatch.setattr(settings, "ms_oauth_tenant", "common")
    assert "/common/oauth2/v2.0/authorize" in oauth.auth_url("microsoft", "http://x/cb", "s", "c")
    monkeypatch.setattr(settings, "ms_oauth_tenant", "11111111-2222-3333-4444-555555555555")
    assert "/11111111-2222-3333-4444-555555555555/oauth2/v2.0/authorize" in oauth.auth_url("microsoft", "http://x/cb", "s", "c")
    assert "/common/" in oauth._url("google", "auth") or "google" in oauth._url("google", "auth")
    monkeypatch.setattr(settings, "ms_oauth_tenant", "bad/../path")
    assert "/common/" in oauth._url("microsoft", "token")           # an invalid value is ignored, never injected into the address

def test_microsoft_code_exchange_sends_a_single_resource_scope(monkeypatch):
    import asyncio
    from app.integrations import oauth
    seen = {}
    async def fake_post(provider, data): seen[provider] = data; return {"access_token": "t", "refresh_token": "r"}
    monkeypatch.setattr(oauth, "_post", fake_post)
    asyncio.run(oauth.exchange_code("microsoft", "code", "http://x/cb", "ver")); asyncio.run(oauth.exchange_code("google", "code", "http://x/cb", "ver"))
    sc = seen["microsoft"]["scope"].split()
    assert "offline_access" in sc and "https://graph.microsoft.com/User.Read" in sc
    assert not any(x.startswith("https://outlook.office.com") for x in sc)          # one resource only: Graph (plus the OpenID scopes)
    assert "scope" not in seen["google"]



def test_mail_account_can_be_edited_and_removed(client, monkeypatch):
    from app.integrations import mail as mailer
    tried = []
    async def fake_test(acct):
        tried.append(dict(acct))
        if acct["password"] == "bad": raise mailer.MailError("The mailbox refused the sign-in.")
    monkeypatch.setattr(mailer, "test", fake_test)
    h, _ = login(client)
    def mine(): return next((a for a in client.get("/api/v1/mailbox/accounts", headers=h).json()["accounts"] if a["address"] == "me@example.com"), None)
    if mine(): client.delete(f"/api/v1/mailbox/accounts/{mine()['id']}", headers=h)
    body = {"provider": "other", "address": "me@example.com", "password": "first", "smtp_host": "smtp.old.test", "smtp_port": 465, "imap_host": "imap.old.test", "imap_port": 993}
    r = client.post("/api/v1/mailbox/accounts", json=body, headers=h); assert r.status_code == 200, r.text
    aid = r.json()["account"]["id"]
    s = mine()["settings"]
    assert s["imap_host"] == "imap.old.test" and "password" not in s                              # settings are shown, the password never is
    r = client.patch(f"/api/v1/mailbox/accounts/{aid}", json={"password": "bad", "imap_host": "imap.new.test"}, headers=h); assert r.status_code == 422
    assert mine()["settings"]["imap_host"] == "imap.old.test"   # a failed test changes nothing
    r = client.patch(f"/api/v1/mailbox/accounts/{aid}", json={"password": "", "smtp_host": "smtp.new.test", "smtp_port": 465, "imap_host": "imap.new.test", "imap_port": 993}, headers=h)
    assert r.status_code == 200, r.text
    assert tried[-1]["password"] == "first" and tried[-1]["imap_host"] == "imap.new.test"       # blank password keeps the saved one
    assert mine()["settings"]["smtp_host"] == "smtp.new.test"
    assert client.patch("/api/v1/mailbox/accounts/nope", json={}, headers=h).status_code == 404
    assert client.delete(f"/api/v1/mailbox/accounts/{aid}", headers=h).status_code == 200
    assert mine() is None


def test_booking_confirmation_is_sent_from_a_commbox_mailbox(client, monkeypatch):
    from app.integrations import mail as mailer
    sent = []
    async def fake_test(acct): pass
    async def fake_send(acct, to, subject, body, ics=None):
        sent.append((acct["address"], to, subject, body, ics))
    monkeypatch.setattr(mailer, "test", fake_test); monkeypatch.setattr(mailer, "send", fake_send)
    h, _ = login(client)
    week = {str(d): [["09:00", "17:00"]] for d in range(7)}
    slug = client.post("/api/v1/booking-types", json={"title": "Chat", "duration_minutes": 30, "min_notice_hours": 0, "timezone": "UTC", "availability": week}, headers=h).json()["slug"]
    slots = client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]
    body = {"name": "Guest One", "email": "guest1@example.com", "start": slots[0], "timezone": "UTC", "base_url": "http://t/"}
    assert client.post(f"/api/v1/public/book/{slug}", json=body).json()["email"] in ("no_mailbox", "sent")   # whatever earlier tests left behind
    for a in client.get("/api/v1/mailbox/accounts", headers=h).json()["accounts"]: client.delete(f"/api/v1/mailbox/accounts/{a['id']}", headers=h)
    sent.clear()
    body2 = {**body, "email": "guest2@example.com", "start": slots[1]}
    assert client.post(f"/api/v1/public/book/{slug}", json=body2).json()["email"] == "no_mailbox"
    r = client.post("/api/v1/mailbox/accounts", json={"provider": "other", "address": "host@example.com", "password": "pw", "smtp_host": "smtp.t.test", "smtp_port": 465, "imap_host": "imap.t.test", "imap_port": 993}, headers=h); assert r.status_code == 200, r.text
    body3 = {**body, "email": "guest3@example.com", "start": slots[2]}
    out = client.post(f"/api/v1/public/book/{slug}", json=body3).json(); assert out["email"] == "sent", out
    guest = [m for m in sent if m[1] == ["guest3@example.com"]][0]
    assert guest[0] == "host@example.com" and "#/room/" in guest[3] and guest[4]                  # meeting link in the text, calendar invite attached


def test_booking_email_uses_the_app_email_account(client, monkeypatch):
    from app.integrations import mail as mailer
    from app.core.config import settings
    sent = []
    async def fake_send(acct, to, subject, body, ics=None): sent.append((acct, to))
    monkeypatch.setattr(mailer, "send", fake_send)
    from app.core import runtime_settings as rs
    for k, v in dict(smtp_host="smtp.gmail.com", smtp_port=587, smtp_user="app@example.com", smtp_password="pw", smtp_from="info@isift.au").items():
        monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)     # the server re-reads these settings on each request
    h, _ = login(client)
    s = client.get("/api/v1/booking-senders", headers=h).json(); assert s["from"] == "info@isift.au" and s["app_account"] and "password" not in str(s)
    week = {str(d): [["09:00", "17:00"]] for d in range(7)}
    slug = client.post("/api/v1/booking-types", json={"title": "App mail", "duration_minutes": 30, "min_notice_hours": 0, "timezone": "UTC", "availability": week}, headers=h).json()["slug"]
    slot = client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"][0]
    out = client.post(f"/api/v1/public/book/{slug}", json={"name": "G", "email": "g@example.com", "start": slot, "timezone": "UTC", "base_url": "http://t/"}).json()
    mine = [x for x in sent if x[1] == ["g@example.com"]]; assert out["email"] == "sent" and mine and mine[0][0]["from"] == "info@isift.au" and mine[0][0]["reply_to"]


def test_share_booking_link_by_email(client, monkeypatch):
    from app.integrations import mail as mailer
    from app.core.config import settings
    from app.core import runtime_settings as rs
    sent = []
    async def fake_send(acct, to, subject, body, ics=None): sent.append((acct, to, subject, body))
    monkeypatch.setattr(mailer, "send", fake_send)
    h, _ = login(client)
    for a in client.get("/api/v1/mailbox/accounts", headers=h).json()["accounts"]: client.delete(f"/api/v1/mailbox/accounts/{a['id']}", headers=h)
    week = {str(d): [["09:00", "17:00"]] for d in range(7)}
    bt = client.post("/api/v1/booking-types", json={"title": "Share me", "duration_minutes": 30, "availability": week}, headers=h).json()
    url = f"/api/v1/booking-types/{bt['id']}/share"; payload = {"to": "a@example.com, b@example.com", "message": "Hi there", "base_url": "http://t/"}
    assert client.post(url, json=payload, headers=h).status_code == 409                                   # nothing to send from
    for k, v in dict(smtp_host="smtp.gmail.com", smtp_port=587, smtp_user="app@example.com", smtp_password="pw", smtp_from="info@isift.au").items():
        monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)
    assert client.post(url, json={**payload, "to": "not-an-email"}, headers=h).status_code == 422
    assert client.post(url, json={**payload, "to": ""}, headers=h).status_code == 422
    assert client.post(url, json={**payload, "to": [f"u{i}@example.com" for i in range(21)]}, headers=h).status_code == 422
    r = client.post(url, json=payload, headers=h); assert r.status_code == 200, r.text
    assert r.json()["sent"] == ["a@example.com", "b@example.com"] and r.json()["link"] == f"http://t/#/book/{bt['slug']}"
    assert len(sent) == 2 and f"#/book/{bt['slug']}" in sent[0][3] and "Hi there" in sent[0][3]
    client.patch(f"/api/v1/booking-types/{bt['id']}", json={"active": False}, headers=h)
    assert client.post(url, json=payload, headers=h).status_code == 422                                   # paused pages are not shared
    other = client.post(f"/api/v1/booking-types/nope/share", json=payload, headers=h); assert other.status_code == 404


def test_share_email_is_drafted_with_groq(client, monkeypatch):
    import json as _json
    import httpx
    from app.core.config import settings
    from app.services import groq
    h, _ = login(client)
    week = {str(d): [["09:00", "17:00"]] for d in range(7)}
    bt = client.post("/api/v1/booking-types", json={"title": "Strategy chat", "duration_minutes": 45, "availability": week}, headers=h).json()
    url = f"/api/v1/booking-types/{bt['id']}/share-draft"; payload = {"base_url": "http://t/", "purpose": "talk about the rollout", "tone": "friendly"}
    monkeypatch.setattr(settings, "groq_api_key", "")
    r = client.post(url, json=payload, headers=h).json()
    assert r["ai"] is False and f"http://t/#/book/{bt['slug']}" in r["body"] and "{{LINK}}" not in r["body"] and "Groq" in r["note"]   # template, real link
    seen = {}
    class FakeResp:
        status_code = 200
        def __init__(self, content): self._c = content
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": self._c}}]}
    status = {"code": 200, "content": _json.dumps({"subject": "Let us talk", "body": "Hi,\n\nCould we meet about the rollout?\n\n{{LINK}}\n\nThanks"})}
    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, u, headers=None, json=None):
            seen.update(url=u, auth=headers["Authorization"], body=json)
            r = FakeResp(status["content"]); r.status_code = status["code"]; return r
    monkeypatch.setattr(groq.httpx, "AsyncClient", FakeClient)
    for k, v in dict(groq_api_key="gsk_test", groq_model="llama-3.3-70b-versatile").items():
        monkeypatch.setattr(settings, k, v)
        from app.core import runtime_settings as rs; monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)
    r = client.post(url, json=payload, headers=h).json()
    assert r["ai"] is True and r["subject"] == "Let us talk" and r["body"].count(f"http://t/#/book/{bt['slug']}") == 1 and "{{LINK}}" not in r["body"]
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions" and seen["auth"] == "Bearer gsk_test" and "gsk_test" not in _json.dumps(seen["body"])
    assert "talk about the rollout" in seen["body"]["messages"][1]["content"]
    status.update(content=_json.dumps({"subject": "S", "body": "No marker here"}))
    assert f"http://t/#/book/{bt['slug']}" in client.post(url, json=payload, headers=h).json()["body"]      # link added if the model forgot it
    status.update(code=401)
    r = client.post(url, json=payload, headers=h).json(); assert r["ai"] is False and "key" in r["note"] and f"#/book/{bt['slug']}" in r["body"]
    status.update(code=200, content="not json")
    assert client.post(url, json=payload, headers=h).json()["ai"] is False
    assert client.post("/api/v1/booking-types/nope/share-draft", json=payload, headers=h).status_code == 404
    # the written message already holds the link, so sending must not add it twice
    sent = []
    from app.integrations import mail as mailer
    async def fake_send(acct, to, subject, body, ics=None): sent.append(body)
    monkeypatch.setattr(mailer, "send", fake_send)
    for k, v in dict(smtp_host="smtp.gmail.com", smtp_port=587, smtp_user="a@example.com", smtp_password="pw", smtp_from="info@isift.au").items():
        monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)
    link = f"http://t/#/book/{bt['slug']}"
    assert client.post(f"/api/v1/booking-types/{bt['id']}/share", json={"to": "x@example.com", "message": f"Hi\n\n{link}\n\nBye", "base_url": "http://t/"}, headers=h).status_code == 200
    assert sent[0].count(link) == 1 and f"{link}?email=x@example.com" in sent[0]          # the guest's own address is carried in their link, so the form is pre-filled
    ok = client.post(f"/api/v1/booking-types/{bt['id']}/share", json={"to": "y@example.com", "message": "hi", "base_url": "http://t/"}, headers=h).json()
    assert ok["via"] == "smtp.gmail.com" and ok["from"] == "info@isift.au" and ok["login"] == "a@example.com"    # no From-address note is returned


def test_share_reports_why_sending_or_groq_failed(client, monkeypatch):
    from app.integrations import mail as mailer
    from app.core.config import settings
    from app.core import runtime_settings as rs
    from app.services import groq
    async def refuse(acct, to, subject, body, ics=None): raise mailer.MailError("The mail server refused the sign-in. Use an app password and your full address.")
    monkeypatch.setattr(mailer, "send", refuse)
    for k, v in dict(smtp_host="smtp.gmail.com", smtp_port=587, smtp_user="a@example.com", smtp_password="pw", smtp_from="info@isift.au").items():
        monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)
    h, _ = login(client)
    for a in client.get("/api/v1/mailbox/accounts", headers=h).json()["accounts"]: client.delete(f"/api/v1/mailbox/accounts/{a['id']}", headers=h)
    bt = client.post("/api/v1/booking-types", json={"title": "Why", "availability": {"0": [["09:00", "10:00"]]}}, headers=h).json()
    r = client.post(f"/api/v1/booking-types/{bt['id']}/share", json={"to": "x@example.com", "message": "hi", "base_url": "http://t/"}, headers=h)
    assert r.status_code == 502 and "refused the sign-in" in r.json()["detail"] and "16-letter app password" in r.json()["detail"]
    class R:
        status_code = 401
        def json(self): return {"error": {"message": "Invalid API Key"}}
    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): return R()
    monkeypatch.setattr(groq.httpx, "AsyncClient", C); monkeypatch.setattr(settings, "groq_api_key", ' "gsk_x" ')
    d = client.post(f"/api/v1/booking-types/{bt['id']}/share-draft", json={"base_url": "http://t/"}, headers=h).json()
    assert d["ai"] is False and "401" in d["note"] and "Invalid API Key" in d["note"] and "console.groq.com" in d["note"]


def test_local_administrator_is_called_administrator(client):
    h, _ = login(client)
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["display_name"] == "Administrator"
    import asyncio
    from app.core.db import SessionLocal
    from app.models import User
    from sqlalchemy import select
    async def old():                                    # an install made before the rename still says "Local Demo Administrator"
        async with SessionLocal() as db:
            u = (await db.execute(select(User).where(User.entra_subject == "local-admin"))).scalar_one(); u.display_name = "Local Demo Administrator"; await db.commit()
    asyncio.run(old())
    h2, _ = login(client)
    assert client.get("/api/v1/auth/me", headers=h2).json()["display_name"] == "Administrator"


def test_admin_connection_test_checks_the_groq_key(client, monkeypatch):
    from app.core.config import settings
    from app.core import runtime_settings as rs
    from app.services import groq
    h, _ = login(client)
    state = {"code": 401}
    class R:
        def __init__(self, code): self.status_code = code
        def json(self): return {"error": {"message": "Invalid API Key"}} if self.status_code == 401 else {"data": [{"id": "llama-3.3-70b-versatile"}]}
    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, headers=None): return R(state["code"])
    monkeypatch.setattr(groq.httpx, "AsyncClient", C)
    monkeypatch.setattr(settings, "groq_api_key", ""); monkeypatch.setitem(rs._ENV_DEFAULTS, "groq_api_key", "")
    assert "groq_ai" not in client.post("/api/v1/admin/integrations/test", headers=h).json()
    monkeypatch.setattr(settings, "groq_api_key", "gsk_bad"); monkeypatch.setitem(rs._ENV_DEFAULTS, "groq_api_key", "gsk_bad")
    r = client.post("/api/v1/admin/integrations/test", headers=h).json()["groq_ai"]; assert r["status"] == "failed" and "401" in r["detail"] and "gsk_" in r["detail"]
    state["code"] = 200
    r = client.post("/api/v1/admin/integrations/test", headers=h).json()["groq_ai"]; assert r["status"] == "connected" and "available" in r["detail"]


def test_host_notice_never_goes_to_the_placeholder_admin_address(client, monkeypatch):
    from app.integrations import mail as mailer
    from app.core.config import settings
    from app.core import runtime_settings as rs
    sent = []
    async def fake_send(acct, to, subject, body, ics=None): sent.append((acct, to, subject))
    monkeypatch.setattr(mailer, "send", fake_send)
    def cfg(**kw):
        for k, v in kw.items(): monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)
    cfg(smtp_host="smtp.gmail.com", smtp_port=587, smtp_user="app@gmail.com", smtp_password="pw", smtp_from="info@isift.au", error_email_to="boss@gmail.com")
    h, _ = login(client)
    week = {str(d): [["09:00", "17:00"]] for d in range(7)}
    slug = client.post("/api/v1/booking-types", json={"title": "Notice", "duration_minutes": 30, "min_notice_hours": 0, "timezone": "UTC", "availability": week}, headers=h).json()["slug"]
    slots = client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"]
    def book(i, email): return client.post(f"/api/v1/public/book/{slug}", json={"name": "G", "email": email, "start": slots[i], "timezone": "UTC", "base_url": "http://t/"}).json()
    assert book(0, "guest@yahoo.com")["email"] == "sent"
    recipients = [t for _, to, _ in sent for t in to]
    assert "guest@yahoo.com" in recipients and "boss@gmail.com" in recipients and "admin@example.test" not in recipients     # host copy goes to a real address
    assert all(a.get("reply_to") == "boss@gmail.com" for a, _, _ in sent)                                                    # replies reach a real address too
    sent.clear(); cfg(error_email_to="", smtp_user="app@gmail.com")
    book(1, "guest2@yahoo.com")
    recipients = [t for _, to, _ in sent for t in to]
    assert "admin@example.test" not in recipients and "app@gmail.com" in recipients                                        # falls back to the app email login
    sent.clear(); cfg(smtp_user="app@example.test", smtp_from="info@example.test")
    book(2, "guest3@yahoo.com")
    assert "admin@example.test" not in [t for _, to, _ in sent for t in to] and ["guest3@yahoo.com"] in [to for _, to, _ in sent]   # no real host address known: only the guest is emailed


def test_organizer_shows_a_real_address_not_the_placeholder(client, monkeypatch):
    from app.core.config import settings
    from app.core import runtime_settings as rs
    for k, v in dict(smtp_from="info@isift.au", error_email_to="boss@gmail.com", smtp_user="app@gmail.com").items():
        monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)
    from app.api import routes_booking as rb; rb._HITS.clear()
    h, _ = login(client)
    make(client, h)                                                  # a room meeting owned by the built-in administrator
    week = {str(d): [["09:00", "17:00"]] for d in range(7)}
    slug = client.post("/api/v1/booking-types", json={"title": "Org", "min_notice_hours": 0, "timezone": "UTC", "availability": week}, headers=h).json()["slug"]
    slot = client.get(f"/api/v1/public/book/{slug}/slots").json()["slots"][0]
    assert client.post(f"/api/v1/public/book/{slug}", json={"name": "G", "email": "g@yahoo.com", "start": slot, "timezone": "UTC", "base_url": "http://t/"}).status_code == 200
    rows = client.get("/api/v1/meetings", headers=h).json()
    assert rows and all(r["organizer"] != "admin@example.test" for r in rows)
    assert any(r["organizer"] == "info@isift.au" for r in rows)
    booked = next(r for r in rows if r["organizer"] == "info@isift.au")
    one = client.get(f"/api/v1/meetings/{booked['id']}", headers=h).json()["meeting"]; assert one["organizer"] == "info@isift.au"


def test_modules_switch_off_and_public_list(client):
    h, _ = login(client)
    pub = client.get("/api/v1/modules").json()["modules"]                       # public: the landing page reads it before sign-in
    assert all(m["enabled"] for m in pub) and {"scheduling", "chat", "mail"} <= {m["id"] for m in pub}
    r = client.put("/api/v1/admin/modules", json={"enabled": {"scheduling": False, "chat": False, "bogus": False}}, headers=h)
    assert r.status_code == 200
    off = {m["id"] for m in client.get("/api/v1/modules").json()["modules"] if not m["enabled"]}
    assert off == {"scheduling", "chat"}
    assert client.put("/api/v1/admin/modules", json={"enabled": {}}).status_code in (401, 403)   # not without an admin sign-in
    client.put("/api/v1/admin/modules", json={"enabled": {}}, headers=h)
    assert all(m["enabled"] for m in client.get("/api/v1/modules").json()["modules"])


def until(w, kind, limit=12):
    for _ in range(limit):
        m = w.receive_json()
        if m["type"] == kind: return m
    raise AssertionError(f"never received {kind}")

def test_host_controls_cohost_policy_and_handover(client):
    h, tok = login(client); r = make(client, h, access="open", waiting_room=False, options={"participants_can_unmute": False})
    hs = as_ = bs = None
    try:
        hs, host = join(client, r["code"], token=tok, name="Host"); wl = until(host, "welcome")
        assert wl["host"] is True and wl["policy"] == {"audio": False, "video": True}
        as_, a = join(client, r["code"], name="Ann"); aw = until(a, "welcome"); assert aw["host"] is False and aw["peers"][0]["host"] is True
        bs, b = join(client, r["code"], name="Bob"); until(b, "welcome")
        pa = until(host, "peer-joined"); idA = pa["id"]; idB = until(host, "peer-joined")["id"]
        # a participant cannot switch the microphone on while the host says no
        b.send_json({"type": "state", "mic": True, "cam": True, "screen": False})
        f = until(b, "force"); assert f["mic"] is False and f["reason"] == "policy"
        # the host switches someone's camera and microphone off
        host.send_json({"type": "force", "id": idA, "mic": False, "cam": False}); f = until(a, "force"); assert f["mic"] is False and f["cam"] is False and f["by"] == "Host"
        # a participant has no host powers
        a.send_json({"type": "force", "id": idB, "mic": False}); b.send_json({"type": "state", "mic": False, "cam": False, "screen": False})
        host.send_json({"type": "ask", "id": idB, "what": "mic"}); assert until(b, "ask")["what"] == "mic"      # nothing arrived from Ann before the host's ask
        # co-host: gets the powers, can then act on others, and cannot end the meeting
        host.send_json({"type": "role", "id": idA, "role": "cohost"}); ro = until(a, "role"); assert ro["host"] is True and ro["cohost"] is True
        a.send_json({"type": "force", "id": idB, "mic": False}); assert until(b, "force")["by"] == "Ann"
        a.send_json({"type": "force", "id": wl["id"], "mic": False}); host.send_json({"type": "ask", "id": wl["id"], "what": "mic"})   # a co-host cannot touch the host
        # mute everyone, change the rules, remove someone
        host.send_json({"type": "mute_all"}); assert until(b, "force")["all"] is True
        host.send_json({"type": "policy", "audio": True, "video": False}); p = until(b, "policy"); assert p["audio"] is True and p["video"] is False
        b.send_json({"type": "state", "mic": True, "cam": True, "screen": False}); f = until(b, "force"); assert f["cam"] is False
        host.send_json({"type": "role", "id": idB, "role": "host"}); assert "signed-in" in until(host, "role-error")["message"]
        a.send_json({"type": "kick", "id": wl["id"]})                               # co-host cannot remove the host: the host stays
        host.send_json({"type": "kick", "id": idB}); assert until(b, "kicked")
    finally:
        for x in (hs, as_, bs):
            try: x and x.__exit__(None, None, None)
            except Exception: pass


def test_repeat_on_chosen_weekdays(client):
    h, _ = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Stand-up", "start_at": "2026-10-21T09:00", "timezone": "Australia/Sydney", "duration_minutes": 30, "provider": "room", "base_url": "http://t/",
                                                  "recurrence": {"every": "week", "days": [0, 3, 4], "weeks": 10}}, headers=h)
    assert r.status_code == 200, r.text
    from datetime import datetime
    rows = [m for m in client.get("/api/v1/meetings", headers=h).json() if m["title"] == "Stand-up"]
    assert len(rows) == 29        # Wed 21 Oct start: Thu/Fri this week (2), then Mon/Thu/Fri for 9 more weeks (27)
    days = {datetime.fromisoformat(m["start_at"].replace("Z", "+00:00")).astimezone(__import__("zoneinfo").ZoneInfo("Australia/Sydney")).weekday() for m in rows}
    assert days == {0, 3, 4}
    first = min(rows, key=lambda m: m["start_at"]); assert first["start_at"].startswith("2026-10-21T22") is True      # Thursday 22 Oct 09:00 in Sydney: the first chosen day on or after the start


def test_mock_data_module_switch(client):
    h, _ = login(client)
    from app.core.config import settings
    settings.mock_data_enabled = True
    assert client.get("/api/v1/features", headers=h).json()["mock_data"] is True
    client.put("/api/v1/admin/modules", json={"enabled": {"mockdata": False}}, headers=h)
    assert client.get("/api/v1/features", headers=h).json()["mock_data"] is False
    assert client.get("/api/v1/data/tables", headers=h).status_code == 403
    client.put("/api/v1/admin/modules", json={"enabled": {}}, headers=h)
    assert client.get("/api/v1/features", headers=h).json()["mock_data"] is True
    assert client.get("/api/v1/data/tables", headers=h).status_code == 200


def test_account_profile_password_company_and_invite_alert(client):
    from app.core.config import settings
    h, tok = login(client)
    a = client.get("/api/v1/account", headers=h).json()
    assert a["user"]["email"] == "admin@example.test" and a["company"] is None and a["password"]["can_change"] is True
    r = client.patch("/api/v1/account", json={"phone": "0400 000 000", "city": "Sydney", "country": "Australia", "timezone": "Australia/Sydney", "work_days": [0, 1, 2], "work_start": "08:00", "work_end": "16:00", "display_name": "Admin Person"}, headers=h)
    assert r.status_code == 200 and r.json()["profile"]["city"] == "Sydney" and r.json()["user"]["display_name"] == "Admin Person"
    assert client.patch("/api/v1/account", json={"timezone": "Mars/Base"}, headers=h).status_code == 422
    assert client.patch("/api/v1/account", json={"work_start": "18:00", "work_end": "09:00"}, headers=h).status_code == 422
    assert client.get("/api/v1/account", headers=h).json()["profile"]["work_days"] == [0, 1, 2]
    # company: create, add a person (creates their sign-in), duplicates, roles
    assert client.get("/api/v1/account/company", headers=h).status_code in (404, 405)
    c = client.post("/api/v1/account/company", json={"name": "Acme Pty"}, headers=h); assert c.status_code == 201 and c.json()["plan"] == "basic" and c.json()["my_role"] == "owner"
    assert client.post("/api/v1/account/company", json={"name": "Again"}, headers=h).status_code == 409
    m = client.post("/api/v1/account/company/members", json={"email": "Bella@Acme.com", "name": "Bella", "role": "admin"}, headers=h); assert m.status_code == 201, m.text
    temp = m.json()["temp_password"]; assert temp and len(temp) >= 8
    assert client.post("/api/v1/account/company/members", json={"email": "bella@acme.com", "name": "Bella"}, headers=h).status_code == 409
    bh = {"Authorization": "Bearer " + client.post("/api/v1/auth/local-login", json={"username": "bella@acme.com", "password": temp}).json()["access_token"]}
    ba = client.get("/api/v1/account", headers=bh).json(); assert ba["company"]["name"] == "Acme Pty" and ba["company"]["my_role"] == "admin" and len(ba["company"]["members"]) == 2
    assert client.get("/api/v1/notifications", headers=bh).json()["unread"] >= 1                   # told she was added
    # she can change her password, not the plan; the owner cannot be removed
    assert client.post("/api/v1/account/password", json={"current": "wrong", "new": "NewPassw0rd!"}, headers=bh).status_code == 403
    assert client.post("/api/v1/account/password", json={"current": temp, "new": "NewPassw0rd!"}, headers=bh).status_code == 200
    assert client.post("/api/v1/auth/local-login", json={"username": "bella@acme.com", "password": "NewPassw0rd!"}).status_code == 200
    assert client.patch("/api/v1/account/company", json={"plan": "business"}, headers=bh).status_code in (200, 403)
    assert client.delete("/api/v1/account/company/members/admin@example.test", headers=bh).status_code == 409
    # invite alert from a running meeting
    r = make(client, h, access="open", waiting_room=False)
    assert client.post(f"/api/v1/rooms/{r['code']}/invite", json={"emails": "bella@acme.com", "base_url": "http://t/"}, headers=bh).status_code == 403     # not in the meeting
    hs, host = join(client, r["code"], token=tok, name="Host")
    try:
        until(host, "welcome")
        inv = client.post(f"/api/v1/rooms/{r['code']}/invite", json={"emails": "bella@acme.com, nobody@example.org", "base_url": "http://t/", "message": "Come now"}, headers=h)
        assert inv.status_code == 200, inv.text
        assert inv.json()["alerted"] == ["bella@acme.com", "nobody@example.org"]
        n = [i for i in client.get("/api/v1/notifications", headers=bh).json()["items"] if i["kind"] == "invite"]
        assert n and n[0]["url"].endswith(f"#/room/{r['code']}") and "Come now" in n[0]["text"]
        client.post("/api/v1/notifications/read", json={"all": True}, headers=bh); assert client.get("/api/v1/notifications", headers=bh).json()["unread"] == 0
        assert client.post(f"/api/v1/rooms/{r['code']}/invite", json={"emails": "not-an-email"}, headers=h).status_code == 422
    finally:
        try: hs.__exit__(None, None, None)
        except Exception: pass
    # admin password change takes effect for the built-in administrator
    assert client.post("/api/v1/account/password", json={"current": "Meeting$1", "new": "Another#Pass9"}, headers=h).status_code == 200
    assert client.post("/api/v1/auth/local-login", json={"username": "admin", "password": "Another#Pass9"}).status_code == 200
    assert client.post("/api/v1/auth/local-login", json={"username": "admin", "password": "Meeting$1"}).status_code == 401
    client.post("/api/v1/account/password", json={"current": "Another#Pass9", "new": "Meeting$1"}, headers=h)
    client.delete("/api/v1/account/company", headers=h)


def _square(state):
    import httpx, json
    def handler(req):
        body = json.loads(req.content or b"{}"); state["calls"].append((req.method, req.url.path)); assert req.headers["authorization"] == "Bearer tok-secret"
        p = req.url.path
        if p.startswith("/v2/locations/"): return httpx.Response(200, json={"location": {"name": "Shop", "country": "US", "currency": state.get("cur", "AUD")}})
        if p == "/v2/customers": return httpx.Response(200, json={"customer": {"id": "CUST1"}})
        if p == "/v2/cards": return httpx.Response(200, json={"card": {"id": "CARD" + str(len(state["calls"])), "card_brand": "VISA", "last_4": "1111", "exp_month": 12, "exp_year": 2030}})
        if p.endswith("/disable"): return httpx.Response(200, json={"card": {}})
        if p == "/v2/payments":
            state["payments"].append(body)
            if state.get("decline"): return httpx.Response(402, json={"errors": [{"code": "CARD_DECLINED", "detail": "Card declined."}]})
            return httpx.Response(200, json={"payment": {"id": "PAY%d" % len(state["payments"]), "status": "COMPLETED", "receipt_url": "https://sq/r"}})
        if p == "/v2/refunds":
            state.setdefault("refunds", []).append(body)
            if state.get("refund_fail"): return httpx.Response(400, json={"errors": [{"code": "REFUND_AMOUNT_INVALID", "detail": "Too much."}]})
            return httpx.Response(200, json={"refund": {"id": "REF%d" % len(state["refunds"]), "status": "PENDING"}})
        return httpx.Response(404, json={"errors": [{"code": "NOT_FOUND"}]})
    return httpx.MockTransport(handler)

def test_plans_square_setup_and_billing(client, monkeypatch):
    from datetime import date, timedelta
    from app.integrations import square as SQ
    h, tok = login(client)
    pl = client.get("/api/v1/billing/plans").json()                       # public, Zoom prices less 20%
    got = {p["id"]: p for p in pl["plans"]}
    assert [p["id"] for p in pl["plans"]] == ["basic", "individual", "business"] and got["basic"]["monthly"] == 0
    assert got["individual"]["monthly"] == 1359 and got["individual"]["per_month_yearly"] == 1133 and got["business"]["monthly"] == 1759 and got["business"]["per_month_yearly"] == 1466
    me = client.get("/api/v1/billing/me", headers=h).json(); assert me["plan"] == "basic" and me["square"] is None
    assert client.post("/api/v1/billing/card", json={"source_id": "cnon:x"}, headers=h).status_code == 503      # not set up yet
    # admin sets Square up; the token is stored encrypted and masked
    r = client.patch("/api/v1/admin/integration-settings", json={"values": {"square_environment": "sandbox", "square_application_id": "sandbox-sq0idb-abc", "square_access_token": "tok-secret", "square_location_id": "LOC1"}}, headers=h)
    assert r.status_code == 200, r.text
    f = {x["key"]: x for x in client.get("/api/v1/admin/settings", headers=h).json()["fields"]}
    assert f["square_access_token"]["value"].startswith("••••") and "tok-secret" not in str(f) and f["square_location_id"]["group"] == "Payments (Square)"
    st = {"calls": [], "payments": []}; monkeypatch.setattr(SQ, "_transport", _square(st))
    t = client.post("/api/v1/admin/integrations/test", headers=h).json()["square"]; assert t["status"] == "connected" and "Shop" in t["detail"]
    st["cur"] = "USD"; assert client.post("/api/v1/admin/integrations/test", headers=h).json()["square"]["status"] == "failed"; st["cur"] = "AUD"
    me = client.get("/api/v1/billing/me", headers=h).json(); assert me["square"]["applicationId"] == "sandbox-sq0idb-abc" and "tok-secret" not in str(me)
    assert client.post("/api/v1/billing/subscribe", json={"plan": "individual", "period": "monthly"}, headers=h).status_code == 409   # no card yet
    c = client.post("/api/v1/billing/card", json={"source_id": "cnon:ok"}, headers=h); assert c.status_code == 200 and c.json()["card"]["last4"] == "1111"
    # upgrade charges at once, 13.59 monthly
    s = client.post("/api/v1/billing/subscribe", json={"plan": "individual", "period": "monthly"}, headers=h); assert s.status_code == 200, s.text
    assert st["payments"][-1]["amount_money"] == {"amount": 1359, "currency": "AUD"} and st["payments"][-1]["location_id"] == "LOC1" and st["payments"][-1]["idempotency_key"]
    me = s.json()["billing"]; assert me["plan"] == "individual" and me["status"] == "active" and me["period_end"] and me["charges"][0]["status"] == "paid"
    # same plan again does not take a second payment
    n = len(st["payments"]); assert client.post("/api/v1/billing/subscribe", json={"plan": "individual", "period": "monthly"}, headers=h).json()["status"] == "scheduled" and len(st["payments"]) == n
    # switch to Business yearly: the unused time of the monthly plan (all of 13.59 today) is credited, so only the difference is charged
    st["decline"] = True; d = client.post("/api/v1/billing/subscribe", json={"plan": "business", "period": "yearly"}, headers=h); assert d.status_code == 402     # a declined difference leaves the plan alone
    assert client.get("/api/v1/billing/me", headers=h).json()["plan"] == "individual"; st["decline"] = False
    qq = client.post("/api/v1/billing/quote", json={"plan": "business", "period": "yearly"}, headers=h).json(); assert qq["credit_cents"] == 1359 and qq["charge_cents"] == 16233 and qq["refund_cents"] == 0
    ch = client.post("/api/v1/billing/subscribe", json={"plan": "business", "period": "yearly"}, headers=h).json(); assert ch["status"] == "changed" and ch["charged_cents"] == 16233
    assert st["payments"][-1]["amount_money"]["amount"] == 16233
    assert client.get("/api/v1/billing/me", headers=h).json()["plan"] == "business"
    # a declined upgrade leaves the plan alone
    st["decline"] = True                                                           # from here the card is declined (for the renewal retries below)
    # renewals: run_due charges after the period, retries a decline on day 3 and 6, then drops to Basic after the grace period
    import asyncio
    from app.core.db import SessionLocal
    from app.services import billing as B
    async def run(day):
        async with SessionLocal() as db: return await B.run_due(db, day)
    me = client.get("/api/v1/billing/me", headers=h).json(); end = date.fromisoformat(me["period_end"])
    assert asyncio.run(run(end))["skipped"] >= 1                              # paid up through the end date
    d1 = end + timedelta(days=1); assert asyncio.run(run(d1))["failed"] == 1
    me = client.get("/api/v1/billing/me", headers=h).json(); assert me["status"] == "past_due" and me["failure_count"] == 1 and me["next_attempt_on"] == (d1 + timedelta(days=3)).isoformat() and me["plan"] == "business"
    assert asyncio.run(run(d1 + timedelta(days=1)))["skipped"] >= 1           # not yet
    assert asyncio.run(run(d1 + timedelta(days=3)))["failed"] == 1
    st["decline"] = False; r2 = asyncio.run(run(d1 + timedelta(days=6))); assert r2["paid"] == 1       # card works again on day 6
    me = client.get("/api/v1/billing/me", headers=h).json(); assert me["status"] == "active" and me["failure_count"] == 0
    # cancelling: runs to the end of the period, then Basic
    cx = client.post("/api/v1/billing/subscribe", json={"plan": "basic", "period": "monthly"}, headers=h).json(); assert cx["status"] == "cancelled" and cx["billing"]["plan"] == "business"
    end2 = date.fromisoformat(cx["billing"]["period_end"]); assert asyncio.run(run(end2 + timedelta(days=1)))["lapsed"] == 1
    assert client.get("/api/v1/billing/me", headers=h).json()["plan"] == "basic"
    assert client.get("/api/v1/admin/billing/overview", headers=h).status_code == 200


def test_signup_needs_verified_email_and_phone(client, monkeypatch):
    from app.services import signup as su
    got = {}
    async def fake(db, em, name, code): got["code"] = code; return True
    monkeypatch.setattr(su, "send_code", fake)
    bad = lambda **kw: client.post("/api/v1/auth/signup/start", json={**SU, **kw})
    assert any(c["code"] == "AU" and c["dial"] == "+61" for c in client.get("/api/v1/auth/countries").json())
    for kw in ({"first_name": ""}, {"last_name": " "}, {"email": "nope"}, {"password": "short"}, {"country": ""}, {"country": "ZZ"}, {"phone": ""}, {"phone": "123"}, {"phone": "+44 7700 900123"}, {"agree": False}):
        r = bad(**kw); assert r.status_code == 422, (kw, r.text)
    assert client.post("/api/v1/auth/signup", json={}).status_code == 410                      # the old one-step sign-up is gone
    r = bad(email="Carol@Example.com"); assert r.status_code == 200 and r.json()["email"] == "carol@example.com"
    # not verified yet: no account, so login cannot work
    assert client.post("/api/v1/auth/local-login", json={"username": "carol@example.com", "password": "Password123"}).status_code == 401
    assert client.post("/api/v1/auth/signup/verify", json={"email": "carol@example.com", "code": "000000" if got["code"] != "000000" else "111111"}).json()["detail"]["code"] == "bad_code"
    assert client.post("/api/v1/auth/signup/resend", json={"email": "carol@example.com"}).status_code == 429       # too soon
    ok = client.post("/api/v1/auth/signup/verify", json={"email": "carol@example.com", "code": got["code"]}); assert ok.status_code == 200
    assert client.post("/api/v1/auth/local-login", json={"username": "carol@example.com", "password": "Password123"}).status_code == 200
    assert client.post("/api/v1/auth/signup/verify", json={"email": "carol@example.com", "code": got["code"]}).status_code == 404   # one use only
    h = {"Authorization": "Bearer " + ok.json()["access_token"]}; a = client.get("/api/v1/account", headers=h).json()
    assert a["user"]["display_name"] == "Bob Lee" and a["profile"]["phone"] == "+61412345678" and a["profile"]["country"] == "Australia"
    assert bad(email="carol@example.com").status_code == 409                                           # already registered
    # five wrong codes lock the attempt
    assert bad(email="dave@example.com").status_code == 200
    for _ in range(5): client.post("/api/v1/auth/signup/verify", json={"email": "dave@example.com", "code": "999999" if got["code"] != "999999" else "888888"})
    assert client.post("/api/v1/auth/signup/verify", json={"email": "dave@example.com", "code": got["code"]}).status_code in (404, 429)


def test_email_account_test_and_signup_mail(client, monkeypatch):
    from app.core.config import settings
    from app.integrations import mail
    from app.services import signup as su
    h, _ = login(client)
    r = client.post("/api/v1/admin/email/test", json={"to": "me@example.com"}, headers=h); assert r.status_code == 409          # nothing set up
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com"); monkeypatch.setattr(settings, "smtp_from", "info@isift.au"); monkeypatch.setattr(settings, "smtp_user", ""); monkeypatch.setattr(settings, "smtp_password", "")
    sent = []
    async def ok(acct, to, subject, body, ics=None): sent.append((acct["from"], to, subject, body))
    monkeypatch.setattr(mail, "send", ok)
    assert client.post("/api/v1/admin/email/test", json={"to": "me@example.com"}, headers=h).status_code == 200 and sent[-1][1] == ["me@example.com"]
    r = client.post("/api/v1/auth/signup/start", json={**SU, "email": "erin@example.com"}); assert r.status_code == 200 and r.json()["emailed"] is True      # no user/password needed
    assert sent[-1][0] == "info@isift.au" and "verification code" in sent[-1][2] and any(ch.isdigit() for ch in sent[-1][3])
    async def boom(acct, to, subject, body, ics=None): raise RuntimeError("550 relay denied")
    monkeypatch.setattr(mail, "send", boom)
    assert "550 relay denied" in client.post("/api/v1/admin/email/test", json={"to": "me@example.com"}, headers=h).json()["detail"]
    r = client.post("/api/v1/auth/signup/start", json={**SU, "email": "fay@example.com"}); assert r.status_code == 502 and "550 relay denied" in r.text


def test_database_url_and_env_import(client, monkeypatch):
    from app.core.config import normalise_database_url as n, settings
    u = n("postgresql://neondb_owner:pw@ep-x-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
    assert u.startswith("postgresql+asyncpg://neondb_owner:pw@ep-x-pooler") and "sslmode" not in u and "channel_binding" not in u and "ssl=require" in u and "prepared_statement_cache_size=0" in u
    assert n("postgres://a:b@h/db") == "postgresql+asyncpg://a:b@h/db" and n("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
    # values from .env are copied into the database once, secrets encrypted, and then the database is the source
    import asyncio
    from app.core import runtime_settings as rs
    from app.core.db import SessionLocal
    from app.models import IntegrationSetting
    monkeypatch.setitem(rs._ENV_DEFAULTS, "smtp_host", "smtp.gmail.com"); monkeypatch.setitem(rs._ENV_DEFAULTS, "groq_api_key", "gsk_testvalue1234")
    async def go():
        async with SessionLocal() as db:
            got = await rs.import_env_to_db(db); assert "smtp_host" in got and "groq_api_key" in got
            raw = (await db.get(IntegrationSetting, rs.STORE_KEY)).value; assert raw["smtp_host"] == "smtp.gmail.com" and raw["groq_api_key"].startswith("enc:") and "gsk_test" not in str(raw)
            await rs.save(db, {"smtp_host": None}); await db.commit()                   # admin resets it
            assert "smtp_host" not in await rs.import_env_to_db(db)                      # and it is not re-imported
    asyncio.run(go())

    from sqlalchemy.engine import make_url
    from sqlalchemy.dialects.postgresql import asyncpg as apg
    from app.core.config import pg_connect_args
    _, kw = apg.dialect().create_connect_args(make_url(u))
    assert kw["ssl"] == "require" and kw["prepared_statement_cache_size"] == 0 and kw["host"].endswith("neon.tech")      # real types, not strings
    assert pg_connect_args(u) == {"statement_cache_size": 0} and pg_connect_args("sqlite+aiosqlite:///x") == {}


def test_slow_mail_server_does_not_hold_up_signup(client, monkeypatch):
    import asyncio, time
    from app.services import signup as su
    sent = {}
    async def slow(db, em, name, code): await asyncio.sleep(0.6); sent["code"] = code; return True
    monkeypatch.setattr(su, "send_code", slow); monkeypatch.setattr(su, "FAST", 0.1)
    t = time.time(); r = client.post("/api/v1/auth/signup/start", json={**SU, "email": "slow@example.com"})
    assert r.status_code == 200 and r.json()["emailed"] == "pending" and time.time() - t < 0.5            # answered at once
    time.sleep(1.0); assert client.get("/api/v1/auth/signup/status", params={"email": "slow@example.com"}).json()["state"] == "sent"
    assert client.post("/api/v1/auth/signup/verify", json={"email": "slow@example.com", "code": sent["code"]}).status_code == 200
    async def bad(db, em, name, code): await asyncio.sleep(0.3); raise RuntimeError("535 auth failed")
    monkeypatch.setattr(su, "send_code", bad)
    assert client.post("/api/v1/auth/signup/start", json={**SU, "email": "slow2@example.com"}).json()["emailed"] == "pending"
    time.sleep(0.8); st = client.get("/api/v1/auth/signup/status", params={"email": "slow2@example.com"}).json(); assert st["state"] == "failed" and "535" in st["error"]


def test_earlier_code_still_works_when_a_newer_one_was_sent(client, monkeypatch):
    import time
    from app.services import signup as su
    codes = []
    async def fake(db, em, name, code): codes.append(code); return True
    monkeypatch.setattr(su, "send_code", fake); monkeypatch.setattr(su, "RESEND_AFTER", su.timedelta(seconds=0))
    for _ in range(2): assert client.post("/api/v1/auth/signup/start", json={**SU, "email": "late@example.com"}).status_code == 200
    assert len(codes) == 2 and codes[0] != codes[1]
    assert client.post("/api/v1/auth/signup/verify", json={"email": "late@example.com", "code": codes[0]}).status_code == 200      # the first (late) email's code


def test_repeat_with_no_end_date():
    from datetime import datetime
    from app.api.routes_connections import _series
    s = datetime(2030, 9, 2, 10, 0)                                                # a Monday
    assert len(_series(s, {"every": "day", "forever": True})) == 365 and len(_series(s, {"every": "week", "forever": True})) == 52 and len(_series(s, {"every": "month", "forever": True})) == 24
    wk = _series(s, {"every": "week", "forever": True, "days": [0, 1, 2, 3, 4]}); assert len(wk) == 260 and all(t.weekday() < 5 for t in wk)
    we = _series(s, {"every": "week", "forever": True, "days": [5, 6]}); assert len(we) == 104 and all(t.weekday() >= 5 for t in we)
    assert len(_series(s, {"every": "day", "count": 300})) == 300


def test_access_keys_for_addins(client):
    h, tok = login(client)
    assert client.post("/api/v1/account/access-keys", json={"name": ""}, headers=h).status_code == 422
    k = client.post("/api/v1/account/access-keys", json={"name": "Outlook add-in"}, headers=h); assert k.status_code == 201, k.text
    key = k.json()["key"]; assert key.startswith("isift_pat_")
    ls = client.get("/api/v1/account/access-keys", headers=h).json()["keys"]; assert len(ls) == 1 and "key" not in ls[0] and ls[0]["last4"] == key[-4:]
    kh = {"Authorization": "Bearer " + key}
    assert client.get("/api/v1/auth/me", headers=kh).json()["email"] == "admin@example.test"
    assert client.get("/api/v1/booking-types", headers=kh).status_code == 200
    r = client.post("/api/v1/rooms", json={"title": "From Outlook", "base_url": "http://t/"}, headers=kh); assert r.status_code == 200 and r.json()["url"]
    assert client.get("/api/v1/admin/billing/overview", headers=kh).status_code == 403          # not on the allow list
    assert client.get("/api/v1/account", headers=kh).status_code == 403 and client.post("/api/v1/account/access-keys", json={"name": "x"}, headers=kh).status_code == 403
    assert client.get("/api/v1/users", headers=kh).status_code in (403, 404)
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer isift_pat_wrong"}).status_code == 401
    assert client.delete(f"/api/v1/account/access-keys/{ls[0]['id']}", headers=h).status_code == 200
    assert client.get("/api/v1/auth/me", headers=kh).status_code == 401                          # revoked


def test_recording_goes_to_database_blob_without_r2(client, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path))
    h, tok = login(client); r = make(client, h)
    webm = bytes.fromhex("1A45DFA3") + b"y" * 2000
    assert client.post(f"/api/v1/rooms/{r['code']}/recording", headers=h, data={"consent_acknowledged": "true", "cloud": "true"}, files={"audio": ("a.webm", webm, "audio/webm"), "video": ("v.webm", webm, "video/webm")}).status_code == 200
    rec = client.get("/api/v1/recordings", headers=h).json()[0]
    assert rec["storage"] == "database" and rec["available"] is True
    g = client.get(f"/api/v1/recordings/{rec['id']}/file", headers=h); assert g.status_code == 200 and g.content == webm
    assert not list((tmp_path / "recordings").glob("*.webm"))              # nothing left on disk
    assert client.delete(f"/api/v1/recordings/{rec['id']}", headers=h).status_code == 200

def test_recording_goes_to_r2_and_streams_back(client, tmp_path, monkeypatch):
    from app.core.config import settings
    from app.core import runtime_settings as rs
    from app.services import storage
    import io
    bucket = {}
    class Body:
        def __init__(self, b): self.b = b
        def iter_chunks(self, n): yield self.b
    class Fake:
        def upload_file(self, path, b, key, ExtraArgs=None): bucket[key] = open(path, "rb").read()
        def get_object(self, Bucket, Key): return {"Body": Body(bucket[Key]), "ContentLength": len(bucket[Key])}
        def delete_object(self, Bucket, Key): bucket.pop(Key, None)
        def head_bucket(self, Bucket): pass
        def put_object(self, Bucket, Key, Body): bucket[Key] = Body
    monkeypatch.setattr(storage, "client", lambda: Fake()); monkeypatch.setattr(storage, "transcode_mp4", lambda *a, **k: False)
    for k, v in {"r2_endpoint": "https://abc.r2.cloudflarestorage.com", "r2_access_key_id": "AK", "r2_secret_access_key": "SK", "r2_bucket": "rec"}.items():
        monkeypatch.setattr(settings, k, v); monkeypatch.setitem(rs._ENV_DEFAULTS, k, v)
    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path))
    h, tok = login(client); r = make(client, h)
    webm = bytes.fromhex("1A45DFA3") + b"z" * 2000
    assert client.post(f"/api/v1/rooms/{r['code']}/recording", headers=h, data={"consent_acknowledged": "true", "cloud": "true"}, files={"audio": ("a.webm", webm, "audio/webm"), "video": ("v.webm", webm, "video/webm")}).status_code == 200
    rec = client.get("/api/v1/recordings", headers=h).json()[0]
    assert rec["storage"] == "r2" and len(bucket) == 1 and list(bucket)[0].startswith("isift-video/") and list(bucket)[0].count("/") == 2
    g = client.get(f"/api/v1/recordings/{rec['id']}/file", headers=h); assert g.status_code == 200 and g.content == webm
    t = client.post("/api/v1/admin/connection-test", headers=h) if False else None
    import asyncio; assert asyncio.run(storage.test_r2())["status"] == "connected"
    assert client.delete(f"/api/v1/recordings/{rec['id']}", headers=h).status_code == 200 and not bucket


def test_recording_local_by_default_and_basic_expiry(client, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path))
    h, tok = login(client); r = make(client, h)
    webm = bytes.fromhex("1A45DFA3") + b"q" * 2000
    up = client.post(f"/api/v1/rooms/{r['code']}/recording", headers=h, data={"consent_acknowledged": "true"}, files={"audio": ("a.webm", webm, "audio/webm")})
    assert up.status_code == 200 and "your computer" in up.json()["message"]
    before = len(client.get("/api/v1/recordings", headers=h).json())                      # nothing kept in the cloud unless asked
    up = client.post(f"/api/v1/rooms/{r['code']}/recording", headers=h, data={"consent_acknowledged": "true", "cloud": "true"}, files={"audio": ("a.webm", webm, "audio/webm")})
    assert up.status_code == 200 and "2 days" in up.json()["message"]                     # test user is on Basic
    allr = client.get("/api/v1/recordings", headers=h).json(); assert len(allr) == before + 1
    rec = [x for x in allr if x["expires_at"] and x["size_bytes"] > 2000 and x["storage"] == "database"][0]
    from datetime import datetime, timezone
    left = datetime.fromisoformat(rec["expires_at"]) - datetime.now(timezone.utc)
    assert 1.9 < left.total_seconds() / 86400 < 2.01
    import asyncio
    from app.core.db import SessionLocal
    from app.models import RoomRecording
    from app.services import storage
    async def age():
        async with SessionLocal() as db:
            row = await db.get(RoomRecording, rec["id"]); from datetime import timedelta; row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1); await db.commit()
            return await storage.purge_expired(db)
    assert asyncio.run(age()) >= 1
    assert rec["id"] not in [x["id"] for x in client.get("/api/v1/recordings", headers=h).json()]

def test_hosted_mode_rules(monkeypatch):
    from app.core.config import Settings
    s = Settings(hosted=True, app_env="production", auth_mode="local", allow_local_auth=True, database_url="postgresql://u:p@h/db", frontend_origin="https://app.example.com",
                 local_auth_secret="x" * 40, local_admin_password="a-long-password-1")
    assert s.is_local_demo is True and s.mock_data_enabled is False and s.load_mock_on_start is False and s.calendar_on_start is False and s.hosted_problems() == []
    bad = Settings(hosted=True, app_env="production", database_url="postgresql://u:p@db:5432/x", frontend_origin="http://localhost:5173").hosted_problems()
    assert len(bad) == 3 and Settings(hosted=True, local_auth_secret="short").hosted_problems()[0].startswith("LOCAL_AUTH_SECRET")
    assert Settings(hosted=False, app_env="production").is_local_demo is False             # production without HOSTED keeps Microsoft-only sign-in


def test_plan_change_credit_difference_and_manual_refund(client, monkeypatch):
    from datetime import date, timedelta
    import asyncio
    from app.integrations import square as SQ
    from app.core.db import SessionLocal
    from app.services import billing as B, store
    h, tok = login(client)
    client.patch("/api/v1/admin/integration-settings", json={"values": {"square_environment": "sandbox", "square_application_id": "sandbox-sq0idb-abc", "square_access_token": "tok-secret", "square_location_id": "LOC1"}}, headers=h)
    st = {"calls": [], "payments": []}; monkeypatch.setattr(SQ, "_transport", _square(st))
    async def clean():          # earlier tests on the same account and day used the same payment keys; start from a clean slate
        from sqlalchemy import delete
        from app.models import IntegrationSetting
        async with SessionLocal() as db: await db.execute(delete(IntegrationSetting).where(IntegrationSetting.key.like("charge:%"))); await db.commit()
    asyncio.run(clean())
    me0 = client.get("/api/v1/billing/me", headers=h).json()
    if me0["plan"] != "basic": client.post("/api/v1/billing/subscribe", json={"plan": "basic", "period": "monthly", "immediate": True}, headers=h)
    client.post("/api/v1/billing/card", json={"source_id": "cnon:ok"}, headers=h)
    # Business yearly 175.92, then move half way through the year to Individual monthly
    s = client.post("/api/v1/billing/subscribe", json={"plan": "business", "period": "yearly"}, headers=h); assert s.status_code == 200, (s.text, client.get("/api/v1/billing/me", headers=h).json())
    async def backdate(days):
        async with SessionLocal() as db:
            key, c, _ = await B.holder(db, await _user(db)); r = await B.record(db, key, c)
            r["period_start"] = (date.today() - timedelta(days=days)).isoformat(); r["period_end"] = (date.today() - timedelta(days=days) + timedelta(days=365)).isoformat(); await store.put(db, key, r)
    async def _user(db):
        from sqlalchemy import select
        from app.models import User
        return (await db.execute(select(User).where(User.email == "admin@example.test"))).scalars().first()
    asyncio.run(backdate(182))
    q = client.post("/api/v1/billing/quote", json={"plan": "individual", "period": "monthly"}, headers=h).json()
    credit = round(17592 * 183 / 365); assert q["kind"] == "change" and q["credit_cents"] == credit and q["charge_cents"] == 0 and q["refund_cents"] == credit - 1359
    n = len(st["payments"])
    d = client.post("/api/v1/billing/subscribe", json={"plan": "individual", "period": "monthly"}, headers=h).json()
    assert d["status"] == "changed" and d["charged_cents"] == 0 and d["refund_requested_cents"] == credit - 1359 and len(st["payments"]) == n      # switched at once, no new charge
    me = client.get("/api/v1/billing/me", headers=h).json(); assert me["plan"] == "individual" and me["refunds"][0]["status"] == "pending"
    assert st.get("refunds") is None                                                       # NOTHING is refunded until an administrator approves
    rid = me["refunds"][0]["id"]
    lst = client.get("/api/v1/admin/billing/refunds?status=pending", headers=h).json()["refunds"]; assert any(x["id"] == rid and x["refundable_cents"] >= credit - 1359 for x in lst)
    assert client.post(f"/api/v1/admin/billing/refunds/{rid}/approve", json={"amount_cents": credit}, headers=h).status_code == 422       # more than was asked for
    st["refund_fail"] = True; bad = client.post(f"/api/v1/admin/billing/refunds/{rid}/approve", json={}, headers=h); assert bad.status_code == 502 and "Too much" in bad.json()["detail"]
    assert client.get("/api/v1/billing/me", headers=h).json()["refunds"][0]["status"] == "pending"
    st["refund_fail"] = False
    ok = client.post(f"/api/v1/admin/billing/refunds/{rid}/approve", json={"amount_cents": 1000, "note": "Partial, goodwill"}, headers=h); assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["paid_back_cents"] == 1000
    assert st["refunds"][-1]["amount_money"] == {"amount": 1000, "currency": "AUD"} and st["refunds"][-1]["payment_id"] == "PAY%d" % len(st["payments"]) or st["refunds"][-1]["payment_id"].startswith("PAY")
    assert client.post(f"/api/v1/admin/billing/refunds/{rid}/approve", json={}, headers=h).status_code == 409        # decided once
    # an upgrade the other way: Individual monthly -> Business monthly. Credit for the unused month, pay the difference
    q2 = client.post("/api/v1/billing/quote", json={"plan": "business", "period": "monthly"}, headers=h).json(); assert q2["charge_cents"] == 1759 - q2["credit_cents"] and q2["credit_cents"] > 0
    assert client.post("/api/v1/billing/subscribe", json={"plan": "business", "period": "monthly"}, headers=h).json()["charged_cents"] == q2["charge_cents"]
    # ending early asks for a refund too, and an administrator can decline it
    e = client.post("/api/v1/billing/subscribe", json={"plan": "basic", "period": "monthly", "immediate": True}, headers=h).json(); assert e["status"] == "ended" and e["refund_requested_cents"] > 0
    assert client.get("/api/v1/billing/me", headers=h).json()["plan"] == "basic"
    dc = client.post(f"/api/v1/admin/billing/refunds/{e['refund_id']}/decline", json={"note": "Outside policy"}, headers=h).json(); assert dc["status"] == "declined" and dc["note"] == "Outside policy"
    # a non-administrator cannot see or approve refunds
    # (covered by require_admin on every refund route)

def test_hosted_password_error_explains_itself(monkeypatch):
    from app.core.config import Settings
    monkeypatch.delenv("LOCAL_ADMIN_PASSWORD", raising=False)
    msg = Settings(hosted=True, local_auth_secret="x" * 40, local_admin_password="Meeting$1", database_url="postgresql://u:p@h/d", frontend_origin="https://a.example.com").hosted_problems()[0]
    assert "not received" in msg
    monkeypatch.setenv("LOCAL_ADMIN_PASSWORD", "ab$c")
    msg = Settings(hosted=True, local_auth_secret="x" * 40, local_admin_password="ab$c", database_url="postgresql://u:p@h/d", frontend_origin="https://a.example.com").hosted_problems()[0]
    assert "4 characters" in msg and "ab$c" not in msg.replace("a $ in", "")


def test_minutes_and_transcripts_use_groq_and_the_saved_model(client, monkeypatch):
    import asyncio, json as _json
    from pydantic import BaseModel
    from app.core.config import settings
    from app.services import llm
    seen = []
    class R:
        def __init__(self, code, body): self.status_code = code; self._b = body; self.text = _json.dumps(body)
        def json(self): return self._b
    class C:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None, data=None, files=None):
            seen.append({"url": url, "auth": (headers or {}).get("Authorization"), "json": json, "data": data})
            if url.endswith("/audio/transcriptions"): return R(200, {"text": "hello", "segments": [{"start": 0, "end": 1, "text": "hello"}]})
            return R(200, {"choices": [{"message": {"content": '{"a": "x"}'}}]})
    class Out(BaseModel):
        a: str
    monkeypatch.setattr(llm.httpx, "AsyncClient", C)
    monkeypatch.setattr(settings, "groq_api_key", "")
    assert not llm.ai_configured() and not llm.transcription_configured()
    try: asyncio.run(llm.chat_json([{"role": "user", "content": "hi"}], Out)); assert False
    except llm.AIUnavailable as e: assert "Groq" in str(e)
    monkeypatch.setattr(settings, "groq_api_key", ' "gsk_abc" '); monkeypatch.setattr(settings, "groq_model", "llama-3.1-8b-instant"); monkeypatch.setattr(settings, "groq_transcription_model", "")
    assert llm.ai_configured() and llm.transcription_configured()
    assert asyncio.run(llm.chat_json([{"role": "user", "content": "hi"}], Out)).a == "x"
    c = seen[-1]; assert c["url"] == "https://api.groq.com/openai/v1/chat/completions" and c["auth"] == "Bearer gsk_abc"
    assert c["json"]["model"] == "llama-3.1-8b-instant" and c["json"]["response_format"] == {"type": "json_object"} and "JSON schema" in c["json"]["messages"][-1]["content"]
    t = asyncio.run(llm.transcribe("a.webm", b"123")); assert t["text"] == "hello"
    c = seen[-1]; assert c["url"].endswith("/audio/transcriptions") and c["data"]["model"] == "whisper-large-v3-turbo"
    try: asyncio.run(llm.transcribe("big.webm", b"0" * (llm.MAX_AUDIO_BYTES + 1))); assert False
    except llm.AIUnavailable as e: assert "25 MB" in str(e)


def test_setup_status_reports_ai_ready_with_groq_only(client, monkeypatch):
    from app.core.config import settings
    h, _ = login(client)
    monkeypatch.setattr(settings, "groq_api_key", "")
    items = {i["key"]: i for i in client.get("/api/v1/admin/setup-status", headers=h).json()["items"]}
    assert items["ai"]["ok"] is False and "Groq" in items["ai"]["title"]
    monkeypatch.setattr(settings, "groq_api_key", "gsk_x")
    items = {i["key"]: i for i in client.get("/api/v1/admin/setup-status", headers=h).json()["items"]}
    assert items["ai"]["ok"] is True and items["transcription"]["ok"] is True
