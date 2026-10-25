"""The live side of a webinar, inside the meeting room's WebSocket (see routes_rooms.py).

People in a webinar room are one of: host (rank 2), panelist (rank 1, a co-host), speaker (an attendee the host let speak),
or attendee (watch only). Attendees are not shown to each other. Their reactions, raised hands and chat go to the host side only.
Everything that is stored (questions, polls, attendance) goes through app.services.webinars.
"""
import asyncio, logging, time
from datetime import datetime, timezone
from app.core.db import SessionLocal
from app.models import Webinar, WebinarPoll
from app.services import webinars as wbs

log = logging.getLogger("isift")
QUIET = {"peer-joined", "peer-left", "state", "hand", "react", "renamed"}       # what an attendee does is told to the host side only

def _rank(p: dict) -> int: return 0 if not p.get("host") else (1 if p.get("cohost") else 2)
def staff(p: dict) -> bool: return _rank(p) >= 1
def is_attendee(p: dict) -> bool: return bool(p.get("attendee"))

async def _send(ws, msg: dict):
    import json
    try: await ws.send_text(json.dumps(msg))
    except Exception: pass

def settings_of(state: dict) -> dict: return (state.get("web") or {}).get("settings") or {}

def recipients(state: dict, msg: dict) -> list[dict]:
    """Who hears an event that an attendee caused: only the host and co-hosts. Everything else goes to everyone as before."""
    who = msg.get("id")
    if who in state.get("attendee_ids", ()) and msg.get("type") in QUIET: return [p for p in state["peers"].values() if staff(p)]
    return list(state["peers"].values())

def info_for(state: dict, p: dict) -> dict:
    s = settings_of(state)
    return {"type": "wb-info", "id": state["web"]["id"], "title": state["web"].get("title", ""), "role": "host" if _rank(p) == 2 else "panelist" if _rank(p) == 1 else "attendee" if is_attendee(p) else "speaker",
            "live": bool(state.get("web_live")), "qa": bool(s.get("qa", True)), "qa_anonymous": bool(s.get("qa_anonymous", True)), "qa_view": s.get("qa_view", "all"), "chat": s.get("chat", "host"), "hand": bool(s.get("hand", True))}

async def go_live(state: dict, code: str, admit):
    """The host starts the webinar: attendees waiting in the holding area are let in. admit(pid, h) lets one of them in."""
    state["web_live"] = True
    for p in list(state["peers"].values()): await _send(p["ws"], {"type": "wb-live", "on": True})
    for pid, h in list(state.get("holding", {}).items()):
        state["holding"].pop(pid, None)
        await admit(pid, h)
    mark_dirty(state, code)

# ---- one coalesced update to everybody, so hundreds of upvotes or votes do not become hundreds of messages each
def mark_dirty(state: dict, code: str):
    t = state.get("wb_task")
    if t and not t.done(): state["wb_dirty"] = True; return
    state["wb_dirty"] = True; state["wb_task"] = asyncio.create_task(_flush(state, code))

async def _flush(state: dict, code: str):
    try:
        while state.get("wb_dirty"):
            state["wb_dirty"] = False; await asyncio.sleep(0.6)
            async with SessionLocal() as db: qs, ps = await wbs.snapshot(db, state["web"]["id"])
            qa_view = settings_of(state).get("qa_view", "all")
            watching = sum(1 for p in state["peers"].values() if is_attendee(p) or p.get("promoted")); holding = len(state.get("holding", {}))
            for p in list(state["peers"].values()):
                v = wbs.views_for(qs, ps, p.get("key", ""), staff(p), qa_view)
                if staff(p): v["counts"] = {"watching": watching, "holding": holding}
                await _send(p["ws"], {"type": "wb-data", **v})
    except Exception: log.exception("webinar update failed")

async def _webinar(state: dict) -> Webinar | None:
    async with SessionLocal() as db: return await db.get(Webinar, state["web"]["id"])

# ---- chat: an attendee's message goes to the host only (or the host side, or everyone), as the host chose
async def chat(state: dict, pid: str, msg: dict, ws) -> bool:
    """Returns True when this message was handled here. Messages from the host side, and everything when chat is open to everyone, take the normal route."""
    me = state["peers"][pid]; mode = settings_of(state).get("chat", "host")
    if staff(me) or mode == "everyone": return False
    text = str(msg.get("text") or "")[:2000]
    if not text.strip(): return True
    if mode == "off": await _send(ws, {"type": "chat-error", "message": "Chat is turned off for this webinar. Use Q&A to ask a question."}); return True
    to = [i for i, p in state["peers"].items() if (_rank(p) == 2 if mode == "host" else staff(p))]
    out = {"type": "chat", "from": pid, "name": me["name"], "text": text, "at": datetime.now(timezone.utc).isoformat(), "to": to, "to_names": [state["peers"][i]["name"] for i in to]}
    for i in {pid, *to}: await _send(state["peers"][i]["ws"], out)
    return True

# ---- Q&A, polls, raise hand, speaking, muting: everything else
async def handle(state: dict, pid: str, msg: dict, code: str, admit) -> bool:
    t = str(msg.get("type") or "")
    if not t.startswith("wb_"): return False
    me = state["peers"][pid]; ws = me["ws"]; st = staff(me); host = _rank(me) == 2; key = me.get("key") or pid
    w = await _webinar(state)
    if not w: return True
    s = w.settings or {}; state["web"]["settings"] = s
    async def say(m): await _send(ws, m)
    if t == "wb_ask":
        async with SessionLocal() as db: q = await wbs.ask(db, w, key, me["name"], me.get("email", ""), msg.get("text"), bool(msg.get("anonymous")))
        await say({"type": "wb-note", "message": "Your question was sent." if q else "Questions are not turned on for this webinar." if not s.get("qa", True) else "Type your question first."})
        if q: mark_dirty(state, code)
    elif t == "wb_up":
        async with SessionLocal() as db: ok = await wbs.upvote(db, w.id, str(msg.get("id") or ""), key)
        if ok: mark_dirty(state, code)
    elif t in ("wb_answer", "wb_dismiss", "wb_reopen") and st:
        async with SessionLocal() as db: ok = await wbs.answer(db, w.id, str(msg.get("id") or ""), me["name"], str(msg.get("text") or ""), bool(msg.get("live")), t == "wb_dismiss", t == "wb_reopen")
        if ok: mark_dirty(state, code)
    elif t == "wb_poll" and st:
        action = str(msg.get("action") or "")
        async with SessionLocal() as db:
            p = await db.get(WebinarPoll, str(msg.get("id") or ""))
            if p and p.webinar_id == w.id:
                if action == "open" and p.status in ("draft", "closed"): p.status = "open"
                elif action == "close" and p.status == "open": p.status = "closed"; p.share_results = bool(msg.get("share"))
                elif action == "share": p.share_results = bool(msg.get("on", True))
                await db.commit()
        mark_dirty(state, code)
    elif t == "wb_vote":
        async with SessionLocal() as db: ok = await wbs.vote(db, w.id, str(msg.get("id") or ""), key, msg.get("choices"))
        await say({"type": "wb-note", "message": "Thank you. Your answer was counted." if ok else "That poll is closed."})
        if ok: mark_dirty(state, code)
    elif t == "wb_live" and host and msg.get("on") and not state.get("web_live"):
        async with SessionLocal() as db:
            ww = await db.get(Webinar, w.id)
            if ww and not ww.started_at: ww.started_at = wbs.now(); await db.commit()
        await go_live(state, code, admit)
    elif t in ("wb_promote", "wb_demote") and st:
        ids = [str(i) for i in (msg.get("ids") or [msg.get("id")]) if i][:50]         # one person or a whole group at once
        on = t == "wb_promote"; ps = state.setdefault("promoted_keys", set()); n = 0
        for i in ids:
            target = state["peers"].get(i)
            if target and not staff(target) and (is_attendee(target) or target.get("promoted")):
                (ps.add if on else ps.discard)(target.get("key") or ""); n += 1
                await _send(target["ws"], {"type": "wb-promoted", "on": on, "by": me["name"]})         # their browser takes the camera and microphone (or lets them go) and joins again with the new part
        await say({"type": "wb-note", "message": (f"{n} invited to speak." if on else f"{n} moved back to watching.") if n else "Choose someone who is watching."})
    elif t == "wb_mute_all" and st:
        for i, p in list(state["peers"].items()):
            if i != pid and _rank(p) < _rank(me) and (p.get("promoted") or staff(p)):
                out = {"type": "force", "mic": False, "by": me["name"], "all": True}
                if msg.get("cam"): out["cam"] = False
                await _send(p["ws"], out)
    elif t == "wb_hand_clear" and st:
        target = state["peers"].get(str(msg.get("id") or ""))
        if target: target["hand"] = False; await _send(target["ws"], {"type": "wb-hand", "up": False})
    return True
