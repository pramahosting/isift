"""Webinars: setup, registration, approval, panelists, polls, reports and reminders. Emails are captured, not sent."""
from datetime import datetime, timedelta, timezone
import pytest
from test_room_access import client, login, signed_up
from app.services import webinars as wb


@pytest.fixture()
def mails(monkeypatch):
    sent = []
    async def fake(to, subject, body, ics=None): sent.append((to, subject, body, bool(ics))); return True
    monkeypatch.setattr(wb, "send_mail", fake)
    return sent


def _start(hours=48): return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _make(client, h, **extra):
    r = client.post("/api/v1/webinars", json={"title": "Launch day", "description": "What is new", "start_at": _start(), "minutes": 45, "tz": "Australia/Sydney", "base_url": "https://isift.test/", **extra}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_webinar_setup_registration_and_reports(client, mails):
    h, _ = login(client)
    client.put("/api/v1/admin/modules", json={"enabled": {"webinars": True, "meetings": True}}, headers=h)
    w = _make(client, h, panelists=[{"email": "Pat@Example.com", "name": "Pat"}, {"email": "bad"}],
              settings={"approval": "manual", "capacity": 3, "questions": [{"label": "Company", "required": True}, {"label": "Role", "type": "choice", "options": ["Dev", "PM"]}]})
    assert w["status"] == "scheduled" and w["room_code"] and w["page"].startswith("https://isift.test/#/webinar/") and len(w["panelists"]) == 1 and "?p=" in w["panelists"][0]["link"]
    assert [m for m in mails if m[0] == "pat@example.com"] and mails[0][3]                                  # panelist invited, with a calendar file
    wid = w["id"]
    info = client.get(f"/api/v1/webinar-public/{wid}").json()
    assert info["title"] == "Launch day" and info["approval"] == "manual" and len(info["questions"]) == 2 and "settings" not in info and "panelists" in info and info["full"] is False
    reg = lambda email, **kw: client.post(f"/api/v1/webinar-public/{wid}/register", json={"name": "Ann Lee", "email": email, "answers": {"q1": "Acme", "q2": "Dev"}, **kw})
    assert reg("not-an-email").status_code == 422
    assert reg("ann@example.com", answers={"q2": "Dev"}).status_code == 422                                  # required question missing
    assert reg("ann@example.com", answers={"q1": "Acme", "q2": "CEO"}).status_code == 422                    # not one of the choices
    r = reg("ann@example.com"); assert r.status_code == 200 and r.json()["status"] == "pending" and r.json()["token"] == ""
    assert mails[-1][0] == "ann@example.com" and "reviews each registration" in mails[-1][2]
    n = len(mails); r = reg("ann@example.com"); assert r.json()["message"].startswith("You are already registered") and len(mails) == n + 1       # same address again: no duplicate, link re-sent
    rows = client.get(f"/api/v1/webinars/{wid}/registrants", headers=h).json()["registrants"]; assert len(rows) == 1 and rows[0]["status"] == "pending"
    tok = rows[0]["link"].split("k=")[1]
    assert client.get(f"/api/v1/webinar-public/{wid}/me?k={tok}").json()["room_code"] == ""                   # not approved: no room yet
    d = client.patch(f"/api/v1/webinars/{wid}/registrants/{rows[0]['id']}", json={"status": "approved"}, headers=h).json(); assert d["registrant"]["status"] == "approved"
    assert mails[-1][0] == "ann@example.com" and "personal link" in mails[-1][2] and mails[-1][3]
    me = client.get(f"/api/v1/webinar-public/{wid}/me?k={tok}").json(); assert me["room_code"] == w["room_code"] and me["name"] == "Ann Lee"
    assert client.get(f"/api/v1/webinar-public/{wid}/me?k=wrong").status_code == 404
    assert client.get(f"/api/v1/webinar-public/{wid}/me?p={w['panelists'][0]['link'].split('p=')[1]}").json()["role"] == "panelist"
    assert "BEGIN:VCALENDAR" in client.get(f"/api/v1/webinar-public/{wid}/calendar.ics?k={tok}").text
    # the host adds people, capacity is respected (3 in total)
    r = client.post(f"/api/v1/webinars/{wid}/registrants", json={"people": [{"name": "B", "email": "b@example.com"}, {"email": "c@example.com"}, {"email": "d@example.com"}, {"email": "bad"}]}, headers=h).json()
    assert r["added"] == 2 and len(r["skipped"]) == 2
    assert client.get(f"/api/v1/webinar-public/{wid}").json()["full"] is True and reg("late@example.com").status_code == 409
    # polls
    p = client.post(f"/api/v1/webinars/{wid}/polls", json={"question": "Which feature next?", "options": ["Polls", "Q&A", ""], "multi": False}, headers=h).json()["poll"]
    assert p["options"] == ["Polls", "Q&A"] and p["status"] == "draft"
    assert client.post(f"/api/v1/webinars/{wid}/polls", json={"question": "x", "options": ["a"]}, headers=h).status_code == 422
    assert client.patch(f"/api/v1/webinars/{wid}/polls/{p['id']}", json={"question": "Which feature first?", "options": ["Polls", "Q&A", "Chat"]}, headers=h).json()["poll"]["options"][2] == "Chat"
    # reports and exports
    rep = client.get(f"/api/v1/webinars/{wid}", headers=h).json()["report"]; assert rep["registered"] == 3 and rep["attended"] == 0
    csvr = client.get(f"/api/v1/webinars/{wid}/export/registrants", headers=h).json(); assert csvr["filename"].endswith("registrants.csv") and "ann@example.com" in csvr["content"] and "Company" in csvr["content"]
    assert client.get(f"/api/v1/webinars/{wid}/export/nothing", headers=h).status_code == 404
    # changing the time tells registrants; cancelling tells them again
    n = len(mails); assert client.patch(f"/api/v1/webinars/{wid}", json={"start_at": _start(72)}, headers=h).status_code == 200 and len(mails) == n + 3 and "New time" in mails[-1][1]
    n = len(mails); assert client.delete(f"/api/v1/webinars/{wid}", headers=h).status_code == 200 and len(mails) == n + 3
    assert client.get(f"/api/v1/webinar-public/{wid}").json()["status"] == "cancelled" and reg("zed@example.com").status_code == 409


def test_webinar_attendance_followup_and_reminders(client, mails, monkeypatch):
    import asyncio
    from app.core.db import SessionLocal
    h, _ = login(client)
    client.put("/api/v1/admin/modules", json={"enabled": {"webinars": True, "meetings": True}}, headers=h)
    soon = _make(client, h, settings={"reminders": {"day": True, "hour": True}, "recording_url": "https://isift.test/rec/1"})
    wid = soon["id"]
    client.post(f"/api/v1/webinars/{wid}/registrants", json={"people": [{"name": "Went", "email": "went@example.com"}, {"name": "Missed", "email": "missed@example.com"}]}, headers=h)
    regs = {r["email"]: r for r in client.get(f"/api/v1/webinars/{wid}/registrants", headers=h).json()["registrants"]}
    async def go():
        async with SessionLocal() as db:
            from app.models import Webinar, WebinarRegistrant
            from sqlalchemy import select
            w = await db.get(Webinar, wid)
            w.start_at = datetime.now(timezone.utc) + timedelta(minutes=50); await db.commit()
            assert await wb.run_reminders(db) == 2                       # one hour to go: both registrants (no panelists)
            assert await wb.run_reminders(db) == 0                       # and only once
            r = await db.get(WebinarRegistrant, regs["went@example.com"]["id"]); await wb.attend_join(db, r.id); await wb.attend_leave(db, r.id, 1800)
            w.status = "ended"; w.ended_at = datetime.now(timezone.utc); await db.commit()
            assert await wb.send_followups(db, w, "attended") == 1 and await wb.send_followups(db, w, "attended") == 0
            assert await wb.send_followups(db, w, "missed", message="Catch up on the recording.") == 1
    asyncio.run(go())
    assert any("Starts in about an hour" in m[1] for m in mails) and any(m[0] == "went@example.com" and "Thank you for joining" in m[1] and "rec/1" in m[2] for m in mails)
    assert any(m[0] == "missed@example.com" and "Catch up on the recording." in m[2] and "rec/1" in m[2] for m in mails)
    rep = client.get(f"/api/v1/webinars/{wid}", headers=h).json()["report"]; assert rep["attended"] == 1 and rep["avg_minutes"] == 30.0
    assert client.post(f"/api/v1/webinars/{wid}/followup", json={"kind": "missed"}, headers=h).json()["sent"] == 0          # already sent


def test_webinar_needs_plan_and_module(client, mails, monkeypatch):
    h, _ = login(client)
    su = signed_up(client, monkeypatch, "basic@example.com", "Basic", "User"); uh = {"Authorization": "Bearer " + su["access_token"]}
    client.get("/api/v1/account", headers=uh)
    r = client.post("/api/v1/webinars", json={"title": "Nope", "start_at": _start()}, headers=uh); assert r.status_code == 403 and "plan" in r.json()["detail"]
    uid = next(u["id"] for u in client.get("/api/v1/admin/users", headers=h).json() if u["email"] == "basic@example.com")
    assert client.patch(f"/api/v1/admin/users/{uid}", json={"limits": {"webinars": True}}, headers=h).status_code == 200
    client.put("/api/v1/admin/modules", json={"enabled": {"webinars": True, "meetings": True}}, headers=h)
    wid = client.post("/api/v1/webinars", json={"title": "Allowed now", "start_at": _start()}, headers=uh).json()["id"]
    client.put("/api/v1/admin/modules", json={"enabled": {"webinars": False}}, headers=h)
    assert client.get("/api/v1/webinars", headers=uh).status_code == 403 and client.get(f"/api/v1/webinar-public/{wid}").status_code == 403
    client.put("/api/v1/admin/modules", json={"enabled": {"webinars": True}}, headers=h)
    assert wid not in [x["id"] for x in client.get("/api/v1/webinars", headers=h).json()["webinars"]]           # another host sees only their own
    assert client.get(f"/api/v1/webinars/{wid}", headers=h).status_code == 404


def _until(w, typ, limit=40):
    for _ in range(limit):
        m = w.receive_json()
        if m["type"] == typ: return m
    raise AssertionError(f"never saw {typ}")


def test_webinar_live_room(client, mails):
    from test_room_access import join
    h, tok = login(client)
    client.put("/api/v1/admin/modules", json={"enabled": {"webinars": True, "meetings": True}}, headers=h)
    w = _make(client, h, panelists=[{"email": "pat@example.com", "name": "Pat"}], settings={"chat": "host", "practice": True})
    wid, code = w["id"], w["room_code"]
    client.post(f"/api/v1/webinars/{wid}/registrants", json={"people": [{"name": "Ann", "email": "ann@example.com"}, {"name": "Bob", "email": "bob@example.com"}]}, headers=h)
    regs = {r["email"]: r["link"].split("k=")[1] for r in client.get(f"/api/v1/webinars/{wid}/registrants", headers=h).json()["registrants"]}
    ptok = w["panelists"][0]["link"].split("p=")[1]
    pl = client.post(f"/api/v1/webinars/{wid}/polls", json={"question": "Ready?", "options": ["Yes", "No"]}, headers=h).json()["poll"]
    info = client.get(f"/api/v1/rooms/{code}?reg={regs['ann@example.com']}").json(); assert info["webinar"]["role"] == "attendee" and info["webinar"]["name"] == "Ann"
    assert client.get(f"/api/v1/rooms/{code}").json()["webinar"]["error"]                                       # no registration: told to register
    # people who are not registered cannot come in
    ws0, a0 = join(client, code, name="Gatecrasher"); assert a0.receive_json()["code"] == "register"; ws0.__exit__(None, None, None)
    ws0, a0 = join(client, code, name="Gatecrasher", reg="wrong"); assert a0.receive_json()["type"] == "error"; ws0.__exit__(None, None, None)
    # host in the practice session; attendee waits in the holding area
    wsH, H = join(client, code, token=tok, name="Host"); assert _until(H, "welcome")["host"] is True and _until(H, "wb-info")["role"] == "host"
    wsA, A = join(client, code, reg=regs["ann@example.com"], name="ignored"); assert A.receive_json()["type"] == "wb-holding"
    wsP, P = join(client, code, panel=ptok, name="x"); wp = _until(P, "welcome"); assert wp["host"] is True and wp["cohost"] is True and _until(P, "wb-info")["role"] == "panelist"
    # go live: the attendee is let in, shown only to the host side
    H.send_json({"type": "wb_live", "on": True})
    wa = _until(A, "welcome"); assert wa["host"] is False and _until(A, "wb-info")["role"] == "attendee" and all(not p.get("attendee") for p in wa["peers"])
    j = _until(H, "peer-joined"); assert j["attendee"] is True and j["name"] == "Ann"                            # named from the registration, not what she typed
    wsB, B = join(client, code, reg=regs["bob@example.com"]); _until(B, "welcome"); _until(H, "peer-joined")
    # attendees cannot switch on a microphone or camera
    A.send_json({"type": "state", "mic": True, "cam": True}); assert _until(H, "state")["mic"] is False
    # chat from an attendee goes to the host only
    A.send_json({"type": "chat", "text": "Can you hear me?"}); c = _until(H, "chat"); assert c["text"] == "Can you hear me?" and c["name"] == "Ann" and len(c["to"]) == 1
    H.send_json({"type": "chat", "text": "SENTINEL"})
    assert _until(B, "chat")["text"] == "SENTINEL"                                                              # Bob never saw Ann's message
    assert _until(P, "chat")["text"] == "SENTINEL"                                                              # nor did the panelist (chat mode: host only)
    # the host answers privately
    hid = next(i for i, p in {c["from"]: 1}.items()); H.send_json({"type": "chat", "text": "Loud and clear", "to": [hid]}); assert _until(A, "chat")["text"] == "Loud and clear"
    # Q&A
    B.send_json({"type": "wb_ask", "text": "What is the price?", "anonymous": True})
    d = _until(H, "wb-data"); q = d["questions"][0]; assert q["text"] == "What is the price?" and "anonymous" in q["name"] and d["counts"]["watching"] == 2
    seen = _until(A, "wb-data")["questions"]; assert seen[0]["name"] == "Anonymous attendee"                       # anonymous to other attendees
    A.send_json({"type": "wb_up", "id": q["id"]}); assert _until(H, "wb-data")["questions"][0]["up"] == 1
    H.send_json({"type": "wb_answer", "id": q["id"], "text": "It starts at $9."}); assert _until(B, "wb-data")["questions"][0]["answer"] == "It starts at $9."
    # poll
    H.send_json({"type": "wb_poll", "id": pl["id"], "action": "open"}); pa = _until(A, "wb-data")["polls"]; assert pa[0]["status"] == "open" and "counts" not in pa[0]
    A.send_json({"type": "wb_vote", "id": pl["id"], "choices": [0]}); B.send_json({"type": "wb_vote", "id": pl["id"], "choices": [1]})
    hp = None
    for _ in range(8):
        hp = _until(H, "wb-data")["polls"][0]
        if hp.get("total") == 2: break
    assert hp["counts"] == [1, 1]
    H.send_json({"type": "wb_poll", "id": pl["id"], "action": "close", "share": True})
    assert _until(A, "wb-data")["polls"][0]["status"] == "closed"
    # let Ann speak: she joins again with the stage part; then the host can mute her
    H.send_json({"type": "wb_promote", "id": j["id"]}); assert _until(A, "wb-promoted")["on"] is True
    wsA.__exit__(None, None, None)
    wsA, A = join(client, code, reg=regs["ann@example.com"]); assert _until(A, "welcome")["host"] is False and _until(A, "wb-info")["role"] == "speaker"
    A.send_json({"type": "state", "mic": True, "cam": True}); st = _until(H, "state"); assert st["mic"] is True                 # a speaker may unmute
    H.send_json({"type": "wb_mute_all", "cam": True}); f = _until(A, "force"); assert f["mic"] is False and f["cam"] is False
    # the host can also end it, and attendance and the report are kept
    H.send_json({"type": "end"})
    for s in (wsA, wsB, wsP, wsH):
        try: s.__exit__(None, None, None)
        except Exception: pass
    rep = client.get(f"/api/v1/webinars/{wid}", headers=h).json(); assert rep["status"] == "ended" and rep["report"]["attended"] == 2 and rep["report"]["questions"] == 1 and rep["report"]["votes"] == 2
    ex = client.get(f"/api/v1/webinars/{wid}/export/questions", headers=h).json()["content"]; assert "What is the price?" in ex and "It starts at $9." in ex
    assert "Yes" in client.get(f"/api/v1/webinars/{wid}/export/polls", headers=h).json()["content"]


def _until(w, kind, pred=None, n=60):
    for _ in range(n):
        m = w.receive_json()
        if m.get("type") == kind and (pred is None or pred(m)): return m
    raise AssertionError(f"never saw {kind}")


def test_webinar_live_room(client, mails):
    from test_room_access import join
    h, tok = login(client)
    client.put("/api/v1/admin/modules", json={"enabled": {"webinars": True, "meetings": True}}, headers=h)
    w = _make(client, h, settings={"chat": "host", "qa_view": "all"}); wid, code = w["id"], w["room_code"]
    client.post(f"/api/v1/webinars/{wid}/registrants", json={"people": [{"name": "Ann", "email": "ann@example.com"}, {"name": "Bo", "email": "bo@example.com"}]}, headers=h)
    toks = {r["email"]: r["link"].split("k=")[1] for r in client.get(f"/api/v1/webinars/{wid}/registrants", headers=h).json()["registrants"]}
    info = client.get(f"/api/v1/rooms/{code}", headers={"Authorization": "Bearer " + tok}).json(); assert info["webinar"]["id"] == wid
    poll = client.post(f"/api/v1/webinars/{wid}/polls", json={"question": "Favourite?", "options": ["Red", "Blue"]}, headers=h).json()["poll"]
    # a stranger without a registration cannot come in
    ws, s = join(client, code, name="Stranger"); m = s.receive_json(); assert m["type"] == "error" and m["code"] == "register"; ws.__exit__(None, None, None)
    # the host opens the room (practice session): attendees wait in the holding area
    hws, hs = join(client, code, name="Host", token=tok); hw = _until(hs, "welcome"); assert hw["host"] is True
    assert _until(hs, "wb-info")["role"] == "host" and _until(hs, "wb-data")["polls"][0]["id"] == poll["id"]
    aws, a = join(client, code, name="x", reg=toks["ann@example.com"]); assert _until(a, "wb-holding")
    bws, b = join(client, code, name="x", reg=toks["bo@example.com"]); assert _until(b, "wb-holding")
    assert _until(hs, "wb-data", lambda m: m.get("counts", {}).get("holding") == 2)
    hs.send_json({"type": "wb_live", "on": True}); assert _until(hs, "wb-live")["on"] is True
    aw = _until(a, "welcome"); aid = aw["id"]; assert aw["host"] is False and all(not p.get("attendee") for p in aw["peers"]) and len(aw["peers"]) == 1     # an attendee sees only the host side
    ai = _until(a, "wb-info"); assert ai["role"] == "attendee" and ai["live"] is True and ai["chat"] == "host"
    _until(b, "welcome")
    # attendees cannot speak: their microphone and camera are switched off by the server
    a.send_json({"type": "state", "mic": True, "cam": True, "screen": True}); st = _until(hs, "state", lambda m: m["id"] == aid); assert st["mic"] is False and st["cam"] is False and st["screen"] is False
    # chat goes to the host only
    a.send_json({"type": "chat", "text": "Can you hear me?"}); c = _until(hs, "chat"); assert c["text"] == "Can you hear me?" and c["name"] == "Ann" and len(c["to"]) == 1
    hs.send_json({"type": "chat", "text": "Welcome everyone"}); assert _until(b, "chat")["text"] == "Welcome everyone"           # the first chat Bo sees is the host's public one
    hs.send_json({"type": "chat", "text": "Private reply", "to": [aid]}); assert _until(a, "chat", lambda m: m["text"] == "Private reply")
    # raise hand reaches the host side only
    a.send_json({"type": "hand", "up": True}); assert _until(hs, "hand")["up"] is True
    # Q&A: everyone can ask, the host answers
    a.send_json({"type": "wb_ask", "text": "Is there a recording?", "anonymous": True}); d = _until(hs, "wb-data", lambda m: m["questions"]); q = d["questions"][0]
    assert q["text"] == "Is there a recording?" and "anonymous" in q["name"]                                                   # the host sees who asked
    d = _until(b, "wb-data", lambda m: m["questions"]); assert d["questions"][0]["name"] == "Anonymous attendee"             # other attendees do not
    b.send_json({"type": "wb_up", "id": q["id"]}); assert _until(hs, "wb-data", lambda m: m["questions"] and m["questions"][0]["up"] == 1)
    a.send_json({"type": "wb_dismiss", "id": q["id"]}); a.send_json({"type": "wb_answer", "id": q["id"], "text": "no"})      # an attendee cannot answer or dismiss
    hs.send_json({"type": "wb_answer", "id": q["id"], "text": "Yes, tomorrow."}); d = _until(b, "wb-data", lambda m: m["questions"] and m["questions"][0]["status"] == "answered"); assert d["questions"][0]["answer"] == "Yes, tomorrow."
    # polls: the host launches, attendees vote, only the host sees live results until shared
    hs.send_json({"type": "wb_poll", "action": "open", "id": poll["id"]})
    pa = _until(a, "wb-data", lambda m: m["polls"] and m["polls"][0]["status"] == "open"); assert "counts" not in pa["polls"][0]
    a.send_json({"type": "wb_vote", "id": poll["id"], "choices": [1]}); assert _until(hs, "wb-data", lambda m: m["polls"] and m["polls"][0].get("counts") == [0, 1])
    a.send_json({"type": "wb_vote", "id": poll["id"], "choices": [0, 1]})                                                       # single choice only: refused
    hs.send_json({"type": "wb_poll", "action": "close", "id": poll["id"], "share": True}); pb = _until(b, "wb-data", lambda m: m["polls"] and m["polls"][0]["status"] == "closed"); assert pb["polls"][0]["counts"] == [0, 1]
    # the host lets Ann speak
    hs.send_json({"type": "wb_promote", "ids": [aid]}); pr = _until(a, "wb-promoted"); assert pr["on"] is True
    a.send_json({"type": "wb_promote", "ids": [aid]})                                                                           # an attendee cannot promote themselves
    # leaving is recorded
    aws.__exit__(None, None, None); bws.__exit__(None, None, None); hws.__exit__(None, None, None)
    rows = {r["email"]: r for r in client.get(f"/api/v1/webinars/{wid}/registrants", headers=h).json()["registrants"]}; assert rows["ann@example.com"]["attended"] is True and rows["bo@example.com"]["attended"] is True
    qs = client.get(f"/api/v1/webinars/{wid}/questions", headers=h).json()["questions"]; assert qs[0]["status"] == "answered"
    assert "Is there a recording?" in client.get(f"/api/v1/webinars/{wid}/export/questions", headers=h).json()["content"]
