from starlette.requests import HTTPConnection
"""Built-in video meeting rooms.

Browsers connect directly to each other (WebRTC); this server only introduces them (signalling over a WebSocket),
hands out the STUN/TURN settings and stores recordings the host chooses to make. The room code in the link is the
secret, so guests can join without an account. Suited to small meetings (about 8 people).

A host can split a larger meeting into discussion groups. People in a group only see, hear and chat with that group (the server
refuses signalling and chat across groups), so every browser connects to a handful of people instead of the whole meeting.
"""
import asyncio, hmac, json, logging, os, re, secrets, shutil, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote as _urlquote, urlsplit, urlunsplit
from fastapi import APIRouter, Header, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
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

_TURN_CACHE: dict = {"at": 0.0, "key": "", "servers": []}

async def ice_config() -> list[dict]:
    """STUN/TURN servers handed to every browser. Without a TURN relay, people behind strict firewalls, phone data or some home routers
    cannot send or receive video and sound, so the relay options are built here: fixed TURN, coturn short-lived passwords, or Cloudflare Realtime TURN."""
    urls = [u.strip() for u in (settings.ice_servers or "").split(",") if u.strip()]
    out = []
    for u in urls:
        e = {"urls": u}
        if u.lower().startswith(("turn:", "turns:")):
            if settings.turn_shared_secret:
                import base64, hashlib, hmac
                user = f"{int(time.time()) + 6 * 3600}:isift"
                e.update(username=user, credential=base64.b64encode(hmac.new(settings.turn_shared_secret.encode(), user.encode(), hashlib.sha1).digest()).decode())
            elif settings.turn_username: e.update(username=settings.turn_username, credential=settings.turn_credential)
        out.append(e)
    if settings.cf_turn_key_id and settings.cf_turn_api_token:
        key = settings.cf_turn_key_id
        if _TURN_CACHE["key"] != key or time.time() - _TURN_CACHE["at"] > 3000:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=6) as c:
                    r = await c.post(f"https://rtc.live.cloudflare.com/v1/turn/keys/{key}/credentials/generate", headers={"Authorization": f"Bearer {settings.cf_turn_api_token}"}, json={"ttl": 14400})
                    r.raise_for_status(); j = r.json().get("iceServers")
                    j = [j] if isinstance(j, dict) else (j or [])
                _TURN_CACHE.update(at=time.time(), key=key, servers=j)
            except Exception: log.exception("Could not get Cloudflare TURN credentials")
        out.extend(_TURN_CACHE["servers"] if _TURN_CACHE["key"] == key else [])
    if not any(str(x.get("urls")).startswith("stun:") for x in out): out.insert(0, {"urls": ["stun:stun.cloudflare.com:3478", "stun:stun.l.google.com:19302"]})
    return out

def room_url(base_url: str, code: str) -> str:
    p = urlsplit(base_url or "")
    if p.scheme not in ("http", "https") or not p.netloc: raise HTTPException(422, "Could not work out this app's web address.")
    return f"{p.scheme}://{p.netloc}/#/room/{code}"

ACCESS = ("open", "passcode", "signed_in")

def clean_access(value, passcode=None) -> tuple[str, str | None]:
    """Return (access, passcode) with defaults from Admin Console. A passcode is made when one is needed."""
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
    if (options or {}).get("open_room"):
        from app.services import entitlements as ent
        if not await ent.can_open_room(db, user): raise HTTPException(403, "An open room is available to the administrator and to paid plans. Upgrade your plan, or ask an administrator to allow it for you.")
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

OLD_PMI_TITLES = {f"{n}'s Personal Meeting Room" for n in ("Administrator", "Local Demo Administrator")}

def refresh_pmi_title(room: Room, host) -> bool:
    """A personal room still carrying an old default name takes its host's current name (a name the host typed is never touched)."""
    if host and host.display_name and (room.options or {}).get("pmi") and room.title in OLD_PMI_TITLES:
        room.title = f"{host.display_name}'s Personal Meeting Room"; return True
    return False

@router.get("/rooms/{code}")
async def room_info(code: str, authorization: str | None = Header(None), db: AsyncSession = Depends(get_db)):
    room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
    if not room: raise HTTPException(404, "This meeting link is not valid.")
    host = await db.get(User, room.host_id)
    if room.ended_at is not None and (room.options or {}).get("pmi"): room.ended_at = None; await db.commit()
    if refresh_pmi_title(room, host): await db.commit()
    me = await _user_from_token(authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None)
    from app.services import virtual_room as vr
    return {"options": {**{k: v for k, v in (room.options or {}).items() if k != "invitees"}, "virtual_room": await vr.effective(db, host, room.options)}, "access": "open" if (room.options or {}).get("open_room") else room.access, "waiting_room": False if (room.options or {}).get("open_room") else room.waiting_room, "you_are_host": bool(me and me.id == room.host_id), "signed_in": bool(me), "title": room.title, "ended": room.ended_at is not None, "host": (host.display_name or host.email) if host else "", "ice": await ice_config(),
            "max_people": min(settings.room_max_people, HUB.get(code, {}).get("max_people") or settings.room_max_people), "allow_guests": room.allow_guests, "people_now": len(HUB.get(code, {}).get("peers", {}))}

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
    msg += (f" and {len(emailed)} got an email." if emailed else ".") if senders else ". No email account is set up (Admin Console, Email sent by the app), so no email was sent."
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

REACTIONS = {"👍", "👏", "❤️", "😂", "😮", "🎉", "🙏", "😢", "🔥", "💯", "👎", "✅"}

def _rank(p: dict) -> int:
    """2 = the host, 1 = a co-host, 0 = everyone else."""
    return 0 if not p.get("host") else (1 if p.get("cohost") else 2)

async def _pen_clear(state: dict, sharer: str, code: str):
    if (state.get("pen") or {}).pop(sharer, None) is not None:
        await _broadcast(code, {"type": "pen", "sharer": sharer, "holder": None, "name": ""})

_DOC_HOSTS = ("onedrive.live.com", "sharepoint.com", "office.com", "dropbox.com", "notion.site", "notion.so", "canva.com", "miro.com", "lucid.app", "airtable.com", "figma.com")

def _doc_url(raw: str):
    """A link to a cloud document that may be shown inside the meeting: only https, and only well-known document services (a guest cannot push any web page onto everyone's screen).
    Returns (address to embed, label) or None. Google links are turned into their read-only preview, which scrolls and pages on its own."""
    raw = (raw or "").strip()
    if len(raw) > 800: return None
    try: u = urlsplit(raw)
    except ValueError: return None
    h = (u.hostname or "").lower()
    if u.scheme != "https" or not h: return None
    names = {"document": "Google Doc", "spreadsheets": "Google Sheet", "presentation": "Google Slides"}
    if h == "docs.google.com":
        m = re.match(r"^/(document|spreadsheets|presentation)/d/e/([A-Za-z0-9_-]+)", u.path)                      # published to the web
        if m:
            kind, key = m.groups()
            tail = {"document": "pub?embedded=true", "spreadsheets": "pubhtml?widget=true&headers=false", "presentation": "embed?start=false&loop=false"}[kind]
            return f"https://docs.google.com/{kind}/d/e/{key}/{tail}", names[kind]
        m = re.match(r"^/(document|spreadsheets|presentation)/d/([A-Za-z0-9_-]{10,})", u.path)
        if m: return f"https://docs.google.com/{m.group(1)}/d/{m.group(2)}/preview", names[m.group(1)]
        return None
    if h == "drive.google.com":
        m = re.match(r"^/file/d/([A-Za-z0-9_-]{10,})", u.path)
        return (f"https://drive.google.com/file/d/{m.group(1)}/preview", "Google Drive file") if m else None
    if any(h == d or h.endswith("." + d) for d in _DOC_HOSTS):
        if h.endswith("figma.com"): return "https://www.figma.com/embed?embed_host=isift&url=" + _urlquote(raw, safe=""), "Figma"
        label = next(n for d, n in (("sharepoint.com", "SharePoint"), ("onedrive", "OneDrive"), ("office.com", "Microsoft 365"), ("dropbox.com", "Dropbox"), ("notion", "Notion"), ("canva.com", "Canva"), ("miro.com", "Miro"), ("lucid.app", "Lucid"), ("airtable.com", "Airtable")) if d in h)
        return urlunsplit(u._replace(fragment="")), label
    return None

def _video_view(v: dict) -> dict:
    """What everyone needs to join a shared video: which one, whether it plays, and where it is right now."""
    t = v["t"] + ((time.time() - v["at"]) if v["playing"] else 0)
    return {"kind": v.get("kind", "yt"), "vid": v.get("vid", ""), "url": v.get("url", ""), "label": v.get("label", ""), "by": v["by"], "by_id": v["by_id"], "playing": v["playing"], "t": round(t, 2)}

def _pub(i: str, p: dict) -> dict:
    d = {"id": i, "name": p["name"], "host": bool(p["host"]), "cohost": bool(p.get("cohost"))}
    if p.get("hand"): d["hand"] = True
    if p.get("sfu"): d["sfu"] = p["sfu"]; d["screen"] = bool(p.get("screen"))
    return d


# ---- big meetings: video carried by the Cloudflare SFU ----
def _stage_ids(state: dict) -> list[str]:
    """Who is shown and heard in a big meeting: screen sharers, the latest speakers, the host and co-hosts, then the newest arrivals."""
    n = max(2, min(16, settings.sfu_on_stage)); peers = state["peers"]; now = time.time(); order: list[str] = []
    def add(i):
        if i in peers and peers[i].get("sfu") and i not in order: order.append(i)
    for i, p in peers.items():
        if p.get("screen"): add(i)
    for i, p in sorted(peers.items(), key=lambda kv: -kv[1].get("spoke", 0)):
        if p.get("spoke") and now - p["spoke"] < 90: add(i)
    for i, p in peers.items():
        if _rank(p) >= 1: add(i)
    for i in reversed(list(peers)): add(i)
    return order[:n]

async def _stage_update(state: dict):
    ids = _stage_ids(state)
    if ids == state.get("stage"): return
    wait = 3.0 - (time.time() - state.get("stage_at", 0))
    if wait > 0:                                   # change at most every few seconds so the picture does not jump about
        t = state.get("stage_task")
        if not t or t.done():
            async def later():
                await asyncio.sleep(wait); state["stage_task"] = None; await _stage_update(state)
            state["stage_task"] = asyncio.create_task(later())
        return
    state["stage"] = ids; state["stage_at"] = time.time()
    for p in list(state["peers"].values()): await _send(p["ws"], {"type": "sfu-active", "ids": ids})

async def _sfu_op(state: dict, pid: str, msg: dict):
    from app.services import sfu
    me = state["peers"][pid]; req = str(msg.get("req") or "")[:40]; t = msg.get("type")
    async def fail(text): await _send(me["ws"], {"type": "sfu-res", "req": req, "ok": False, "message": text})
    try:
        if t == "sfu-push":
            kinds = [x for x in (msg.get("tracks") or [])[:2] if isinstance(x, dict) and x.get("kind") in ("audio", "video") and isinstance(x.get("mid"), str) and 0 < len(x["mid"]) <= 16]
            sdp = msg.get("sdp")
            if not kinds or not isinstance(sdp, str) or len(sdp) > 60000: return await fail("Could not start sending your video.")
            if not me.get("sfu_pub"): me["sfu_pub"] = await sfu.new_session()
            j = await sfu.push(me["sfu_pub"], sdp, [{"mid": k["mid"], "name": f"{pid}-{k['kind']}"} for k in kinds])
            me["sfu"] = {"session": me["sfu_pub"], "tracks": {k["kind"]: f"{pid}-{k['kind']}" for k in kinds}}
            await _send(me["ws"], {"type": "sfu-res", "req": req, "ok": True, "sdp": (j.get("sessionDescription") or {}).get("sdp")})
            for i, p in list(state["peers"].items()):
                if i != pid: await _send(p["ws"], {"type": "sfu-pub", "id": pid, "sfu": me["sfu"], "screen": bool(me.get("screen"))})
            await _stage_update(state)
        elif t == "sfu-pull":
            wanted, meta = [], {}
            for i in [str(x) for x in (msg.get("ids") or [])[:16]]:
                p = state["peers"].get(i)
                if i == pid or not p or not p.get("sfu"): continue
                for kind, name in p["sfu"]["tracks"].items():
                    wanted.append({"session": p["sfu"]["session"], "name": name}); meta[name] = {"id": i, "kind": kind}
            if not wanted: return await _send(me["ws"], {"type": "sfu-res", "req": req, "ok": True, "session": None, "tracks": []})
            sess = await sfu.new_session(); me.setdefault("sfu_subs", set()).add(sess)
            j = await sfu.pull(sess, wanted)
            await _send(me["ws"], {"type": "sfu-res", "req": req, "ok": True, "session": sess, "sdp": (j.get("sessionDescription") or {}).get("sdp"),
                                   "tracks": [{"mid": x.get("mid"), **meta[x["trackName"]]} for x in (j.get("tracks") or []) if x.get("trackName") in meta and x.get("mid") is not None]})
        elif t == "sfu-answer":
            sess, sdp = msg.get("session"), msg.get("sdp")
            if sess not in me.get("sfu_subs", set()) or not isinstance(sdp, str): return await fail("That video session is not yours.")
            await sfu.renegotiate(sess, sdp)
            await _send(me["ws"], {"type": "sfu-res", "req": req, "ok": True})
    except sfu.SfuError as ex:
        await fail(str(ex))
    except Exception:
        log.exception("big-meeting video step failed"); await fail("The video server had a problem. Try again in a moment.")

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
    if state.get("sfu"): await _send(me["ws"], {"type": "groups-error", "message": "Discussion groups are not available in big meetings."}); return
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

def _multi_on(state: dict) -> bool:
    """Several people may share at once when the host's plan includes it and the host has not switched it off."""
    return bool(state.get("multi_ok", True) and state.get("multi_share", True))

async def _admit(code: str, state: dict, pid: str, ws: WebSocket, name: str, is_host: bool, room_options: dict | None = None, user_id: str | None = None, cohost: bool = False) -> bool:
    cap = max(2, min(settings.room_max_people, state.get("max_people") or settings.room_max_people))
    if len(state["peers"]) >= cap:
        await _send(ws, {"type": "error", "message": f"This meeting is full ({cap} people is the limit for the host's plan)."}); return False
    peers_before = [_pub(i, p) for i, p in _view(state, None)]           # a newcomer starts in the main room
    state["peers"][pid] = {"ws": ws, "name": name, "host": is_host or cohost, "cohost": cohost, "user_id": user_id, "group": None}
    from app.services import sfu as _sfu
    switching = bool(not state.get("sfu") and _sfu.configured() and len(state["peers"]) >= settings.sfu_from_people)
    if switching:
        if state.get("groups"): await _close_groups(state, "closed")
        state["sfu"] = True                      # from now on this meeting uses the Cloudflare video server
    await _send(ws, {"type": "welcome", "id": pid, "host": is_host or cohost, "cohost": cohost, "policy": state["policy"], "peers": peers_before, "recording": state["recording"], "can_record": state.get("rec_ok", True), "cloud_rec": state.get("cloud_ok", True), "ends_in": max(0, int(state["started"] + state["limit"] * 60 - time.time())) if state.get("limit") else None, "options": {**{k: v for k, v in (room_options or {}).items() if k != "invitees"}, "virtual_room": bool(state.get("vroom_allowed", True) and state.get("vroom", True))}, "vroom_allowed": bool(state.get("vroom_allowed", True)), "shape": state.get("shape", "rect"),
                     "waiting": [{"id": i, "name": w["name"]} for i, w in state["waiting"].items()] if (is_host or cohost) else [],
                     "groups_open": bool(state.get("groups")), "roster": _roster_msg(state) if (state.get("groups") and (is_host or cohost)) else None,
                     "sfu": bool(state.get("sfu")), "stage": state.get("stage") or [], "total": len(state["peers"]),
                     "locked": bool(state.get("locked")), "hide_pics": bool(state.get("hide_pics")), "captions": bool(state.get("captions_want")), "video": _video_view(state["video"]) if state.get("video") else None, "multi_share": _multi_on(state), "multi_ok": state.get("multi_ok", True), "watch_ok": state.get("watch_ok", True), "pens": dict(state.get("pen") or {})})
    if switching:
        for i, p in list(state["peers"].items()):
            if i != pid: await _send(p["ws"], {"type": "sfu", "on": True})
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
            if room and room.ended_at is not None and (room.options or {}).get("pmi"):
                room.ended_at = None; await db.commit()          # a personal room is permanent: one closed by an older version opens again
            if room:
                host_id, ended, access, passcode, waiting_room, room_options = room.host_id, room.ended_at is not None, room.access, room.passcode, room.waiting_room, dict(room.options or {})
                from app.services import virtual_room as vr
                vr_meeting = (room_options or {}).get("virtual_room", False) is True                          # the tick box in the meeting setup
                host_user = await db.get(User, host_id)
                vr_allowed = await vr.allowed(db, host_user)                                # the service and the host's account allow it
                from app.services import entitlements as ent
                host_lim = await ent.limits(db, host_user)                                  # plan limits of whoever hosts: recording, meeting length, open room
                if not host_lim["open_room"]: room_options["open_room"] = False             # an open room only works for the administrator and paid hosts
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
        left = await ent.minutes_left(db, host_user) if code not in HUB else None
        if left is not None and left <= 0:
            await _send(ws, {"type": "error", "message": "The host has used all of this month's meeting hours. Ask them to upgrade their plan or contact an administrator."}); await ws.close(); return
        if left is not None: host_lim = {**host_lim, "meeting_minutes": min(host_lim["meeting_minutes"] or left, left)}     # the meeting cannot run past the hours left this month
        state = HUB.setdefault(code, {"host_email": host_user.email, "max_people": host_lim.get("max_participants") or 0, "started": time.time(), "limit": host_lim["meeting_minutes"], "rec_ok": bool(host_lim["recording"]), "peers": {}, "waiting": {}, "recording": False, "groups": None, "vroom": vr_meeting, "vroom_allowed": vr_allowed,
                                      "policy": {"audio": room_options.get("participants_can_unmute", True) is not False, "video": room_options.get("participants_can_video", True) is not False}})
        state.update(cloud_ok=bool(host_lim.get("cloud_recording", True)), max_people=host_lim.get("max_participants") or 0, multi_ok=bool(host_lim.get("multi_share", True)), watch_ok=bool(host_lim.get("watch_together", True)), rec_ok=bool(host_lim["recording"]))      # the host's plan as it is now: an upgrade or a lapse applies to the next person who joins
        if state.get("limit") and not state.get("timer"): state["timer"] = asyncio.create_task(_meeting_clock(code, state))
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
        if state.get("locked") and not is_host and not cohost_join:
            await _send(ws, {"type": "error", "code": "locked", "message": "The host has locked this meeting, so nobody new can join right now."}); pid = None; await ws.close(); return
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
            elif t == "rename":     # a person changes the name others see
                new = " ".join(str(msg.get("name") or "").split())[:60]
                if new:
                    name = new; state["peers"][pid]["name"] = new
                    for _i, _p in list(state["peers"].items()): await _send(_p["ws"], {"type": "renamed", "id": pid, "name": new})
                    await _roster_to_hosts(state)
            elif t in ("sfu-push", "sfu-pull", "sfu-answer") and state.get("sfu"): await _sfu_op(state, pid, msg)
            elif t == "talk" and state.get("sfu"):
                state["peers"][pid]["spoke"] = time.time(); await _stage_update(state)
            elif t == "state":      # mic / camera / screen-share indicators
                me = state["peers"][pid]; mic, cam = bool(msg.get("mic")), bool(msg.get("cam")); want_screen = bool(msg.get("screen"))
                rival = next((p for i, p in state["peers"].items() if i != pid and p.get("screen") and p.get("group") == me.get("group")), None) if want_screen and not me.get("screen") and not _multi_on(state) else None
                if rival:                                   # when the host has switched several shares off, one person shares at a time: the second one waits until the first stops
                    await _send(ws, {"type": "share-denied", "by": rival.get("name") or "Someone"}); want_screen = False
                if me.get("screen") and not want_screen: await _pen_clear(state, pid, code)     # sharing stopped: the pen goes back
                me["screen"] = want_screen
                if state.get("sfu"): asyncio.create_task(_stage_update(state))
                if _rank(me) == 0:                          # the host's rules: a participant cannot switch on what is not allowed
                    if mic and not state["policy"]["audio"]: mic = False; await _send(ws, {"type": "force", "mic": False, "reason": "policy"})
                    if cam and not state["policy"]["video"]: cam = False; await _send(ws, {"type": "force", "cam": False, "reason": "policy"})
                await _to_view(state, me.get("group"), {"type": "state", "id": pid, "mic": mic, "cam": cam, "screen": want_screen}, skip=pid)
            elif t == "react":                       # an emoji that floats up on everyone's screen
                me = state["peers"][pid]; now = time.time(); emoji = str(msg.get("emoji") or "")[:8]
                if emoji in REACTIONS and now - me.get("last_react", 0) > 0.12:
                    me["last_react"] = now; await _to_view(state, me.get("group"), {"type": "react", "id": pid, "name": me["name"], "emoji": emoji})
            elif t == "hand":                        # raise or lower a hand
                me = state["peers"][pid]; me["hand"] = bool(msg.get("up"))
                await _to_view(state, me.get("group"), {"type": "hand", "id": pid, "name": me["name"], "up": me["hand"]}, skip=pid)
            elif t in ("pen_give", "pen_take", "pen_ask", "pointer", "draw", "draw_clear") and state.get("multi_ok", True):     # pointer and pen on someone's shared screen (a paid-plan facility)
                me = state["peers"][pid]; sid = pid if t in ("pen_give", "pen_take") else str(msg.get("sharer") or "")
                sh = state["peers"].get(sid); pens = state.setdefault("pen", {})
                if not sh or not sh.get("screen") or sh.get("group") != me.get("group"): pass
                elif t == "pen_give":
                    to = str(msg.get("to") or ""); tp = state["peers"].get(to)
                    if tp and to != pid and tp.get("group") == me.get("group"):
                        pens[pid] = to; await _to_view(state, me.get("group"), {"type": "pen", "sharer": pid, "holder": to, "name": tp["name"]})
                elif t == "pen_take": await _pen_clear(state, pid, code)
                elif t == "pen_ask":
                    if sid != pid: await _send(sh["ws"], {"type": "pen_ask", "id": pid, "name": me["name"]})
                elif sid == pid or pens.get(sid) == pid:                  # only the sharer, or the person holding the pen, may point or draw
                    now = time.time()
                    if t == "pointer":
                        if now - me.get("_pt", 0) >= 0.03:
                            me["_pt"] = now; x, y = msg.get("x"), msg.get("y")
                            ok = isinstance(x, (int, float)) and isinstance(y, (int, float))
                            await _to_view(state, me.get("group"), {"type": "pointer", "sharer": sid, "by": pid, "name": me["name"], "x": max(0, min(1, x)) if ok else None, "y": max(0, min(1, y)) if ok else None}, skip=pid)
                    elif t == "draw":
                        pts = [[max(0.0, min(1.0, float(a))), max(0.0, min(1.0, float(b)))] for a, b in (msg.get("pts") or [])[:60] if isinstance(a, (int, float)) and isinstance(b, (int, float))]
                        if pts: await _to_view(state, me.get("group"), {"type": "draw", "sharer": sid, "by": pid, "sid": str(msg.get("sid") or "")[:24], "pts": pts}, skip=pid)
                    else: await _to_view(state, me.get("group"), {"type": "draw_clear", "sharer": sid, "by": pid}, skip=pid)
            elif t == "video" and not state.get("watch_ok", True):
                await _send(ws, {"type": "video-error", "message": "Watching a video or document together is not included in the host's plan (Basic). Upgrade to Standard or Business."})
            elif t == "video":                       # watch a YouTube video together: the starter (or a host) loads, plays, pauses and skips for everyone
                me = state["peers"][pid]; op = msg.get("op"); cur = state.get("video"); vid = str(msg.get("vid") or "")
                if op == "web" and (not cur or cur["by_id"] == pid or _rank(me) >= 1):                  # a cloud document (Google Docs, Sheets, Slides, Drive, Microsoft 365, ...) shown to everyone
                    d = _doc_url(str(msg.get("url") or ""))
                    if not d: await _send(ws, {"type": "video-error", "message": "That link cannot be shown inside the meeting. Use a share link from Google Docs, Sheets, Slides or Drive, Microsoft 365 / OneDrive / SharePoint, Dropbox, Notion, Canva, Figma or Miro, and make sure it is open to anyone with the link."})
                    else:
                        state["video"] = cur = {"kind": "web", "url": d[0], "label": d[1], "by": me["name"], "by_id": pid, "playing": False, "t": 0.0, "at": time.time()}
                        await _broadcast(code, {"type": "video", **_video_view(cur)})
                elif op == "load" and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) and (not cur or cur["by_id"] == pid or _rank(me) >= 1):
                    state["video"] = cur = {"kind": "yt", "vid": vid, "by": me["name"], "by_id": pid, "playing": True, "t": 0.0, "at": time.time()}
                    await _broadcast(code, {"type": "video", **_video_view(cur)})
                elif cur and op in ("play", "pause", "seek", "stop") and (cur["by_id"] == pid or _rank(me) >= 1):
                    if op == "stop":
                        state["video"] = None; await _broadcast(code, {"type": "video", "stopped": True, "by": me["name"]})
                    else:
                        try: tt = max(0.0, min(float(msg.get("t") or 0), 86400.0))
                        except (TypeError, ValueError): tt = 0.0
                        cur["t"] = tt; cur["at"] = time.time()
                        if op != "seek": cur["playing"] = (op == "play")
                        await _broadcast(code, {"type": "video", **_video_view(cur)}, skip=pid)
            elif t == "captions_want":               # captions run while at least one person wants to read them
                want = state.setdefault("captions_want", set()); before = bool(want)
                (want.add if msg.get("on") else want.discard)(pid)
                if before != bool(want): await _broadcast(code, {"type": "captions", "on": bool(want)})
            elif t == "caption" and state.get("captions_want"):       # what a person said, written by their own browser
                me = state["peers"][pid]; text = str(msg.get("text") or "").strip()[:400]
                if text: await _to_view(state, me.get("group"), {"type": "caption", "id": pid, "name": me["name"], "text": text, "final": bool(msg.get("final"))}, skip=pid)
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
            elif _rank(state["peers"][pid]) == 2 and t == "record" and msg.get("on") and not state.get("rec_ok", True):
                await _send(ws, {"type": "notice", "kind": "record", "message": "Recording is not allowed for this account. Ask an administrator to allow recording for you."})
            elif _rank(state["peers"][pid]) == 2 and t == "record":
                state["recording"] = bool(msg.get("on")); await _broadcast(code, {"type": "recording", "on": state["recording"]})
            elif _rank(state["peers"][pid]) >= 1 and t in ("kick", "force", "ask", "mute_all", "policy", "role", "vroom", "tshape", "lock", "hidepics", "multishare"):
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
                elif t == "lock":                           # nobody new can join while the meeting is locked
                    state["locked"] = bool(msg.get("on")); await _broadcast(code, {"type": "locked", "on": state["locked"], "by": me["name"]})
                elif t == "multishare":                     # allow several people to share at the same time (shown side by side)
                    if msg.get("on") and not state.get("multi_ok", True): await _send(ws, {"type": "plan-limit", "message": "Several people sharing at once is not included in the host's plan (Basic). Upgrade to Standard or Business."})
                    else: state["multi_share"] = bool(msg.get("on")); await _broadcast(code, {"type": "multishare", "on": _multi_on(state), "by": me["name"]})
                elif t == "hidepics":                       # no profile letters or pictures on tiles without video
                    state["hide_pics"] = bool(msg.get("on")); await _broadcast(code, {"type": "hidepics", "on": state["hide_pics"], "by": me["name"]})
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
                    if r and not (r.options or {}).get("open_room") and not (r.options or {}).get("pmi"):               # an open room is never closed for good: everyone leaves, the link keeps working
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
                for _s, _h in list((state.get("pen") or {}).items()):         # a leaving sharer or pen holder ends that pen
                    if _s == pid or _h == pid: await _pen_clear(state, _s, code)
                _cw = state.get("captions_want")
                if _cw and pid in _cw:
                    _cw.discard(pid)
                    if not _cw: await _broadcast(code, {"type": "captions", "on": False})
                await _to_view(state, gone.get("group") if gone else None, {"type": "peer-left", "id": pid})
                await _roster_to_hosts(state)
                if state.get("sfu"): await _stage_update(state)
            if not state["peers"] and not state["waiting"]:
                task = (state.get("groups") or {}).get("task")
                if task: task.cancel()
                if state.get("timer") and not state.get("ending"): state["timer"].cancel()
                if state.get("stage_task"): state["stage_task"].cancel()
                HUB.pop(code, None)
                if state.get("host_email"):
                    try:
                        from app.services import entitlements as _ent
                        async with SessionLocal() as _db: await _ent.add_meeting_minutes(_db, state["host_email"], (time.time() - state["started"]) / 60)     # counts towards the host's monthly hours
                    except Exception: log.exception("Could not count meeting minutes")

async def _meeting_clock(code: str, state: dict) -> None:
    """Basic hosts get meetings of a limited length: everyone is told 10 minutes before the end (like Zoom), and the meeting then closes."""
    from app.services.entitlements import WARN_MINUTES
    end = state["started"] + state["limit"] * 60
    try:
        warn = end - WARN_MINUTES * 60
        if warn > time.time(): await asyncio.sleep(warn - time.time())
        left = max(0, round((end - time.time()) / 60))
        await _broadcast(code, {"type": "notice", "kind": "ending", "ends_in": max(0, int(end - time.time())), "minutes": left, "message": f"This meeting will end in {left} minute{'s' if left != 1 else ''} because the host's plan allows {state['limit']} minute{'s' if state['limit'] != 1 else ''}. The host can start a new meeting, or upgrade the plan for longer meetings."})
        if end > time.time(): await asyncio.sleep(end - time.time())
        state["ending"] = True                          # from here the room's own shutdown must not cancel this task half way through
        await _broadcast(code, {"type": "ended", "reason": "limit"})
        async with SessionLocal() as db:
            room = (await db.execute(select(Room).where(Room.code == code))).scalar_one_or_none()
            if room: await end_room(db, room, False)
    except asyncio.CancelledError:
        raise

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

@router.post("/rooms/{code}/rename")
async def rename_meeting(code: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """The host changes the meeting's name. Everyone in the room sees the new name straight away."""
    room = await _host_room_any(db, code, user)
    title = " ".join(str((payload or {}).get("title") or "").split())[:200]
    if not title: raise HTTPException(400, "Type a name for the meeting.")
    room.title = title
    if room.meeting_id:
        m = await db.get(Meeting, room.meeting_id)
        if m: m.title = title
    await db.commit()
    if code in HUB: await _broadcast(code, {"type": "title", "title": title})
    return {"ok": True, "title": title}

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
                         request: Request = None, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    if not consent_acknowledged: raise HTTPException(400, "Confirm that participants were told the meeting was recorded.")
    room = await _host_room(db, code, user)
    from app.services import entitlements as ent
    lim = await ent.limits(db, user)
    if not lim["recording"]: raise HTTPException(403, "Recording is not included in your plan. Ask an administrator to allow recording for you.")
    if cloud and not lim.get("cloud_recording", True): cloud = False          # Basic: the recording stays with the host, saved on their own computer
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
        try: await ent.check_storage(db, user, size)
        except HTTPException:
            audio_path.unlink(missing_ok=True); keep.unlink(missing_ok=True); raise
        try: placed = await storage.store_file(keep, user, rid, has_video)
        except Exception as exc:
            log.exception("Could not store recording")
            audio_path.unlink(missing_ok=True); keep.unlink(missing_ok=True)
            raise HTTPException(502, "The recording could not be saved to cloud storage: " + str(exc)[:160] + " Check Admin Console > Recording storage and press Connection test. Your own computer's copy is not affected.")
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
        note += " To get a transcript, an administrator must add a transcription model in Admin Console."
    db.add(AuditLog(actor=user.email, action="room.recording.saved", resource_type="room", safe_metadata={"bytes": size, "video": has_video}))
    await db.commit()
    if cloud:
        emailed = bool(_mail_app_sender())
        if emailed:
            asyncio.create_task(_email_recording_link(user.email, user.display_name or "", room.title, rid, has_video, expires, _public_base(request)))
            note += " An email with a download link is on its way to you."
        else: note += " (Email is not set up in Admin Console, so no download link was emailed.)"
    await ent.bump(db, user.email, "recordings", 1)
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

def _mail_app_sender():
    from app.services import signup
    return signup.app_sender()

def _public_base(request: Request | None) -> str:
    """The web address people use to reach this app, for links in emails."""
    o = (settings.frontend_origin or "").rstrip("/")
    if o and not o.startswith(("http://localhost", "http://127.")): return o
    return str(request.base_url).rstrip("/") if request else o

def _dl_sig(rid: str, exp: int) -> str:
    return hmac.new(settings.local_auth_secret.encode(), f"recording-download:{rid}:{exp}".encode(), "sha256").hexdigest()[:40]

def recording_download_url(base: str, rid: str, expires_at: datetime | None) -> tuple[str, datetime]:
    """A link that downloads one recording without signing in. It stops working after 7 days, or sooner when the cloud copy expires."""
    end = datetime.now(timezone.utc) + timedelta(days=7)
    if expires_at is not None:
        e = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        end = min(end, e)
    exp = int(end.timestamp())
    return f"{base}/api/v1/recordings/{rid}/download?exp={exp}&sig={_dl_sig(rid, exp)}", end

async def _email_recording_link(to: str, name: str, title: str, rid: str, has_video: bool, expires_at, base: str) -> None:
    from app.integrations import mail
    acct = _mail_app_sender()
    if not acct: return
    url, end = recording_download_url(base, rid, expires_at)
    kind = "video" if has_video else "audio"
    body = (f"Hi {name or 'there'},\n\nYour {kind} recording of \"{title}\" has been saved to the cloud and is ready.\n\n"
            f"Download it here (no sign-in needed, so keep this email private):\n{url}\n\n"
            f"The link works until {end.strftime('%d %b %Y')}. You can also find the recording under Meetings > Recordings in iSift.\n\n— iSift")
    try: await mail.send(acct, [to], f"Your recording is ready: {title}", body)
    except Exception: log.exception("Could not email the recording link")

async def _serve_recording(db, row, disposition: str):
    rec = row[0]; fname = f"{row[1].title[:40] or 'meeting'}"; rid = rec.id
    if rec.storage == "r2":
        from app.services import storage
        try:
            obj = storage.client().get_object(Bucket=settings.r2_bucket, Key=rec.object_key)
        except Exception: raise HTTPException(502, "Cloud storage could not be reached. Check Admin Console > Recording storage.")
        ext = ".mp4" if rec.mimetype == "video/mp4" else ".webm"
        return StreamingResponse(obj["Body"].iter_chunks(1024 * 1024), media_type=rec.mimetype or "video/webm", headers={"Content-Disposition": f'{disposition}; filename="{fname}{ext}"', "Content-Length": str(obj["ContentLength"])})
    if rec.storage == "database":
        blob = (await db.execute(select(RoomRecording.data).where(RoomRecording.id == rid))).scalar_one_or_none()
        if not blob: raise HTTPException(410, "This recording is no longer stored.")
        return Response(bytes(blob), media_type=rec.mimetype or "video/webm", headers={"Content-Disposition": f'{disposition}; filename="{fname}.webm"'})
    found = resolve_recording(rec.path, rec.id)
    if not found: raise HTTPException(410, "The recording file is no longer in the recordings folder. If you moved the app, copy its docs/data/audio folder across too.")
    return FileResponse(found, media_type="video/webm" if rec.has_video else "audio/webm", filename=f"{fname}.webm", content_disposition_type=disposition)

@router.get("/recordings/{rid}/download")
async def recording_download(rid: str, exp: int, sig: str, db: AsyncSession = Depends(get_db)):
    """The link in the 'recording is ready' email: the signature proves the host was sent it, and it expires."""
    if exp < time.time() or not hmac.compare_digest(sig, _dl_sig(rid, exp)): raise HTTPException(403, "This download link is not valid or has expired. Sign in to iSift and open Meetings > Recordings.")
    row = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(RoomRecording.id == rid))).first()
    if not row: raise HTTPException(404, "Recording not found")
    return await _serve_recording(db, row, "attachment")

@router.get("/recordings/{rid}/file")
async def recording_file(rid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(RoomRecording, Room).join(Room, Room.id == RoomRecording.room_id).where(RoomRecording.id == rid))).first()
    if not row or row[1].host_id != user.id: raise HTTPException(404, "Recording not found")
    return await _serve_recording(db, row, "inline")

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
