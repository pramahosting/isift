from starlette.requests import HTTPConnection
"""Built-in video meeting rooms.

Browsers connect directly to each other (WebRTC); this server only introduces them (signalling over a WebSocket),
hands out the STUN/TURN settings and stores recordings the host chooses to make. The room code in the link is the
secret, so guests can join without an account. Suited to small meetings (about 8 people).

A host can split a larger meeting into discussion groups. People in a group only see, hear and chat with that group (the server
refuses signalling and chat across groups), so every browser connects to a handful of people instead of the whole meeting.
"""
import asyncio, hmac, json, logging, os, secrets, shutil, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import APIRouter, Header, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.security import principal
from app.core import runtime_settings as rs
from app.models import User, Meeting, Room, RoomRecording, Job, AuditLog

log = logging.getLogger("isift")
router = APIRouter(prefix="/api/v1")
MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
WEBM = bytes.fromhex("1A45DFA3")

def ice_config() -> list[dict]:
    urls = [u.strip() for u in (settings.ice_servers or "").split(",") if u.strip()]
    out = []
    for u in urls:
        e = {"urls": u}
        if u.lower().startswith(("turn:", "turns:")) and settings.turn_username: e.update(username=settings.turn_username, credential=settings.turn_credential)
        out.append(e)
    return out

def room_url(base_url: str, code: str) -> str:
    p = urlsplit(base_url or "")
    if p.scheme not in ("http", "https") or not p.netloc: raise HTTPException(422, "Could not work out this app's web address.")
    return f"{p.scheme}://{p.netloc}/#/room/{code}"

ACCESS = ("open", "passcode", "signed_in")

def clean_access(value, passcode=None) -> tuple[str, str | None]:
    """Return (access, passcode) with defaults from Admin settings. A passcode is made when one is needed."""
    access = str(value or "").strip().lower()
    if access not in ACCESS: access = settings.room_default_access if settings.room_default_access in ACCESS else "open"
    if access != "passcode": return access, None
    pc = "".join(ch for ch in str(passcode or "") if ch.isalnum())[:12]
    if len(pc) < 4: pc = f"{secrets.randbelow(10**6):06d}"
    return access, pc

def clean_options(raw, keep: dict | None = None) -> dict:
    """Meeting options chosen by the host. Unknown keys are dropped; invitees must look like email addresses."""
    from app.services.invites import EMAIL
    out = dict(keep or {}); raw = raw if isinstance(raw, dict) else {}
    for k in ("mute_on_entry", "video_off_on_entry", "auto_record", "host_video_off", "participants_can_unmute", "participants_can_video", "virtual_room", "open_room"):
        if k in raw: out[k] = bool(raw[k])
    if "invitees" in raw:
        out["invitees"] = sorted({str(e).strip().lower() for e in (raw["invitees"] or []) if EMAIL.match(str(e).strip())})[:200]
    return out

async def make_room(db: AsyncSession, user: User, title: str, base_url: str, meeting: Meeting | None = None, start: datetime | None = None, minutes: int = 60,
                    access: str | None = None, passcode: str | None = None, waiting_room: bool | None = None, options: dict | None = None) -> tuple[Room, Meeting]:
    await rs.apply_overrides(db)
    access, passcode = clean_access(access, passcode)
    waiting = settings.room_default_waiting if waiting_room is None else bool(waiting_room)
    code = secrets.token_urlsafe(9).replace("_", "x").replace("-", "y")
    url = room_url(base_url, code)
    if meeting is None:
        start = start or datetime.now(timezone.utc)
        meeting = Meeting(owner_id=user.id, external_id=f"room:{code}", title=title, organizer=user.email, start_at=start, end_at=start + timedelta(minutes=minutes), sensitivity="normal", join_url=url, status="scheduled")
        db.add(meeting); await db.flush()
    else: meeting.join_url = url
    if (options or {}).get("open_room"): access, passcode, waiting = "open", None, False          # an open room needs no passcode and no admitting
    room = Room(code=code, host_id=user.id, meeting_id=meeting.id, title=title[:200], access=access, passcode=passcode, waiting_room=waiting, allow_guests=access != "signed_in", options=clean_options(options))
    db.add(room); await db.commit()
    return room, meeting

@router.post("/rooms")
async def create_room(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Start an instant meeting room now."""
    title = (str(payload.get("title") or "").strip() or f"{user.display_name or user.email}'s meeting")[:200]
    room, meeting = await make_room(db, user, title, str(payload.get("base_url") or ""), access=payload.get("access"), passcode=payload.get("passcode"), waiting_room=payload.get("waiting_room"), options=payload.get("options"))
    db.add(AuditLog(actor=user.email, action="room.create", resource_type="room", safe_metadata={"access": room.access, "waiting_room": room.waiting_room})); await db.commit()
    return {"code": room.code, "meeting_id": meeting.id, "url": meeting.join_url, "access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room}

@router.get("/rooms-recent")
async def rooms_recent(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Meeting rooms this person hosted lately (newest first), for the Join window's drop-down. Rooms that have ended are left out."""
    rows = (await db.execute(select(Room, Meeting).outerjoin(Meeting, Meeting.id == Room.meeting_id).where(Room.host_id == user.id, Room.ended_at.is_(None))
                             .order_by(Room.created_at.desc()).limit(40))).all()
    now = datetime.now(timezone.utc); out = []
    for r, m in rows:
        at = (m.start_at if m else None) or r.created_at
        if at and at.tzinfo is None: at = at.replace(tzinfo=timezone.utc)
        if at and at > now + timedelta(days=1): continue          # not yet: those are upcoming, not past
        out.append({"code": r.code, "title": r.title, "at": at.isoformat() if at else None})
    out.sort(key=lambda x: x["at"] or "", reverse=True)
    return {"rooms": out[:15]}

@router.get("/rooms/{code}")
async def room_info(code: str, authorization: str | None = Header(None), db: AsyncSession = Depends(get_db)):
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room: raise HTTPException(404, "This meeting link is not valid.")
    host = await db.get(User, room.host_id)
    me = await _user_from_token(authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None)
    from app.services import virtual_room as vr
    return {"options": {**{k: v for k, v in (room.options or {}).items() if k != "invitees"}, "virtual_room": await vr.effective(db, host, room.options)}, "access": "open" if (room.options or {}).get("open_room") else room.access, "waiting_room": False if (room.options or {}).get("open_room") else room.waiting_room, "you_are_host": bool(me and me.id == room.host_id), "signed_in": bool(me), "title": room.title, "ended": room.ended_at is not None, "host": (host.display_name or host.email) if host else "", "ice": ice_config(),
            "max_people": settings.room_max_people, "allow_guests": room.allow_guests, "people_now": len(HUB.get(code, {}).get("peers", {}))}

@router.post("/rooms/{code}/invite")
async def invite_people(code: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Invite people to a running meeting: an email with the link, plus an alert in iSift for anyone with an account.
    Allowed for the host and for signed-in people who are in the meeting."""
    from app.services.invites import EMAIL
    from app.services.notify import notify
    from app.api.routes_booking import _senders
    from app.integrations import mail as mailer
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room or room.ended_at is not None: raise HTTPException(404, "This meeting has ended or the link is not valid.")
    inside = room.host_id == user.id or any(p.get("user_id") == user.id for p in HUB.get(code, {}).get("peers", {}).values())
    if not inside: raise HTTPException(403, "Join the meeting first, then invite people.")
    raw = payload.get("emails") or []
    if isinstance(raw, str): raw = raw.replace(";", ",").replace("\n", ",").split(",")
    emails = list(dict.fromkeys(str(e).strip().lower() for e in raw if str(e).strip()))
    bad = [e for e in emails if not EMAIL.match(e)]
    if bad: raise HTTPException(422, f"“{bad[0]}” does not look like an email address.")
    if not emails: raise HTTPException(422, "Add at least one email address.")
    if len(emails) > 20: raise HTTPException(422, "Invite up to 20 people at a time.")
    link = room_url(str(payload.get("base_url") or ""), code); who = user.display_name or user.email
    note = str(payload.get("message") or "").strip()[:500]
    host = room.host_id == user.id
    lines = [f"{who} invites you to join the meeting “{room.title}” now.", "", f"Join: {link}", f"Meeting ID: {code}"]
    if room.access == "passcode": lines.append(f"Passcode: {room.passcode}" if host else "This meeting needs a passcode: ask the person who invited you.")
    if note: lines += ["", note]
    subject = f"{who} invited you to “{room.title}”"
    senders = await _senders(db, user); emailed, failed, alerted = [], [], []
    for to in emails:
        await notify(db, to, "invite", f"{who} invited you to “{room.title}”", note or "The meeting is happening now.", link, who); alerted.append(to)
        if not senders: continue
        err = ""
        for acct in senders:
            try: await mailer.send(acct, [to], subject, "\n".join(lines)); emailed.append(to); err = ""; break
            except mailer.MailError as exc: err = str(exc)
        if err: failed.append({"to": to, "reason": err})
    db.add(AuditLog(actor=user.email, action="room.invite", resource_type="room", safe_metadata={"people": len(emails)})); await db.commit()
    msg = f"Invited {len(emails)} {'person' if len(emails) == 1 else 'people'}. They see an alert in iSift if they have an account"
    msg += (f" and {len(emailed)} got an email." if emailed else ".") if senders else ". No email account is set up (Admin settings, Email sent by the app), so no email was sent."
    return {"alerted": alerted, "emailed": emailed, "failed": failed, "message": msg}

@router.get("/rooms/{code}/host")
async def room_host_view(code: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    room = await _host_room_any(db, code, user)
    return {"access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room, "url": (await db.get(Meeting, room.meeting_id)).join_url if room.meeting_id else None}

@router.patch("/rooms/{code}")
async def room_change(code: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """The host changes who can join. Applies to people who join from now on."""
    room = await _host_room_any(db, code, user)
    if "access" in payload or "passcode" in payload:
        room.access, room.passcode = clean_access(payload.get("access", room.access), payload.get("passcode") or (room.passcode if payload.get("access", room.access) == "passcode" else None))
        room.allow_guests = room.access != "signed_in"
    if "waiting_room" in payload: room.waiting_room = bool(payload["waiting_room"])
    await db.commit()
    return {"access": room.access, "passcode": room.passcode, "waiting_room": room.waiting_room}

async def _host_room_any(db: AsyncSession, code: str, user: User) -> Room:
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room: raise HTTPException(404, "Meeting not found")
    if room.host_id != user.id: raise HTTPException(403, "Only the host can do this.")
    return room

async def _user_from_token(token: str | None) -> User | None:
    if not token: return None
    async with SessionLocal() as db:
        try: return await principal(HTTPConnection({"type": "websocket", "path": "/", "headers": [], "query_string": b""}), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token), db)
        except HTTPException: return None

# ---- signalling hub (one server process; rooms are small) ----
HUB: dict[str, dict] = {}

async def _send(ws: WebSocket, msg: dict):
    try: await ws.send_text(json.dumps(msg))
    except Exception: pass

async def _broadcast(code: str, msg: dict, skip: str | None = None):
    for pid, p in list(HUB.get(code, {}).get("peers", {}).items()):
        if pid != skip: await _send(p["ws"], msg)

_FAILS: dict[str, list[float]] = {}      # wrong passcode attempts per room

def _passcode_ok(code: str, given: str, real: str | None) -> tuple[bool, str]:
    now = time.time(); tries = [t for t in _FAILS.get(code, []) if now - t < 600]
    if len(tries) >= 10: _FAILS[code] = tries; return False, "Too many wrong passcodes. Wait a few minutes and try again."
    if real and hmac.compare_digest(str(given or "").strip().encode(), real.encode()): return True, ""
    tries.append(now); _FAILS[code] = tries
    return False, "That passcode is not right."

async def _tell_hosts(state: dict):
    waiting = [{"id": i, "name": w["name"]} for i, w in state["waiting"].items()]
    for p in list(state["peers"].values()):
        if p["host"]: await _send(p["ws"], {"type": "waiting-list", "list": waiting})

def _rank(p: dict) -> int:
    """2 = the host, 1 = a co-host, 0 = everyone else."""
    return 0 if not p.get("host") else (1 if p.get("cohost") else 2)

def _pub(i: str, p: dict) -> dict: return {"id": i, "name": p["name"], "host": bool(p["host"]), "cohost": bool(p.get("cohost"))}

# ---- discussion groups ----
MAX_GROUPS = 30

def _gmeta(state: dict, gid: str | None) -> dict | None:
    """The group's public details, or None for the main room."""
    g = state.get("groups")
    if not gid or not g: return None
    for x in g["list"]:
        if x["id"] == gid: return {"id": x["id"], "name": x["name"]}
    return None

def _view(state: dict, gid: str | None) -> list[tuple[str, dict]]:
    """Everyone who is in one group (gid None = the main room), in the order they joined."""
    return [(i, p) for i, p in state["peers"].items() if p.get("group") == gid]

async def _to_view(state: dict, gid: str | None, msg: dict, skip: str | None = None):
    for i, p in _view(state, gid):
        if i != skip: await _send(p["ws"], msg)

def _ends_at(state: dict) -> str | None:
    g = state.get("groups"); return g.get("ends_at") if g else None

def _roster_msg(state: dict) -> dict:
    g = state.get("groups")
    return {"type": "roster", "groups": [{"id": x["id"], "name": x["name"]} for x in g["list"]] if g else None, "ends_at": _ends_at(state),
            "people": [{"id": i, "name": p["name"], "group": p.get("group"), "host": bool(p["host"]), "cohost": bool(p.get("cohost"))} for i, p in state["peers"].items()]}

async def _roster_to_hosts(state: dict, force: bool = False):
    """Hosts and co-hosts see who is in which group. Only sent while groups are open (or once more when they close)."""
    if not state.get("groups") and not force: return
    msg = _roster_msg(state)
    for p in list(state["peers"].values()):
        if p["host"]: await _send(p["ws"], msg)

async def _regroup(state: dict, moves: dict[str, str | None], reason: str | None = None):
    """Move people between groups (or back to the main room) and tell everyone whose group changed.

    Each member of an affected group gets the full list of who is now in it; their browser drops connections to
    people who are gone and connects to new ones. To avoid two browsers calling each other at once, the person who
    moved in makes the call (and when two people move in together, the one with the smaller id does)."""
    old: dict[str, str | None] = {}
    for pid, gid in moves.items():
        p = state["peers"].get(pid)
        if not p or p.get("group") == gid: continue
        old[pid] = p.get("group"); p["group"] = gid
    if not old: return
    moved_in: dict[str | None, set] = {}
    for pid in old: moved_in.setdefault(state["peers"][pid]["group"], set()).add(pid)
    for gid in set(old.values()) | set(moved_in):
        members = _view(state, gid); fresh = moved_in.get(gid, set())
        for i, p in members:
            offer = [j for j, _ in members if j != i and (j not in fresh or i < j)] if i in fresh else []
            await _send(p["ws"], {"type": "group", "group": _gmeta(state, gid), "peers": [_pub(j, q) for j, q in members if j != i], "offer_to": offer,
                                  "ends_at": _ends_at(state) if gid else None, "reason": reason if i in old else None, "moved": i in old})

async def _close_groups(state: dict, reason: str = "closed"):
    g = state.get("groups")
    if not g: return
    task = g.get("task")
    if task and task is not asyncio.current_task(): task.cancel()
    moves = {i: None for i, p in state["peers"].items() if p.get("group")}
    state["groups"] = None
    await _regroup(state, moves, reason)
    await _roster_to_hosts(state, force=True)

async def _auto_close(state: dict, token: str, seconds: float):
    await asyncio.sleep(seconds)
    g = state.get("groups")
    if g and g.get("token") == token:
        g["task"] = None; await _close_groups(state, "time")

def _split(ids: list[str], count: int) -> list[list[str]]:
    """Share people over `count` groups as evenly as possible, keeping the order they joined in."""
    size, extra = divmod(len(ids), count); out, at = [], 0
    for k in range(count):
        n = size + (1 if k < extra else 0); out.append(ids[at:at + n]); at += n
    return out

async def _groups_start(state: dict, pid: str, msg: dict):
    me = state["peers"][pid]
    if state.get("groups"): await _send(me["ws"], {"type": "groups-error", "message": "Discussion groups are already open. Bring everyone back first to start again."}); return
    include_hosts = bool(msg.get("include_hosts"))
    ids = [i for i, p in state["peers"].items() if p.get("group") is None and (include_hosts or _rank(p) == 0)]
    try: count = int(msg.get("count") or 0)
    except (TypeError, ValueError): count = 0
    if len(ids) < 2: await _send(me["ws"], {"type": "groups-error", "message": "At least two participants (not counting hosts) are needed to make groups."}); return
    if count < 2 or count > MAX_GROUPS: await _send(me["ws"], {"type": "groups-error", "message": f"Choose between 2 and {MAX_GROUPS} groups."}); return
    count = min(count, len(ids))
    token = uuid.uuid4().hex[:8]; mins = 0
    try: mins = int(msg.get("minutes") or 0)
    except (TypeError, ValueError): pass
    mins = mins if 1 <= mins <= 240 else 0
    ends = (datetime.now(timezone.utc) + timedelta(minutes=mins)).isoformat() if mins else None
    state["groups"] = {"list": [{"id": f"g{k + 1}", "name": f"Group {k + 1}"} for k in range(count)], "token": token, "ends_at": ends, "task": None}
    if mins: state["groups"]["task"] = asyncio.create_task(_auto_close(state, token, mins * 60))
    moves = {}
    for k, chunk in enumerate(_split(ids, count)):
        for i in chunk: moves[i] = f"g{k + 1}"
    await _regroup(state, moves, "assigned"); await _roster_to_hosts(state)

async def _groups_move(state: dict, pid: str, msg: dict):
    me = state["peers"][pid]; target = msg.get("id"); gid = msg.get("group") or None
    if not state.get("groups"): await _send(me["ws"], {"type": "groups-error", "message": "Discussion groups are not open."}); return
    if target not in state["peers"] or (gid and not _gmeta(state, gid)): await _send(me["ws"], {"type": "groups-error", "message": "That person or group is no longer there."}); return
    await _regroup(state, {target: gid}, "moved"); await _roster_to_hosts(state)

async def _admit(code: str, state: dict, pid: str, ws: WebSocket, name: str, is_host: bool, room_options: dict | None = None, user_id: str | None = None, cohost: bool = False) -> bool:
    if len(state["peers"]) >= max(2, settings.room_max_people):
        await _send(ws, {"type": "error", "message": "This meeting is full."}); return False
    peers_before = [_pub(i, p) for i, p in _view(state, None)]           # a newcomer starts in the main room
    state["peers"][pid] = {"ws": ws, "name": name, "host": is_host or cohost, "cohost": cohost, "user_id": user_id, "group": None}
    await _send(ws, {"type": "welcome", "id": pid, "host": is_host or cohost, "cohost": cohost, "policy": state["policy"], "peers": peers_before, "recording": state["recording"], "options": {**{k: v for k, v in (room_options or {}).items() if k != "invitees"}, "virtual_room": bool(state.get("vroom_allowed", True) and state.get("vroom", True))}, "vroom_allowed": bool(state.get("vroom_allowed", True)), "shape": state.get("shape", "rect"),
                     "waiting": [{"id": i, "name": w["name"]} for i, w in state["waiting"].items()] if (is_host or cohost) else [],
                     "groups_open": bool(state.get("groups")), "roster": _roster_msg(state) if (state.get("groups") and (is_host or cohost)) else None})
    await _to_view(state, None, {"type": "peer-joined", "id": pid, "name": name, "host": is_host or cohost, "cohost": cohost}, skip=pid)
    await _roster_to_hosts(state)
    return True

@router.websocket("/ws/rooms/{code}")
async def room_socket(ws: WebSocket, code: str):
    await ws.accept()
    pid = None
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=20))
        if first.get("type") != "join": await ws.close(); return
        async with SessionLocal() as db:
            room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
            if room:
                host_id, ended, access, passcode, waiting_room, room_options = room.host_id, room.ended_at is not None, room.access, room.passcode, room.waiting_room, dict(room.options or {})
                from app.services import virtual_room as vr
                vr_meeting = (room_options or {}).get("virtual_room", False) is True                          # the tick box in the meeting setup
                vr_allowed = await vr.allowed(db, await db.get(User, host_id))                                # the service and the host's account allow it
                room_options["virtual_room"] = vr_allowed and vr_meeting
                if room_options.get("open_room"): access, waiting_room = "open", False                  # open room: anyone joins at any time, nobody is admitted
        if not room or ended:
            await _send(ws, {"type": "error", "message": "This meeting has ended or the link is not valid."}); await ws.close(); return
        user = await _user_from_token(first.get("token"))
        is_host = bool(user and user.id == host_id)
        if access == "signed_in" and not user:
            await _send(ws, {"type": "error", "code": "signin", "message": "Sign in to join this meeting. It is only open to people with an account."}); await ws.close(); return
        if access == "passcode" and not is_host:
            ok, why = _passcode_ok(code, first.get("passcode"), passcode)
            if not ok: await _send(ws, {"type": "error", "code": "passcode", "message": why}); await ws.close(); return
        name = (str(first.get("name") or "").strip() or (user.display_name if user else "") or "Guest")[:60]
        state = HUB.setdefault(code, {"peers": {}, "waiting": {}, "recording": False, "groups": None, "vroom": vr_meeting, "vroom_allowed": vr_allowed,
                                      "policy": {"audio": room_options.get("participants_can_unmute", True) is not False, "video": room_options.get("participants_can_video", True) is not False}})
        client = str(first.get("client") or "")[:40]
        if client:                                         # the same browser tab joining again (refresh, network drop): drop its old, dead connection first
            for old_id, old in list(state["peers"].items()):
                if old.get("client") == client:
                    state["peers"].pop(old_id, None)
                    await _to_view(state, old.get("group"), {"type": "peer-left", "id": old_id})
                    try: await old["ws"].close()
                    except Exception: pass
        pid = uuid.uuid4().hex[:10]
        if is_host and any(_rank(p) == 2 for p in state["peers"].values()): is_host, cohost_join = False, True      # the host role was handed to someone else: come back as co-host
        else: cohost_join = False
        if room_options.get("open_room") and not is_host and not cohost_join:
            ranks = [_rank(p) for p in state["peers"].values()]
            if 2 not in ranks: is_host = True               # open room, nobody in charge: the first person in becomes the host
            elif 1 not in ranks: cohost_join = True         # the second person in becomes the co-host; everybody after is a normal participant   # nobody in charge is here: the first person in can run the room
        if waiting_room and not is_host and not cohost_join:
            state["waiting"][pid] = {"ws": ws, "name": name, "user_id": user.id if user else None}
            await _send(ws, {"type": "waiting"}); await _tell_hosts(state)
        elif not await _admit(code, state, pid, ws, name, is_host, room_options, user.id if user else None, cohost_join):
            pid = None; await ws.close(); return
        if pid in state["peers"]: state["peers"][pid]["client"] = client
        while True:
            msg = json.loads(await ws.receive_text()); t = msg.get("type")
            if pid not in state["peers"]:
                continue                                  # still in the waiting room: nothing else is allowed yet
            if t == "signal":
                target = state["peers"].get(msg.get("to"))
                if target and target.get("group") == state["peers"][pid].get("group"): await _send(target["ws"], {"type": "signal", "from": pid, "data": msg.get("data")})
            elif t == "chat":
                text = str(msg.get("text") or "")[:2000]
                if text.strip():
                    out = {"type": "chat", "from": pid, "name": name, "text": text, "at": datetime.now(timezone.utc).isoformat()}
                    to = msg.get("to")
                    if isinstance(to, list) and to:      # one person or a chosen group of people in the room
                        ids = [i for i in dict.fromkeys(str(x) for x in to[:50]) if i in state["peers"] and i != pid and state["peers"][i].get("group") == state["peers"][pid].get("group")]
                        if not ids: await _send(ws, {"type": "chat-error", "message": "Those people are not in your group or have left the meeting."}); continue
                        out.update({"to": ids, "to_names": [state["peers"][i]["name"] for i in ids]})
                        for i in [pid] + ids: await _send(state["peers"][i]["ws"], out)
                    else:
                        await _to_view(state, state["peers"][pid].get("group"), out)        # to everyone in the same group (or the main room)
            elif t == "state":      # mic / camera / screen-share indicators
                me = state["peers"][pid]; mic, cam = bool(msg.get("mic")), bool(msg.get("cam"))
                if _rank(me) == 0:                          # the host's rules: a participant cannot switch on what is not allowed
                    if mic and not state["policy"]["audio"]: mic = False; await _send(ws, {"type": "force", "mic": False, "reason": "policy"})
                    if cam and not state["policy"]["video"]: cam = False; await _send(ws, {"type": "force", "cam": False, "reason": "policy"})
                await _to_view(state, me.get("group"), {"type": "state", "id": pid, "mic": mic, "cam": cam, "screen": bool(msg.get("screen"))}, skip=pid)
            elif _rank(state["peers"][pid]) >= 1 and t == "groups_start": await _groups_start(state, pid, msg)
            elif _rank(state["peers"][pid]) >= 1 and t == "groups_move": await _groups_move(state, pid, msg)
            elif _rank(state["peers"][pid]) >= 1 and t == "groups_end": await _close_groups(state, "closed")
            elif _rank(state["peers"][pid]) >= 1 and t == "announce":
                text = str(msg.get("text") or "").strip()[:300]
                if text: await _broadcast(code, {"type": "announce", "name": state["peers"][pid]["name"], "text": text})
            elif t == "help" and state.get("groups") and state["peers"][pid].get("group"):
                gm = _gmeta(state, state["peers"][pid]["group"])
                for p in list(state["peers"].values()):
                    if p["host"]: await _send(p["ws"], {"type": "help", "name": state["peers"][pid]["name"], "group": gm["name"] if gm else ""})
            elif _rank(state["peers"][pid]) >= 1 and t in ("admit", "admit_all"):
                ids = list(state["waiting"]) if t == "admit_all" else [msg.get("id")]
                for wid in ids:
                    w = state["waiting"].pop(wid, None)
                    if w and not await _admit(code, state, wid, w["ws"], w["name"], False, room_options, w.get("user_id")):
                        try: await w["ws"].close()
                        except Exception: pass
                await _tell_hosts(state)
            elif _rank(state["peers"][pid]) >= 1 and t == "deny":
                w = state["waiting"].pop(msg.get("id"), None)
                if w:
                    await _send(w["ws"], {"type": "denied"})
                    try: await w["ws"].close()
                    except Exception: pass
                await _tell_hosts(state)
            elif _rank(state["peers"][pid]) == 2 and t == "record":
                state["recording"] = bool(msg.get("on")); await _broadcast(code, {"type": "recording", "on": state["recording"]})
            elif _rank(state["peers"][pid]) >= 1 and t in ("kick", "force", "ask", "mute_all", "policy", "role", "vroom", "tshape"):
                me = state["peers"][pid]; target = state["peers"].get(msg.get("id"))
                if t == "kick":
                    if target and msg.get("id") != pid and _rank(target) < _rank(me): await _send(target["ws"], {"type": "kicked"}); await target["ws"].close()
                elif t == "force":                          # switch someone's microphone and/or camera off (people turn them back on themselves)
                    if target and msg.get("id") != pid and _rank(target) < _rank(me):
                        out = {"type": "force", "by": me["name"]}
                        if msg.get("mic") is False: out["mic"] = False
                        if msg.get("cam") is False: out["cam"] = False
                        if len(out) > 2: await _send(target["ws"], out)
                elif t == "ask":                            # ask someone to switch their microphone or camera on
                    if target and msg.get("id") != pid: await _send(target["ws"], {"type": "ask", "by": me["name"], "what": "cam" if msg.get("what") == "cam" else "mic"})
                elif t == "mute_all":
                    for i, p in state["peers"].items():
                        if i != pid and _rank(p) < _rank(me): await _send(p["ws"], {"type": "force", "mic": False, "by": me["name"], "all": True})
                elif t == "vroom":                          # the host or a co-host switches the virtual room (boardroom table) on or off while the meeting runs
                    if state.get("vroom_allowed", True):
                        state["vroom"] = bool(msg.get("on"))
                        await _broadcast(code, {"type": "vroom", "on": state["vroom"], "by": me["name"]})
                elif t == "tshape":                  # the host or a co-host flips the boardroom table between rectangular and round; everyone sees it
                    state["shape"] = "round" if msg.get("shape") == "round" else "rect"
                    await _broadcast(code, {"type": "tshape", "shape": state["shape"], "by": me["name"]})
                elif t == "policy":
                    for key, field in (("audio", "audio"), ("video", "video")):
                        if key in msg: state["policy"][field] = bool(msg[key])
                    await _broadcast(code, {"type": "policy", **state["policy"], "by": me["name"]})
                    if msg.get("mute_now"):
                        for i, p in state["peers"].items():
                            if i != pid and _rank(p) < 1: await _send(p["ws"], {"type": "force", "mic": False, "by": me["name"], "all": True})
                elif t == "role" and _rank(me) == 2 and target and msg.get("id") != pid:       # only the host hands out roles
                    role = msg.get("role")
                    if role == "cohost": target["host"], target["cohost"] = True, True; await _broadcast(code, {"type": "role", "id": msg["id"], "host": True, "cohost": True}); await _send(target["ws"], {"type": "role", "id": msg["id"], "host": True, "cohost": True, "self": True})
                    elif role == "participant" and _rank(target) == 1: target["host"], target["cohost"] = False, False; await _broadcast(code, {"type": "role", "id": msg["id"], "host": False, "cohost": False}); await _send(target["ws"], {"type": "role", "id": msg["id"], "host": False, "cohost": False, "self": True})
                    elif role == "host":
                        if not target.get("user_id"): await _send(ws, {"type": "role-error", "message": "Only a signed-in person can be made the host, because hosting needs an account. Make them co-host instead."})
                        else:
                            async with SessionLocal() as db:
                                r = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
                                if r: r.host_id = target["user_id"]; await db.commit()
                            target["host"], target["cohost"] = True, False; me["host"], me["cohost"] = False, False
                            for i, p in ((msg["id"], target), (pid, me)):
                                await _broadcast(code, {"type": "role", "id": i, "host": p["host"], "cohost": False}); await _send(p["ws"], {"type": "role", "id": i, "host": p["host"], "cohost": False, "self": True, "transferred": True})
                            await _tell_hosts(state)
            elif _rank(state["peers"][pid]) == 2 and t == "end":
                async with SessionLocal() as db:
                    r = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
                    if r and not (r.options or {}).get("open_room"):               # an open room is never closed for good: everyone leaves, the link keeps working
                        r.ended_at = datetime.now(timezone.utc); await finish_meeting(db, r); await db.commit()
                await _broadcast(code, {"type": "ended"})
                for p in list(state["peers"].values()) + list(state["waiting"].values()):
                    try: await p["ws"].close()
                    except Exception: pass
                break
    except (WebSocketDisconnect, asyncio.TimeoutError, json.JSONDecodeError, RuntimeError):
        pass
    finally:
        state = HUB.get(code)
        if state and pid:
            if state["waiting"].pop(pid, None) is not None: await _tell_hosts(state)
            if pid in state["peers"]:
                gone = state["peers"].pop(pid, None)
                await _to_view(state, gone.get("group") if gone else None, {"type": "peer-left", "id": pid})
                await _roster_to_hosts(state)
            if not state["peers"] and not state["waiting"]:
                task = (state.get("groups") or {}).get("task")
                if task: task.cancel()
                HUB.pop(code, None)

async def finish_meeting(db: AsyncSession, room: Room) -> None:
    """A meeting that really took place: record when it actually ended and mark it completed (the caller commits)."""
    m = await db.get(Meeting, room.meeting_id) if room.meeting_id else None
    if not m or m.status in ("cancelled", "completed"): return
    now = datetime.now(timezone.utc); start = m.start_at if m.start_at.tzinfo else m.start_at.replace(tzinfo=timezone.utc)
    m.end_at = max(now, start + timedelta(minutes=1)); m.status = "completed"

async def end_room(db: AsyncSession, room: Room, cancel_meeting: bool) -> None:
    """Close a meeting room for everyone and, if asked, mark its calendar entry cancelled."""
    if room.ended_at is None and not (room.options or {}).get("pmi") and not ((room.options or {}).get("open_room") and not cancel_meeting):
        room.ended_at = datetime.now(timezone.utc)   # a personal meeting room is permanent
        if not cancel_meeting: await finish_meeting(db, room)
    if cancel_meeting and room.meeting_id:
        m = await db.get(Meeting, room.meeting_id)
        if m and m.status != "cancelled": m.status = "cancelled"
    await db.commit()
    state = HUB.get(room.code)
    if state:
        await _broadcast(room.code, {"type": "ended"})
        for p in list(state["peers"].values()) + list(state["waiting"].values()):
            try: await p["ws"].close()
            except Exception: pass

@router.post("/rooms/{code}/end")
async def end_meeting(code: str, payload: dict | None = None, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """The host ends the meeting for everyone (and cancels it on the calendar when `cancel` is true)."""
    room = await _host_room_any(db, code, user)
    await end_room(db, room, bool((payload or {}).get("cancel", True)))
    db.add(AuditLog(actor=user.email, action="room.end", resource_type="room", safe_metadata={})); await db.commit()
    return {"ok": True}

# ---- recordings ----
async def _host_room(db: AsyncSession, code: str, user: User) -> Room:
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room: raise HTTPException(404, "Meeting not found")
    if room.host_id != user.id: raise HTTPException(403, "Only the host can save a recording.")
    return room

async def _save_upload(f: UploadFile, dest: Path, limit: int) -> int:
    size, head = 0, b""
    try:
        with dest.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > limit: raise HTTPException(413, "The recording is larger than the allowed size.")
                if not head: head = chunk[:4]
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True); raise
    if head != WEBM: dest.unlink(missing_ok=True); raise HTTPException(415, "The recording is not a valid WebM file.")
    return size

@router.post("/rooms/{code}/recording")
async def save_recording(code: str, consent_acknowledged: bool = Form(...), cloud: bool = Form(False), audio: UploadFile = File(...), video: UploadFile | None = File(None),
                         user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    if not consent_acknowledged: raise HTTPException(400, "Confirm that participants were told the meeting was recorded.")
    room = await _host_room(db, code, user)
    base = Path(settings.audio_storage_dir) / "recordings"; base.mkdir(parents=True, exist_ok=True)
    rid = str(uuid.uuid4()); keep = base / f"{rid}.webm"
    audio_path = Path(settings.audio_storage_dir) / f"{rid}-speech.webm"; Path(settings.audio_storage_dir).mkdir(parents=True, exist_ok=True)
    a_size = await _save_upload(audio, audio_path, settings.audio_max_bytes)
    size = a_size
    if not cloud:
        # Default: the host's browser keeps the file on their own computer. Nothing is stored on the server (only the speech audio, for the transcript).
        keep.unlink(missing_ok=True); has_video = False
        note = "Recording saved on your computer."
    else:
        if video is not None and video.filename:
            size = await _save_upload(video, keep, MAX_VIDEO_BYTES)
            has_video = True
        else:
            shutil.copyfile(audio_path, keep); has_video = False          # audio-only meeting: keep a copy for download
        from app.services import storage, billing
        try: placed = await storage.store_file(keep, user, rid, has_video)
        except Exception as exc:
            log.exception("Could not store recording")
            audio_path.unlink(missing_ok=True); keep.unlink(missing_ok=True)
            raise HTTPException(502, "The recording could not be saved to cloud storage: " + str(exc)[:160] + " Check Admin settings > Recording storage and press Connection test. Your own computer's copy is not affected.")
        size = placed.pop("size_bytes")
        plan = await billing.plan_of(db, user)
        expires = datetime.now(timezone.utc) + timedelta(days=storage.BASIC_DAYS) if plan == "basic" else None
        db.add(RoomRecording(id=rid, room_id=room.id, size_bytes=size, has_video=has_video, expires_at=expires, **placed))
        note = "Recording saved on your computer and in the cloud." + (" On the Basic plan the cloud copy is removed after 2 days; upgrade to keep it longer." if expires else "")
    meeting = await db.get(Meeting, room.meeting_id) if room.meeting_id else None
    from app.services.llm import transcription_configured
    if meeting and transcription_configured():
        db.add(Job(kind="transcribe_audio", payload={"meeting_id": meeting.id, "path": str(audio_path), "filename": f"{rid}.webm", "owner_id": user.id}))
        meeting.transcript_status = "queued"; note += " The transcript is being prepared and will appear under Transcripts."
    else:
        audio_path.unlink(missing_ok=True)
        note += " To get a transcript, an administrator must add a transcription model in Admin settings."
    db.add(AuditLog(actor=user.email, action="room.recording.saved", resource_type="room", safe_metadata={"bytes": size, "video": has_video}))
    await db.commit()
    return {"id": rid, "message": note}

def resolve_recording(path: str, rid: str) -> Path | None:
    """Find a recording file even if the app folder was moved or renamed since it was saved."""
    base = Path(settings.audio_storage_dir) / "recordings"
    for cand in (Path(path), base / f"{rid}.webm", base / Path(str(path).replace("\\", "/")).name):
        try:
            if cand.is_file(): return cand
        except OSError: pass
    return None

@router.get("/recordings")
async def my_recordings(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    from app.services import storage as _st
    await _st.purge_expired(db)
    rows = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(Room.host_id == user.id).order_by(RoomRecording.created_at.desc()).limit(100))).all()
    return [{"id": r.id, "title": room.title, "created_at": (r.created_at.replace(tzinfo=timezone.utc) if r.created_at.tzinfo is None else r.created_at).isoformat(), "size_bytes": r.size_bytes, "has_video": r.has_video, "storage": r.storage, "expires_at": (r.expires_at.replace(tzinfo=timezone.utc) if r.expires_at is not None and r.expires_at.tzinfo is None else r.expires_at).isoformat() if r.expires_at else None, "available": r.storage in ("r2", "database") or resolve_recording(r.path, r.id) is not None} for r, room in rows]

@router.get("/recordings/{rid}/file")
async def recording_file(rid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(RoomRecording.id == rid))).first()
    if not row or row[1].host_id != user.id: raise HTTPException(404, "Recording not found")
    rec = row[0]; fname = f"{row[1].title[:40] or 'meeting'}"
    if rec.storage == "r2":
        from app.services import storage
        try:
            obj = storage.client().get_object(Bucket=settings.r2_bucket, Key=rec.object_key)
        except Exception: raise HTTPException(502, "Cloud storage could not be reached. Check Admin settings > Recording storage.")
        ext = ".mp4" if rec.mimetype == "video/mp4" else ".webm"
        return StreamingResponse(obj["Body"].iter_chunks(1024 * 1024), media_type=rec.mimetype or "video/webm", headers={"Content-Disposition": f'inline; filename="{fname}{ext}"', "Content-Length": str(obj["ContentLength"])})
    if rec.storage == "database":
        blob = (await db.execute(select(RoomRecording.data).where(RoomRecording.id == rid))).scalar_one_or_none()
        if not blob: raise HTTPException(410, "This recording is no longer stored.")
        return Response(bytes(blob), media_type=rec.mimetype or "video/webm", headers={"Content-Disposition": f'inline; filename="{fname}.webm"'})
    found = resolve_recording(row[0].path, row[0].id)
    if not found: raise HTTPException(410, "The recording file is no longer in the recordings folder. If you moved the app, copy its docs/data/audio folder across too.")
    return FileResponse(found, media_type="video/webm" if row[0].has_video else "audio/webm", filename=f"{row[1].title[:40] or 'meeting'}.webm")

@router.delete("/recordings/{rid}")
async def delete_recording(rid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(RoomRecording.id == rid))).first()
    if not row or row[1].host_id != user.id: raise HTTPException(404, "Recording not found")
    if row[0].storage == "r2" and row[0].object_key:
        from app.services import storage
        await asyncio.to_thread(storage.delete_object, row[0].object_key)
    found = resolve_recording(row[0].path, row[0].id) if row[0].path else None
    if found: found.unlink(missing_ok=True)
    await db.delete(row[0])
    db.add(AuditLog(actor=user.email, action="room.recording.deleted", resource_type="room", safe_metadata={})); await db.commit()
    return {"ok": True}
