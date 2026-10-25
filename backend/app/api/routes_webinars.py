"""Webinars: the host's screens (set up, registrants, polls, reports) and the public registration page.

The live part (view-only attendees, Q&A and poll messages) runs inside the meeting room, see routes_rooms.py.
The module can be switched off in Admin Console (Customers > Modules) and per plan; the host's plan must also include webinars.
"""
import secrets, time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal
from app.models import User, Webinar, WebinarRegistrant, WebinarQuestion, WebinarPoll, AuditLog, Room
from app.services import webinars as wb
from app.services.invites import EMAIL

MODULE = "webinars"

async def _module_on(db: AsyncSession, user: User | None = None):
    from app.api.routes_modules import disabled
    from app.services import entitlements as ent
    off = set(await disabled(db)) | (set(await ent.modules_off(db, user)) if user else set())
    if MODULE in off or "meetings" in off: raise HTTPException(403, "Webinars are switched off. An administrator can turn them on under Customers > Modules.")

async def _host(user: User = Depends(principal), db: AsyncSession = Depends(get_db)) -> User:
    from app.services import entitlements as ent
    await _module_on(db, user)
    if not (await ent.limits(db, user)).get("webinars"): raise HTTPException(403, "Webinars are not included in your plan. Upgrade your plan, or ask an administrator to allow them for you.")
    return user

router = APIRouter(prefix="/api/v1/webinars", tags=["webinars"])
pub = APIRouter(prefix="/api/v1/webinar-public", tags=["webinars"])

def _base(request: Request, payload: dict | None = None) -> str:
    from app.api.routes_rooms import _public_base
    b = str((payload or {}).get("base_url") or "")
    if b.startswith(("http://", "https://")):
        from urllib.parse import urlsplit
        p = urlsplit(b); return f"{p.scheme}://{p.netloc}"
    return _public_base(request).rstrip("/")

def _when(v) -> datetime:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError: raise HTTPException(422, "Choose the date and time of the webinar.")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

async def _mine(db: AsyncSession, user: User, wid: str) -> Webinar:
    w = await db.get(Webinar, wid)
    if not w or w.host_id != user.id: raise HTTPException(404, "That webinar was not found.")
    return w

def _live(w: Webinar) -> dict:
    from app.api.routes_rooms import HUB
    st = HUB.get(w.room_code)
    if not st: return {"live": False, "watching": 0, "on_air": False}
    return {"live": True, "on_air": bool(st.get("web_live")), "watching": sum(1 for p in st["peers"].values() if p.get("attendee") or p.get("promoted"))}

def _summary(w: Webinar, counts: dict) -> dict:
    c = counts.get(w.id, {})
    return {"id": w.id, "title": w.title, "start_at": wb.aware(w.start_at).isoformat(), "minutes": w.minutes, "tz": w.tz, "status": w.status, "room_code": w.room_code,
            "registered": c.get("approved", 0) + c.get("pending", 0), "pending": c.get("pending", 0), "attended": c.get("attended", 0), **_live(w)}

async def _counts(db: AsyncSession, ids: list[str]) -> dict:
    out: dict = {}
    if not ids: return out
    regs = (await db.execute(select(WebinarRegistrant.webinar_id, WebinarRegistrant.status, WebinarRegistrant.joins).where(WebinarRegistrant.webinar_id.in_(ids)))).all()
    for wid, status, joins in regs:
        d = out.setdefault(wid, {}); d[status] = d.get(status, 0) + 1
        if joins: d["attended"] = d.get("attended", 0) + 1
    return out

@router.get("")
async def list_mine(user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Webinar).where(Webinar.host_id == user.id).order_by(Webinar.start_at.desc()).limit(200))).scalars().all()
    counts = await _counts(db, [w.id for w in rows])
    return {"webinars": [_summary(w, counts) for w in rows], "max_attendees": int(settings.webinar_max_attendees or 500)}

def _detail(w: Webinar, counts: dict) -> dict:
    return {**_summary(w, counts), "description": w.description, "settings": {k: v for k, v in (w.settings or {}).items() if k != "base"}, "page": wb.page_link(w),
            "panelists": [{"email": p["email"], "name": p.get("name", ""), "link": wb.panelist_link(w, p)} for p in (w.panelists or [])]}

async def _make_room(db: AsyncSession, user: User, w_title: str, base: str, start: datetime, minutes: int):
    from app.api.routes_rooms import make_room
    return await make_room(db, user, w_title, base + "/", start=start, minutes=minutes, access="open", waiting_room=False, options={"mute_on_entry": True})

@router.post("")
async def create(payload: dict, request: Request, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    title = str(payload.get("title") or "").strip()[:200]
    if len(title) < 3: raise HTTPException(422, "Give the webinar a title of at least 3 letters.")
    start = _when(payload.get("start_at"))
    if start < datetime.now(timezone.utc) - timedelta(hours=1): raise HTTPException(422, "Choose a date and time in the future.")
    try: minutes = max(10, min(int(payload.get("minutes") or 60), 600))
    except (TypeError, ValueError): minutes = 60
    base = _base(request, payload)
    s = wb.clean_settings({**(payload.get("settings") or {}), "base": base})
    room, meeting = await _make_room(db, user, title, base, start, minutes)
    w = Webinar(host_id=user.id, room_code=room.code, title=title, description=str(payload.get("description") or "").strip()[:4000], start_at=start, minutes=minutes,
                tz=str(payload.get("tz") or "Australia/Sydney")[:60], settings=s, panelists=wb.clean_panelists(payload.get("panelists")), reminder_state={})
    db.add(w); db.add(AuditLog(actor=user.email, action="webinar.create", resource_type="webinar", safe_metadata={"title": title})); await db.commit()
    for p in w.panelists: await wb.tell_panelist(w, p, user)
    return {**_detail(w, {}), "message": "Webinar created."}

@router.get("/{wid}")
async def detail(wid: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid)
    return {**_detail(w, await _counts(db, [w.id])), "report": await wb.report(db, w)}

@router.patch("/{wid}")
async def update(wid: str, payload: dict, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid)
    if w.status != "scheduled": raise HTTPException(409, "This webinar has already ended or was cancelled.")
    before = (wb.aware(w.start_at), w.title); old_panel = {p["email"] for p in (w.panelists or [])}
    if "title" in payload:
        t = str(payload["title"] or "").strip()[:200]
        if len(t) < 3: raise HTTPException(422, "Give the webinar a title of at least 3 letters.")
        w.title = t
    if "description" in payload: w.description = str(payload["description"] or "").strip()[:4000]
    if "start_at" in payload: w.start_at = _when(payload["start_at"])
    if "minutes" in payload:
        try: w.minutes = max(10, min(int(payload["minutes"]), 600))
        except (TypeError, ValueError): pass
    if "tz" in payload: w.tz = str(payload["tz"] or w.tz)[:60]
    if "settings" in payload: w.settings = wb.clean_settings(payload["settings"], w.settings)
    if "panelists" in payload: w.panelists = wb.clean_panelists(payload["panelists"], w.panelists)
    if (wb.aware(w.start_at), w.title) != before:
        w.reminder_state = {}                                                # reminders are due again for the new time
        room = (await db.execute(select(Room).where(Room.code == w.room_code))).scalar_one_or_none()
        if room: room.title = w.title
    await db.commit()
    if wb.aware(w.start_at) != before[0]:
        regs = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.status == "approved"))).scalars().all()
        for r in regs: await wb.send_mail(r.email, f"New time: {w.title}", f"Hi {r.name or 'there'},\n\nThe time of {w.title} has changed.\n\nNew time: {wb.when_text(w)}\nYour personal link (unchanged): {wb.join_link(w, r)}", wb.ics_for(w, r.email, wb.join_link(w, r)))
    for p in w.panelists:
        if p["email"] not in old_panel: await wb.tell_panelist(w, p, user)
    return {**_detail(w, await _counts(db, [w.id])), "message": "Saved."}

@router.delete("/{wid}")
async def cancel(wid: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid)
    if w.status == "scheduled":
        w.status = "cancelled"; w.ended_at = datetime.now(timezone.utc)
        regs = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.status.in_(("approved", "pending"))))).scalars().all()
        db.add(AuditLog(actor=user.email, action="webinar.cancel", resource_type="webinar", safe_metadata={"title": w.title})); await db.commit()
        for r in regs: await wb.send_mail(r.email, f"Cancelled: {w.title}", f"Hi {r.name or 'there'},\n\n{w.title} ({wb.when_text(w)}) has been cancelled by the host.", wb.ics_for(w, r.email, "", cancel=True))
    return {"ok": True, "message": "The webinar was cancelled and registered people were told."}

# ---- registrants
def _reg_view(r: WebinarRegistrant, w: Webinar) -> dict:
    return {"id": r.id, "name": r.name, "email": r.email, "status": r.status, "source": r.source, "registered": wb._row_dt(r.created_at), "answers": {k: v for k, v in (r.answers or {}).items() if not k.startswith("_")},
            "attended": bool(r.joins), "minutes": round((r.seconds or 0) / 60, 1), "link": wb.join_link(w, r)}

@router.get("/{wid}/registrants")
async def registrants(wid: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid)
    rows = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id).order_by(WebinarRegistrant.created_at.desc()).limit(5000))).scalars().all()
    return {"registrants": [_reg_view(r, w) for r in rows], "questions": (w.settings or {}).get("questions", [])}

async def _room_left(db: AsyncSession, w: Webinar) -> int:
    cap = min(int(settings.webinar_max_attendees or 500), int((w.settings or {}).get("capacity") or 0) or 10**9)
    n = (await db.execute(select(func.count()).select_from(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.status.in_(("approved", "pending"))))).scalar() or 0
    return max(0, cap - n)

@router.post("/{wid}/registrants")
async def add_registrants(wid: str, payload: dict, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid)
    if w.status != "scheduled": raise HTTPException(409, "This webinar has already ended or was cancelled.")
    added, skipped = 0, []
    left = await _room_left(db, w)
    for p in (payload.get("people") or [])[:200]:
        email = str((p or {}).get("email") or "").strip().lower()
        if not EMAIL.match(email): skipped.append(email or "(empty)"); continue
        if (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.email == email))).scalar_one_or_none(): skipped.append(email); continue
        if left <= 0: skipped.append(email + " (full)"); continue
        r = WebinarRegistrant(webinar_id=w.id, email=email, name=str((p or {}).get("name") or "").strip()[:200] or email.split("@")[0], status="approved", source="host", token=secrets.token_urlsafe(18), answers={})
        db.add(r); await db.commit(); left -= 1; added += 1
        await wb.tell_registration(db, w, r)
    return {"added": added, "skipped": skipped, "message": f"{added} added and emailed." + (f" Skipped: {', '.join(skipped[:5])}." if skipped else "")}

@router.patch("/{wid}/registrants/{rid}")
async def decide(wid: str, rid: str, payload: dict, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid); r = await db.get(WebinarRegistrant, rid)
    if not r or r.webinar_id != w.id: raise HTTPException(404, "That registration was not found.")
    st = str(payload.get("status") or "")
    if st == "resend":
        if r.status != "approved": raise HTTPException(409, "Only approved registrations get a link.")
        return {"ok": await wb.tell_registration(db, w, r), "message": "The email was sent again."}
    if st not in ("approved", "denied", "cancelled"): raise HTTPException(422, "Choose approve, deny or cancel.")
    if st == "approved" and r.status != "approved" and await _room_left(db, w) <= 0 and r.status != "pending": raise HTTPException(409, "The webinar is full.")
    changed = r.status != st; r.status = st; await db.commit()
    if changed and st in ("approved", "denied"): await wb.tell_decision(db, w, r)
    return {"registrant": _reg_view(r, w), "message": {"approved": "Approved and emailed their link.", "denied": "Declined and told them.", "cancelled": "Registration cancelled."}[st]}

@router.post("/{wid}/registrants/approve-all")
async def approve_all(wid: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid); n = 0
    for r in (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.status == "pending"))).scalars().all():
        r.status = "approved"; await db.commit(); await wb.tell_decision(db, w, r); n += 1
    return {"approved": n, "message": f"{n} approved and emailed."}

# ---- polls (prepared here; opened and closed during the webinar)
def _poll_in(payload: dict) -> dict:
    q = " ".join(str(payload.get("question") or "").split())[:300]
    opts = [" ".join(str(o).split())[:120] for o in (payload.get("options") or []) if str(o).strip()][:10]
    if len(q) < 3 or len(opts) < 2: raise HTTPException(422, "A poll needs a question and at least two answers.")
    return {"question": q, "options": opts, "multi": bool(payload.get("multi"))}

@router.get("/{wid}/polls")
async def polls(wid: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid); _, ps = await wb.snapshot(db, w.id)
    return {"polls": [wb.poll_view(p, "", True) for p in ps]}

@router.post("/{wid}/polls")
async def poll_add(wid: str, payload: dict, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid); _, ps = await wb.snapshot(db, w.id)
    if len(ps) >= 30: raise HTTPException(422, "A webinar can have up to 30 polls.")
    p = WebinarPoll(webinar_id=w.id, position=len(ps), votes={}, **_poll_in(payload)); db.add(p); await db.commit()
    return {"poll": wb.poll_view(p, "", True), "message": "Poll saved."}

@router.patch("/{wid}/polls/{pid}")
async def poll_edit(wid: str, pid: str, payload: dict, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid); p = await db.get(WebinarPoll, pid)
    if not p or p.webinar_id != w.id: raise HTTPException(404, "That poll was not found.")
    if p.status != "draft": raise HTTPException(409, "A poll that has been launched cannot be changed. Add a new one.")
    for k, v in _poll_in(payload).items(): setattr(p, k, v)
    await db.commit(); return {"poll": wb.poll_view(p, "", True), "message": "Poll saved."}

@router.delete("/{wid}/polls/{pid}")
async def poll_del(wid: str, pid: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid); p = await db.get(WebinarPoll, pid)
    if not p or p.webinar_id != w.id: raise HTTPException(404, "That poll was not found.")
    await db.delete(p); await db.commit(); return {"ok": True}

# ---- Q&A, reports, follow-up
@router.get("/{wid}/questions")
async def questions(wid: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid); qs, _ = await wb.snapshot(db, w.id)
    return {"questions": [wb.q_view(q, "", True) for q in qs]}

@router.get("/{wid}/export/{kind}")
async def export(wid: str, kind: str, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    if kind not in ("registrants", "attendance", "questions", "polls"): raise HTTPException(404, "Unknown report.")
    w = await _mine(db, user, wid); name, text = await wb.export(db, w, kind)
    return {"filename": name, "content": "﻿" + text}

@router.post("/{wid}/followup")
async def followup(wid: str, payload: dict, user: User = Depends(_host), db: AsyncSession = Depends(get_db)):
    w = await _mine(db, user, wid)
    if w.status != "ended": raise HTTPException(409, "Follow-up emails can be sent once the webinar has ended.")
    kind = "missed" if payload.get("kind") == "missed" else "attended"
    n = await wb.send_followups(db, w, kind, str(payload.get("subject") or "")[:200], str(payload.get("message") or "")[:4000])
    return {"sent": n, "message": f"{n} email{'s' if n != 1 else ''} sent." if n else "Nobody to email: everyone in that group already has this email, or there is no email account set up in Admin Console."}

# ---------------------------------------------------------------- public registration page (no sign-in)
_REG: dict[str, list[float]] = {}

async def _pub(db: AsyncSession, wid: str) -> Webinar:
    await _module_on(db)
    w = await db.get(Webinar, wid)
    if not w: raise HTTPException(404, "This webinar was not found.")
    return w

@pub.get("/{wid}")
async def public_info(wid: str, db: AsyncSession = Depends(get_db)):
    w = await _pub(db, wid); host = await wb.host_of(db, w); s = w.settings or {}
    left = await _room_left(db, w)
    return {"id": w.id, "title": w.title, "description": w.description, "host": (host.display_name or host.email.split("@")[0]) if host else "", "start_at": wb.aware(w.start_at).isoformat(),
            "minutes": w.minutes, "tz": w.tz, "status": w.status, "registration": bool(s.get("registration", True)), "approval": s.get("approval", "auto"), "questions": s.get("questions", []),
            "full": left <= 0 and bool(s.get("registration", True)), "panelists": [p.get("name") for p in (w.panelists or []) if p.get("name")], "room_code": w.room_code}

@pub.post("/{wid}/register")
async def register(wid: str, payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    w = await _pub(db, wid); s = w.settings or {}
    if w.status != "scheduled": raise HTTPException(409, "Registration is closed for this webinar.")
    if not s.get("registration", True): raise HTTPException(409, "This webinar does not need registration. Just open the link.")
    ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "x")
    now = time.time(); hits = [t for t in _REG.get(ip, []) if now - t < 3600]
    if len(hits) >= 20: raise HTTPException(429, "Too many registrations from this network. Please try again later.")
    _REG[ip] = hits + [now]
    email = str(payload.get("email") or "").strip().lower(); name = " ".join(str(payload.get("name") or "").split())[:200]
    if not EMAIL.match(email): raise HTTPException(422, "Enter a valid email address.")
    if len(name) < 2: raise HTTPException(422, "Enter your name.")
    answers = {}
    for q in s.get("questions", []):
        v = " ".join(str((payload.get("answers") or {}).get(q["id"]) or "").split())[:300]
        if q.get("required") and not v: raise HTTPException(422, f"Please answer: {q['label']}")
        if v and q.get("type") == "choice" and v not in q.get("options", []): raise HTTPException(422, f"Choose one of the answers for: {q['label']}")
        if v: answers[q["id"]] = v
    existing = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.email == email))).scalar_one_or_none()
    if existing:
        if existing.status in ("approved", "pending"): await wb.tell_registration(db, w, existing); return {"status": existing.status, "message": "You are already registered. We sent your link again."}
        raise HTTPException(409, "This registration was cancelled or declined. Contact the host.")
    if await _room_left(db, w) <= 0: raise HTTPException(409, "This webinar is full.")
    r = WebinarRegistrant(webinar_id=w.id, email=email, name=name, answers=answers, status="pending" if s.get("approval") == "manual" else "approved", source="self", token=secrets.token_urlsafe(18))
    db.add(r); await db.commit(); await wb.tell_registration(db, w, r)
    return {"status": r.status, "token": r.token if r.status == "approved" else "", "message": "Thank you. The host will review your registration and email you." if r.status == "pending" else "You are registered. We emailed your personal link."}

@pub.get("/{wid}/me")
async def public_me(wid: str, k: str = "", p: str = "", db: AsyncSession = Depends(get_db)):
    w = await _pub(db, wid)
    if p:
        pan = next((x for x in (w.panelists or []) if secrets.compare_digest(x["token"], p)), None)
        if not pan: raise HTTPException(404, "That panelist link is not valid.")
        return {"role": "panelist", "name": pan.get("name") or pan["email"], "room_code": w.room_code, "status": "approved", "webinar_status": w.status}
    r = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.token == k, WebinarRegistrant.webinar_id == w.id))).scalar_one_or_none() if k else None
    if not r: raise HTTPException(404, "That registration link is not valid. Register again to get a new one.")
    return {"role": "attendee", "name": r.name, "email": r.email, "status": r.status, "room_code": w.room_code if r.status == "approved" else "", "webinar_status": w.status}

@pub.post("/{wid}/cancel")
async def public_cancel(wid: str, payload: dict, db: AsyncSession = Depends(get_db)):
    w = await _pub(db, wid); k = str(payload.get("k") or "")
    r = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.token == k, WebinarRegistrant.webinar_id == w.id))).scalar_one_or_none() if k else None
    if not r: raise HTTPException(404, "That registration link is not valid.")
    r.status = "cancelled"; await db.commit(); return {"ok": True, "message": "Your registration was cancelled."}

@pub.get("/{wid}/calendar.ics")
async def public_ics(wid: str, k: str = "", db: AsyncSession = Depends(get_db)):
    w = await _pub(db, wid)
    r = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.token == k, WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.status == "approved"))).scalar_one_or_none() if k else None
    if not r: raise HTTPException(404, "That registration link is not valid.")
    return Response(wb.ics_for(w, r.email, wb.join_link(w, r)), media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="webinar.ics"'})
