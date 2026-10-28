import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
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
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_token_roundtrip_and_tamper():
    from app.services import rsvp
    t = rsvp.make_token("m-1", "A@X.com"); assert rsvp.read_token(t) == ("m-1", "a@x.com")
    assert rsvp.read_token(t[:-2] + "zz") is None and rsvp.read_token("junk") is None


def test_footer_has_reply_and_calendar_links():
    from app.services import rsvp
    class M: id = "m-1"; title = "Plan & review"; start_at = datetime(2030, 1, 1, 10, tzinfo=timezone.utc); end_at = datetime(2030, 1, 1, 11, tzinfo=timezone.utc)
    f = rsvp.footer("https://isift.au", M, "a@x.com", "https://isift.au/#/room/abc")
    assert "#/rsvp/" in f and len(f) < 300 and "calendar.google.com" not in f          # one short link in the plain text
    h = rsvp.html_body("Hello\nJoin: https://isift.au/#/room/abc", "https://isift.au", M, "a@x.com", "https://isift.au/#/room/abc")
    assert "?r=proposed" in h and "?r=calendar" in h          # no accept button that opens a web page
    h2 = rsvp.html_body("Join: https://isift.au/#/room/abc", "https://isift.au", M, "a@x.com", "https://isift.au/#/room/abc", "host@yahoo.com")
    assert h2.index("#/room/abc") < h2.index(">Yes<") < h2.index(">No<") < h2.index(">Maybe<") and "mailto:host%40yahoo.com" in h2 and "isift-reply%3Am-1%3Aaccepted%3A" in h2 and "?r=accepted" not in h2


def test_reply_reaches_host_and_proposal_moves_meeting(client):
    from app.services import rsvp
    h = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Board", "start_at": "2030-01-01T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/"}, headers=h)
    assert r.status_code == 200, r.text; mid = r.json()["id"]
    tok = rsvp.make_token(mid, "guest@example.com")
    info = client.get(f"/api/v1/rsvp/{tok}"); assert info.status_code == 200 and info.json()["title"] == "Board" and "google" in info.json()["calendar"]
    assert client.get("/api/v1/rsvp/bad.token").status_code == 404
    assert client.post(f"/api/v1/rsvp/{tok}", json={"status": "nope"}).status_code == 422
    assert client.post(f"/api/v1/rsvp/{tok}", json={"status": "accepted"}).status_code == 200
    got = client.get(f"/api/v1/meetings/{mid}/responses", headers=h).json()
    assert got["counts"]["accepted"] == 1 and got["responses"][0]["email"] == "guest@example.com"
    assert client.get(f"/api/v1/meetings/{mid}/responses").status_code in (401, 403)          # hosts only
    soon = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    assert client.post(f"/api/v1/rsvp/{tok}", json={"status": "proposed", "proposed_start": "2001-01-01T00:00:00Z"}).status_code == 422
    assert client.post(f"/api/v1/rsvp/{tok}", json={"status": "proposed", "proposed_start": soon.isoformat(), "note": "Clash"}).status_code == 200
    assert client.get(f"/api/v1/meetings/{mid}/responses", headers=h).json()["counts"]["proposed"] == 1
    a = client.post(f"/api/v1/meetings/{mid}/accept-proposal", json={"email": "guest@example.com"}, headers=h); assert a.status_code == 200, a.text
    assert a.json()["start_at"].startswith(soon.strftime("%Y-%m-%d"))
    assert client.get(f"/api/v1/meetings/{mid}/responses", headers=h).json()["counts"]["proposed"] == 0      # replies start again after a move


def test_host_code_makes_a_signed_out_browser_the_host(client):
    h = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Board", "start_at": "2030-01-01T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/"}, headers=h)
    code = r.json()["join_url"].split("#/room/")[1]
    hc = client.get(f"/api/v1/rooms/{code}/host", headers=h).json()["host_code"]; assert len(hc) == 9 and hc[4] == "-"
    assert client.get(f"/api/v1/rooms/{code}/host", headers=h).json()["host_code"] == hc          # stays the same
    def go(**kw):
        with client.websocket_connect(f"/api/v1/ws/rooms/{code}") as w:
            w.send_json({"type": "join", "name": "Pramod", **kw}); return w.receive_json()
    assert go().get("host") is not True                                                # signed out, no code: a guest (waits to be let in)
    assert go(host_code=hc)["host"] is True                                             # with the host code: the host
    assert go(host_code=hc.lower().replace("-", " "))["host"] is True                   # typed loosely
    bad = go(host_code="AAAA-AAAA"); assert bad["type"] == "error" and bad["code"] == "hostcode"


def test_invite_pass_skips_passcode_and_waiting_room(client):
    from app.api.routes_rooms import invite_pass, invite_pass_email
    h = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Board", "start_at": "2030-01-01T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/", "access": "passcode", "waiting_room": True}, headers=h)
    code = r.json()["join_url"].split("#/room/")[1]
    def go(**kw):
        with client.websocket_connect(f"/api/v1/ws/rooms/{code}") as w:
            w.send_json({"type": "join", "name": "Sam", **kw}); return w.receive_json()
    assert go()["type"] == "error"                                                    # passcode needed
    assert go(invite="junk")["type"] == "error"
    assert go(invite=invite_pass(code, "sam@x.com"))["type"] == "welcome"             # personal link: straight in, no waiting room
    assert invite_pass_email("OTHER", invite_pass(code, "sam@x.com")) is None         # only for this meeting
    assert invite_pass_email(code, invite_pass(code, "sam@x.com", hours=-1)) is None  # and only for a while


def test_invitations_are_sent_from_any_connected_mailbox_with_fallback(client, monkeypatch):
    from app.integrations import mail as mailer
    from app.services import rsvp
    sent = []
    async def fake_senders(db, user): return [{"address": "host@gmail.com", "id": "a1"}, {"address": "noreply@isift.au", "id": "p", "platform": True}]
    async def fake_send(acct, to, subject, body, ics=None, *a, **k):
        if acct["address"] == "host@gmail.com" and "bad@example.com" in to: raise mailer.MailError("The mail server refused the sign-in.")
        sent.append((acct["address"], to, body, ics))
    monkeypatch.setattr(rsvp, "senders", fake_senders); monkeypatch.setattr(mailer, "send", fake_send)
    h = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Board", "start_at": "2030-01-01T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/", "invite": "pk@example.com"}, headers=h)
    assert r.status_code == 200 and "Invitations sent" in r.json()["message"], r.text
    frm, to, body, ics = sent[-1]; assert frm == "host@gmail.com" and to == ["pk@example.com"]
    assert b"METHOD:REQUEST" in ics
    r2 = client.post("/api/v1/meetings", json={"title": "Two", "start_at": "2030-01-02T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/", "invite": "bad@example.com"}, headers=h)
    assert "Invitations sent" in r2.json()["message"] and sent[-1][0] == "noreply@isift.au"       # the first mailbox failed, so the app's own sender was used


def test_resend_invitations_reports_which_mailbox_or_why_not(client, monkeypatch):
    from app.integrations import mail as mailer
    from app.services import rsvp
    sent = []
    async def fake_senders(db, user): return [{"address": "host@gmail.com", "id": "a1"}]
    async def fake_send(acct, to, subject, body, ics=None, *a, **k):
        if "bad@example.com" in to: raise mailer.MailError("The mail server refused the sign-in.")
        sent.append((acct["address"], to))
    monkeypatch.setattr(rsvp, "senders", fake_senders); monkeypatch.setattr(mailer, "send", fake_send)
    h = login(client)
    r = client.post("/api/v1/meetings", json={"title": "Again", "start_at": "2030-01-01T10:00:00Z", "duration_minutes": 30, "provider": "room", "base_url": "http://t/", "invite": "pk@example.com, bad@example.com"}, headers=h)
    mid = r.json()["id"] if "id" in r.json() else r.json()["meeting"]["id"]
    sent.clear()
    r2 = client.post(f"/api/v1/meetings/{mid}/resend-invites", json={}, headers=h)
    assert r2.status_code == 200, r2.text
    j = r2.json()
    assert [(x["to"], x["from"]) for x in j["sent"]] == [("pk@example.com", "host@gmail.com")]
    assert j["failed"][0]["to"] == "bad@example.com" and "refused" in j["message"] and "Spam" in j["message"]
    r3 = client.post(f"/api/v1/meetings/{mid}/resend-invites", json={"email": "nobody@x.com"}, headers=h)
    assert r3.status_code == 422


def test_senders_use_login_mailbox_else_app_sender_via_isift(client, monkeypatch):
    import asyncio
    from app.api import routes_booking
    from app.services import rsvp
    async def fake(db, owner): return [{"address": "app@gmail.com", "platform": True}, {"address": "other@gmail.com"}, {"address": "Host@Yahoo.com"}]
    monkeypatch.setattr(routes_booking, "_senders", fake)
    class U: email = "host@yahoo.com"; display_name = "Pramod Singh"
    assert [a["address"] for a in asyncio.run(rsvp.senders(None, U()))] == ["Host@Yahoo.com"]          # the login address alone
    class V: email = "nobody@corp.com"; display_name = "No Body"
    out = asyncio.run(rsvp.senders(None, V()))                                                             # not connected: the Zoom way, never another mailbox
    assert [a["address"] for a in out] == ["app@gmail.com"] and out[0]["from"] == "No Body via iSift <app@gmail.com>" and out[0]["reply_to"] == "nobody@corp.com"
    from types import SimpleNamespace as NS
    h = rsvp.html_body("Hi", "https://x.au", NS(id="m1", title="T"), "g@x.com", None, "")                 # app sender: Yes / No / Maybe record in iSift
    assert "?r=accepted" in h and "mailto:" not in h
