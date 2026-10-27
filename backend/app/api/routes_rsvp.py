"""Replying to a meeting invitation (no account needed) and the host's view of the replies."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.models import User, Meeting, AuditLog
from app.services import rsvp, calendar_sync as cal

router = APIRouter(prefix="/api/v1", tags=["rsvp"])

def _aware(d: datetime) -> datetime: return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

async def _from_token(db: AsyncSession, token: str):
    t = rsvp.read_token(token)
    if not t: raise HTTPException(404, "This reply link is not valid.")
    m = await db.get(Meeting, t[0])
    if not m or m.status == "cancelled": raise HTTPException(404, "This meeting was cancelled or no longer exists.")
    return m, t[1]

@router.get("/rsvp/{token}")
async def rsvp_info(token: str, db: AsyncSession = Depends(get_db)):
    m, email = await _from_token(db, token)
    host = await db.get(User, m.owner_id); v = await rsvp.load(db, m.id)
    return {"title": m.title, "start_at": _aware(m.start_at).isoformat(), "end_at": _aware(m.end_at).isoformat(), "timezone": m.timezone, "host": (host.display_name or host.email) if host else "",
            "email": email, "join_url": m.join_url, "agenda": m.agenda or "", "answer": v["responses"].get(email),
            "calendar": rsvp.calendar_links(m.title, m.start_at, m.end_at, m.join_url, m.agenda or "")}

@router.post("/rsvp/{token}")
async def rsvp_answer(token: str, payload: dict, db: AsyncSession = Depends(get_db)):
    m, email = await _from_token(db, token)
    status = str(payload.get("status") or "")
    if status not in rsvp.STATUSES: raise HTTPException(422, "Choose Accept, Maybe, Decline or suggest another time.")
    proposed = ""
    if status == "proposed":
        try: p = datetime.fromisoformat(str(payload.get("proposed_start") or "").replace("Z", "+00:00"))
        except ValueError: raise HTTPException(422, "Choose the day and time you suggest.")
        if p.tzinfo is None: p = p.replace(tzinfo=timezone.utc)
        if p < datetime.now(timezone.utc): raise HTTPException(422, "Suggest a time in the future.")
        proposed = p.astimezone(timezone.utc).isoformat()
    note = str(payload.get("note") or "").strip()[:500]
    await rsvp.record(db, m.id, email, status, proposed, note)
    host = await db.get(User, m.owner_id)
    if host:
        shown = ""
        if proposed:
            tz = await cal.user_timezone(db); shown = datetime.fromisoformat(proposed).astimezone(tz).strftime("%A %d %B %Y, %H:%M") + f" ({tz})"
        await rsvp.tell_host(db, m, host, email, status, shown, note, str(await cal.user_timezone(db)))
    db.add(AuditLog(actor=email, action="meeting.rsvp", resource_type="meeting", safe_metadata={"status": status})); await db.commit()
    msg = {"accepted": "Thanks. You are going, and the host has been told.", "tentative": "Thanks. The host knows you might come.", "declined": "Thanks. The host knows you cannot come.",
           "proposed": "Thanks. Your suggested time was sent to the host, who can accept it."}[status]
    return {"message": msg, "status": status}

# ---- the host's side ----

async def _mine(db: AsyncSession, user: User, meeting_id: str) -> Meeting:
    m = await db.get(Meeting, meeting_id)
    if not m or m.owner_id != user.id: raise HTTPException(404, "Meeting not found")
    return m

@router.get("/meetings/{meeting_id}/responses")
async def responses(meeting_id: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    from app.api.routes_connections import _room_for
    m = await _mine(db, user, meeting_id); v = await rsvp.load(db, m.id); room = await _room_for(db, m)
    invited = sorted(set(v["invited"]) | set(((room.options or {}).get("invitees") or []) if room else []))
    rows = [{"email": e, **(v["responses"].get(e) or {"status": "waiting"})} for e in invited]
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("accepted", "tentative", "declined", "proposed", "waiting")}
    return {"responses": rows, "counts": counts}

@router.post("/meetings/{meeting_id}/accept-proposal")
async def accept_proposal(meeting_id: str, payload: dict, request: Request, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Move the meeting to the time one person suggested and send everyone the updated invitation."""
    from app.api.routes_connections import _room_for
    from app.integrations import mail as mailer
    from app.services.invites import build_ics
    m = await _mine(db, user, meeting_id); email = str(payload.get("email") or "").lower()
    v = await rsvp.load(db, m.id); r = v["responses"].get(email)
    if not r or r.get("status") != "proposed" or not r.get("proposed_start"): raise HTTPException(404, "That person has no suggested time.")
    dur = _aware(m.end_at) - _aware(m.start_at)
    m.start_at = datetime.fromisoformat(r["proposed_start"]); m.end_at = m.start_at + dur
    room = await _room_for(db, m)
    if room and room.ended_at is not None and not (room.options or {}).get("pmi"): room.ended_at = None
    await db.commit(); await rsvp.reset(db, m.id)
    invited = sorted(set(v["invited"]) | set(((room.options or {}).get("invitees") or []) if room else []))
    note = " The meeting time was changed."
    acct = await cal.get_mail(db, user.id)
    if invited and acct:
        tz = await cal.user_timezone(db)
        try:
            body = f"{user.display_name or user.email} moved the meeting: {m.title}\nNew time: {_aware(m.start_at).astimezone(tz).strftime('%A %d %B %Y, %H:%M')} ({tz})\n" + (f"Join: {m.join_url}\n" if m.join_url else "")
            ics = build_ics(m.id, m.title, _aware(m.start_at), _aware(m.end_at), acct["address"], invited, m.join_url, m.agenda or "", sequence=int(datetime.now(timezone.utc).timestamp()))
            await rsvp.send_each(acct, invited, f"Updated: {m.title}", body, m, rsvp.public_base(request), m.join_url, ics, m.agenda or "")
            note += f" Updated invitations were sent to {len(invited)}."
        except mailer.MailError as exc: note += f" They could not be emailed: {exc}"
    elif invited: note += " Updated invitations were not sent: connect your mail account on the Connections page first."
    db.add(AuditLog(actor=user.email, action="meeting.accept_proposal", resource_type="meeting", safe_metadata={})); await db.commit()
    return {"message": note.strip(), "start_at": _aware(m.start_at).isoformat()}
