"""Booking pages: the scheduling feature of Calendly and Cal.com.

A person publishes a booking page (weekly hours, meeting length, buffers). Anyone with the link, no account needed, picks a free
time and enters a name and email. iSift then creates a built-in video room and a meeting for the host, and the guest gets a
join link plus a private link to cancel or reschedule. Free times are worked out from the host's weekly hours minus
everything already in their iSift calendar (including meetings pulled from Outlook, Google and other calendars).
"""
import re, secrets, time
from urllib.parse import quote
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import principal
from app.integrations import mail as mailer
from app.models import User, Meeting, Room, BookingType, Booking, AuditLog

router = APIRouter(prefix="/api/v1")
EMAIL = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")
DEFAULT_HOURS = {str(d): [["09:00", "17:00"]] for d in range(5)}      # Monday to Friday
_HITS: dict[str, list[float]] = {}

def _aware(d: datetime) -> datetime: return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def _zone(name: str | None, fallback: str = "UTC") -> ZoneInfo:
    try: return ZoneInfo(name or fallback)
    except Exception: return ZoneInfo(fallback)

def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (s or "meeting")[:60]

def _clean_hours(raw) -> dict:
    out = {}
    if not isinstance(raw, dict): raise HTTPException(422, "Weekly hours are not valid.")
    for k, spans in raw.items():
        if str(k) not in {"0", "1", "2", "3", "4", "5", "6"}: continue
        good = []
        for sp in (spans or [])[:6]:
            try:
                a, b = str(sp[0]), str(sp[1]); ha, hb = dtime.fromisoformat(a), dtime.fromisoformat(b)
            except Exception: raise HTTPException(422, "Use times like 09:00 and 17:00.")
            if hb <= ha: raise HTTPException(422, "A day's end time must be after its start time.")
            good.append([ha.strftime("%H:%M"), hb.strftime("%H:%M")])
        if good: out[str(k)] = sorted(good)
    if not out: raise HTTPException(422, "Choose at least one day with available hours.")
    return out

def _num(payload: dict, key: str, lo: int, hi: int, default: int) -> int:
    try: v = int(payload.get(key, default))
    except (TypeError, ValueError): raise HTTPException(422, f"{key.replace('_', ' ').capitalize()} must be a number.")
    if not lo <= v <= hi: raise HTTPException(422, f"{key.replace('_', ' ').capitalize()} must be between {lo} and {hi}.")
    return v

def _type_out(bt: BookingType, base: str = "") -> dict:
    return {"id": bt.id, "slug": bt.slug, "title": bt.title, "description": bt.description, "duration_minutes": bt.duration_minutes, "buffer_minutes": bt.buffer_minutes,
            "min_notice_hours": bt.min_notice_hours, "days_ahead": bt.days_ahead, "timezone": bt.timezone, "availability": bt.availability or {}, "active": bt.active}

async def _unique_slug(db: AsyncSession, want: str, skip_id: str = "") -> str:
    slug, n = want, 1
    while True:
        row = (await db.execute(select(BookingType).where(BookingType.slug == slug))).scalar_one_or_none()
        if not row or row.id == skip_id: return slug
        n += 1; slug = f"{want}-{n}"[:80]

# ---------------- owner: manage booking pages ----------------
@router.get("/booking-types")
async def list_types(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(BookingType).where(BookingType.owner_id == user.id).order_by(BookingType.created_at))).scalars().all()
    return [_type_out(r) for r in rows]

def _apply(bt: BookingType, payload: dict, creating: bool = False) -> None:
    if creating or "title" in payload:
        t = str(payload.get("title") or "").strip()
        if not t: raise HTTPException(422, "Give the booking page a title, for example 30 minute meeting.")
        bt.title = t[:200]
    if "description" in payload: bt.description = str(payload.get("description") or "")[:2000]
    if creating or "duration_minutes" in payload: bt.duration_minutes = _num(payload, "duration_minutes", 5, 480, 30)
    if "buffer_minutes" in payload: bt.buffer_minutes = _num(payload, "buffer_minutes", 0, 240, 0)
    if "min_notice_hours" in payload: bt.min_notice_hours = _num(payload, "min_notice_hours", 0, 24 * 30, 4)
    if "days_ahead" in payload: bt.days_ahead = _num(payload, "days_ahead", 1, 180, 30)
    if "timezone" in payload:
        try: ZoneInfo(str(payload["timezone"]))
        except Exception: raise HTTPException(422, "That time zone is not recognised.")
        bt.timezone = str(payload["timezone"])
    if "availability" in payload: bt.availability = _clean_hours(payload["availability"])
    if "active" in payload: bt.active = bool(payload["active"])

@router.post("/booking-types")
async def create_type(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    if len((await db.execute(select(BookingType).where(BookingType.owner_id == user.id))).scalars().all()) >= 20:
        raise HTTPException(409, "You can have up to 20 booking pages.")
    bt = BookingType(owner_id=user.id, timezone="UTC", availability=dict(DEFAULT_HOURS))
    from app.services import calendar_sync as cal
    bt.timezone = str(await cal.user_timezone(db))
    _apply(bt, payload, creating=True)
    bt.slug = await _unique_slug(db, _slug(str(payload.get("slug") or bt.title)))
    db.add(bt); db.add(AuditLog(actor=user.email, action="booking.type.create", resource_type="booking_type", safe_metadata={"slug": bt.slug}))
    await db.commit(); return _type_out(bt)

@router.patch("/booking-types/{tid}")
async def update_type(tid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    bt = await db.get(BookingType, tid)
    if not bt or bt.owner_id != user.id: raise HTTPException(404, "Booking page not found.")
    _apply(bt, payload)
    if payload.get("slug"): bt.slug = await _unique_slug(db, _slug(str(payload["slug"])), bt.id)
    await db.commit(); return _type_out(bt)

@router.post("/booking-types/{tid}/share-draft")
async def share_draft(tid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Write the email that shares this booking link (Groq when set up, otherwise a template). Nothing is sent."""
    from app.services import groq
    bt = await db.get(BookingType, tid)
    if not bt or bt.owner_id != user.id: raise HTTPException(404, "Booking page not found.")
    link = f"{_base(payload)}#/book/{bt.slug}"
    d, ai, note = await groq.draft(_host_name(user), bt.title, bt.duration_minutes, bt.description or "", str(payload.get("purpose") or ""), str(payload.get("to") or "")[:120], str(payload.get("tone") or "friendly"))
    return {"subject": d["subject"], "body": d["body"].replace(groq.MARK, link), "ai": ai, "note": note, "link": link}

@router.post("/booking-types/{tid}/share")
async def share_type(tid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Email the booking link to up to 20 people from the app email account (or the host's mailbox). Replies go to the host."""
    from app.services.invites import EMAIL
    bt = await db.get(BookingType, tid)
    if not bt or bt.owner_id != user.id: raise HTTPException(404, "Booking page not found.")
    if not bt.active: raise HTTPException(422, "This booking page is paused. Turn it on before sharing it.")
    raw = payload.get("to") or []
    to = [x.strip().lower() for x in (re.split(r"[,;\s]+", raw) if isinstance(raw, str) else raw) if str(x).strip()]
    to = list(dict.fromkeys(to))
    if not to: raise HTTPException(422, "Enter at least one email address.")
    if len(to) > 20: raise HTTPException(422, "You can send to up to 20 people at a time.")
    bad = [x for x in to if not EMAIL.match(x)]
    if bad: raise HTTPException(422, f"This does not look like an email address: {bad[0]}")
    link = f"{_base(payload)}#/book/{bt.slug}"
    note = str(payload.get("message") or "").strip()[:2000]
    host = _host_name(user)
    subject = str(payload.get("subject") or "").strip()[:200] or f"Book a time with {host}"
    if link in note: body = note + "\n\n- sent with iSift"          # the written message already carries the link
    else: body = (note + "\n\n" if note else f"Hello,\n\n{host} would like to meet with you.\n\n") + f"Pick a time that suits you ({bt.duration_minutes} minutes):\n{link}\n\nYou do not need an account. You will get a confirmation with the video link.\n\n- {host}, sent with iSift"
    senders = await _senders(db, user)
    if not senders: raise HTTPException(409, "No email account is set up for sending. Copy the link instead, or ask the administrator to fill in Email sent by the app in Admin settings.")
    failed = []; why = ""; via = {}
    for addr in to:
        for acct in senders:
            try: await mailer.send(acct, [addr], subject, body.replace(link, f"{link}?email={quote(addr, safe='@')}")); via = {"host": acct.get("smtp_host", ""), "from": acct.get("from") or acct.get("address", ""), "login": acct.get("username") or acct.get("address", "")}; break
            except Exception as exc:
                why = str(exc) if isinstance(exc, mailer.MailError) else f"{type(exc).__name__}"
                if acct.get("platform") and "gmail" in (acct.get("smtp_host") or "").lower() and "refused" in why:
                    why += " For Gmail, the SMTP password in Admin settings must be a 16-letter app password (Google Account, Security, 2-Step Verification, App passwords), not the normal Gmail password."
                continue
        else: failed.append(addr)
    db.add(AuditLog(actor=user.email, action="booking.share", resource_type="booking_type", safe_metadata={"count": len(to), "failed": len(failed)})); await db.commit()
    if len(failed) == len(to): raise HTTPException(502, f"The email could not be sent. {why or 'Check the sending account.'} You can still copy the link or use your own email app.")
    return {"sent": [x for x in to if x not in failed], "failed": failed, "link": link, "via": via.get("host", ""), "from": via.get("from", ""), "login": via.get("login", "")}

@router.delete("/booking-types/{tid}")
async def delete_type(tid: str, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    bt = await db.get(BookingType, tid)
    if not bt or bt.owner_id != user.id: raise HTTPException(404, "Booking page not found.")
    await db.delete(bt); await db.commit(); return {"ok": True}

def _booking_out(b: Booking, bt: BookingType | None, base: str = "") -> dict:
    return {"id": b.id, "type_id": b.type_id, "type_title": bt.title if bt else "", "guest_name": b.guest_name, "guest_email": b.guest_email, "guest_note": b.guest_note,
            "start_at": _aware(b.start_at).isoformat(), "end_at": _aware(b.end_at).isoformat(), "status": b.status, "meeting_id": b.meeting_id, "room_code": b.room_code, "token": b.token}

@router.get("/bookings")
async def list_bookings(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(days=14)
    rows = (await db.execute(select(Booking).where(Booking.owner_id == user.id, Booking.start_at >= since).order_by(Booking.start_at))).scalars().all()
    types = {t.id: t for t in (await db.execute(select(BookingType).where(BookingType.owner_id == user.id))).scalars().all()}
    return [_booking_out(b, types.get(b.type_id)) for b in rows]

# ---------------- free times ----------------
async def _busy(db: AsyncSession, owner_id: str, start: datetime, end: datetime, skip_meeting: str = "") -> list[tuple[datetime, datetime]]:
    out = []
    for m in (await db.execute(select(Meeting).where(Meeting.owner_id == owner_id, Meeting.start_at < end, Meeting.end_at > start))).scalars().all():
        if m.status == "cancelled" or m.id == skip_meeting: continue
        a, b = _aware(m.start_at), _aware(m.end_at)
        if b - a >= timedelta(hours=20): continue            # all-day events do not block the day
        out.append((a, b))
    return out

async def free_slots(db: AsyncSession, bt: BookingType, start_day: date, end_day: date, skip_meeting: str = "") -> list[datetime]:
    zone = _zone(bt.timezone); now = datetime.now(timezone.utc)
    earliest = now + timedelta(hours=bt.min_notice_hours); latest = now + timedelta(days=bt.days_ahead)
    first = datetime.combine(start_day, dtime.min, zone).astimezone(timezone.utc); last = datetime.combine(end_day + timedelta(days=1), dtime.min, zone).astimezone(timezone.utc)
    busy = await _busy(db, bt.owner_id, first - timedelta(hours=12), last + timedelta(hours=12), skip_meeting)
    dur, buf = timedelta(minutes=bt.duration_minutes), timedelta(minutes=bt.buffer_minutes)
    out, day = [], start_day
    while day <= end_day:
        for span in (bt.availability or {}).get(str(day.weekday()), []):
            a = datetime.combine(day, dtime.fromisoformat(span[0]), zone).astimezone(timezone.utc)
            b = datetime.combine(day, dtime.fromisoformat(span[1]), zone).astimezone(timezone.utc)
            t = a
            while t + dur <= b:
                if t >= earliest and t <= latest and not any(t - buf < be and t + dur + buf > bs for bs, be in busy): out.append(t)
                t += dur
        day += timedelta(days=1)
    return out

# ---------------- public: the page guests see ----------------
async def _public_type(db: AsyncSession, slug: str) -> tuple[BookingType, User]:
    bt = (await db.execute(select(BookingType).where(BookingType.slug == slug))).scalar_one_or_none()
    owner = await db.get(User, bt.owner_id) if bt else None
    if not bt or not bt.active or not owner or not owner.is_active: raise HTTPException(404, "This booking page is not available.")
    return bt, owner

def _host_name(u: User) -> str: return u.display_name or u.email.split("@")[0]

@router.get("/public/book/{slug}")
async def public_page(slug: str, db: AsyncSession = Depends(get_db)):
    bt, owner = await _public_type(db, slug)
    return {"title": bt.title, "description": bt.description, "duration_minutes": bt.duration_minutes, "host": _host_name(owner), "timezone": bt.timezone, "days_ahead": bt.days_ahead}

@router.get("/public/book/{slug}/slots")
async def public_slots(slug: str, start: str = "", end: str = "", db: AsyncSession = Depends(get_db)):
    bt, _ = await _public_type(db, slug)
    zone = _zone(bt.timezone); today = datetime.now(zone).date()
    try: d0 = date.fromisoformat(start) if start else today; d1 = date.fromisoformat(end) if end else d0 + timedelta(days=bt.days_ahead)
    except ValueError: raise HTTPException(422, "Use dates like 2026-10-20.")
    d0 = max(d0 - timedelta(days=1), today - timedelta(days=1)); d1 = min(d1 + timedelta(days=1), today + timedelta(days=bt.days_ahead + 1))
    if (d1 - d0).days > 70: raise HTTPException(422, "Ask for up to ten weeks at a time.")
    return {"duration_minutes": bt.duration_minutes, "slots": [s.isoformat().replace("+00:00", "Z") for s in await free_slots(db, bt, d0, d1)]}

def _limit(request: Request, key: str, n: int = 12, per: int = 3600) -> None:
    ip = request.client.host if request.client else "?"; k = f"{key}:{ip}"; now = time.time()
    hits = [t for t in _HITS.get(k, []) if now - t < per]
    if len(hits) >= n: raise HTTPException(429, "Too many requests from this device. Try again later.")
    hits.append(now); _HITS[k] = hits

def _parse_start(raw) -> datetime:
    try: d = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError: raise HTTPException(422, "Choose a time from the list.")
    return _aware(d).astimezone(timezone.utc)

def _fmt(d: datetime, tz: str) -> str:
    z = _zone(tz); l = _aware(d).astimezone(z); return l.strftime("%A %d %B %Y, %I:%M %p ") + (l.tzname() or tz)

from app.services.identity import routable as _routable, shown_email, reply_email

def host_email(owner: User) -> str: return reply_email(owner.email)

async def _senders(db: AsyncSession, owner: User) -> list[dict]:
    """Where booking emails are sent from: the app's own email account (Admin settings, Email sent by the app) first, then the host's Commbox mailboxes, then the older single mailbox. Guest replies go to the host."""
    from app.api import routes_mailbox as mb
    from app.services import calendar_sync as cal
    out = []
    if settings.smtp_host and settings.smtp_user and settings.smtp_password:     # the "Email sent by the app" account set by the administrator
        out.append({"address": settings.smtp_from or settings.smtp_user, "from": settings.smtp_from or settings.smtp_user, "reply_to": host_email(owner),
                    "username": settings.smtp_user, "password": settings.smtp_password, "smtp_host": settings.smtp_host, "smtp_port": settings.smtp_port, "platform": True})
    try:
        for a in await mb._stored(db, owner):
            try: out.append(await mb._account(db, owner, a["id"]))
            except Exception: continue
    except Exception: pass
    legacy = await cal.get_mail(db, owner.id)
    if legacy and not any(x.get("address") == legacy.get("address") and not x.get("platform") for x in out): out.append(legacy)
    return out

@router.get("/booking-senders")
async def booking_senders(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """Which address booking emails will come from (shown on the Booking tab). Never includes a password."""
    s = await _senders(db, user)
    return {"from": (s[0].get("from") or s[0].get("address")) if s else "", "app_account": bool(s and s[0].get("platform")), "count": len(s)}

async def _email_both(db: AsyncSession, owner: User, bt: BookingType, b: Booking, join_url: str, kind: str) -> str:
    """Best effort: send from the host's connected mailbox. Returns a short note; failures never block the booking."""
    from app.services import calendar_sync as cal
    from app.services.invites import build_ics
    accts = await _senders(db, owner)
    if not accts: return "no_mailbox"
    cancel = kind == "cancelled"; word = {"booked": "confirmed", "cancelled": "cancelled", "rescheduled": "rescheduled"}[kind]
    host = _host_name(owner)
    ics = None
    try:
        ics = build_ics(b.id, f"{bt.title}: {b.guest_name} and {host}", _aware(b.start_at), _aware(b.end_at), (host_email(owner) or owner.email), [b.guest_email] + ([host_email(owner)] if host_email(owner) else []), join_url, bt.description, sequence=1 if kind != "booked" else 0, cancel=cancel)
        body = (f"Hello {b.guest_name},\n\nYour {bt.duration_minutes} minute meeting with {host} is {word}.\n\nWhen: {_fmt(b.start_at, b.guest_timezone)}\n" + ("" if cancel else f"Join: {join_url}\n") + "\n" + (f"Change or cancel: {join_url.split('#')[0]}#/booking/{b.token}\n" if not cancel else "") + "\n- iSift")
        guest_msg = (f"{word.capitalize()}: {bt.title} with {host}", body, ics)
        host_msg = (f"{word.capitalize()}: {b.guest_name} booked {bt.title}", f"{b.guest_name} <{b.guest_email}> {word} {bt.title}.\nWhen: {_fmt(b.start_at, bt.timezone)}\n" + (f"Note: {b.guest_note}\n" if b.guest_note else ""), None)
        for acct in accts:                      # try each of the host's mailboxes until one can send
            try:
                await mailer.send(acct, [b.guest_email], *guest_msg)
                if host_email(owner):
                    try: await mailer.send(acct, [host_email(owner)], *host_msg)
                    except Exception: pass      # the guest's confirmation is what matters
                return "sent"
            except Exception: continue
        return "failed"
    except Exception: return "failed"

def _base(payload: dict) -> str:
    from urllib.parse import urlsplit
    p = urlsplit(str(payload.get("base_url") or settings.frontend_origin or ""))
    if p.scheme not in ("http", "https") or not p.netloc: raise HTTPException(422, "Could not work out this app's web address.")
    return f"{p.scheme}://{p.netloc}/"

async def _create(db: AsyncSession, bt: BookingType, owner: User, name: str, email: str, note: str, tz: str, start: datetime, base: str) -> tuple[Booking, str]:
    from app.api.routes_rooms import make_room
    end = start + timedelta(minutes=bt.duration_minutes)
    z = _zone(bt.timezone); free = await free_slots(db, bt, (start.astimezone(z).date()) - timedelta(days=1), start.astimezone(z).date() + timedelta(days=1))
    if start not in free: raise HTTPException(409, "Sorry, that time was just taken or is no longer available. Please pick another.")
    host = _host_name(owner)
    m = Meeting(owner_id=owner.id, external_id=f"local:{secrets.token_hex(8)}", title=f"{bt.title}: {name} and {host}", organizer=shown_email(owner.email), start_at=start, end_at=end, sensitivity="normal", status="scheduled",
                agenda=(f"Booked by {name} <{email}> through the booking page.\n" + (f"Note from guest: {note}" if note else "")).strip())
    db.add(m); await db.flush()
    room, m = await make_room(db, owner, m.title, base, meeting=m, access="open", waiting_room=False, options={})
    m.external_id = f"room:{room.code}"
    b = Booking(type_id=bt.id, owner_id=owner.id, token=secrets.token_urlsafe(24), guest_name=name, guest_email=email, guest_note=note, guest_timezone=tz, start_at=start, end_at=end, meeting_id=m.id, room_code=room.code)
    db.add(b); await db.commit(); return b, m.join_url

def _guest(payload: dict) -> tuple[str, str, str, str]:
    name = str(payload.get("name") or "").strip()[:200]; email = str(payload.get("email") or "").strip().lower()
    if not name: raise HTTPException(422, "Please enter your name.")
    if not EMAIL.match(email): raise HTTPException(422, "Please enter a valid email address so you get the meeting link.")
    tz = str(payload.get("timezone") or "UTC")
    try: ZoneInfo(tz)
    except Exception: tz = "UTC"
    return name, email, str(payload.get("note") or "").strip()[:1000], tz

@router.post("/public/book/{slug}")
async def public_book(slug: str, payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    _limit(request, "book")
    bt, owner = await _public_type(db, slug)
    name, email, note, tz = _guest(payload)
    b, join = await _create(db, bt, owner, name, email, note, tz, _parse_start(payload.get("start")), _base(payload))
    db.add(AuditLog(actor=email, action="booking.create", resource_type="booking", safe_metadata={"slug": slug})); await db.commit()
    sent = await _email_both(db, owner, bt, b, join, "booked")
    return {"token": b.token, "join_url": join, "start_at": _aware(b.start_at).isoformat(), "end_at": _aware(b.end_at).isoformat(), "email": sent, "host": _host_name(owner), "title": bt.title}

# ---------------- public: manage a booking with its private link ----------------
async def _by_token(db: AsyncSession, token: str) -> tuple[Booking, BookingType, User]:
    b = (await db.execute(select(Booking).where(Booking.token == token))).scalar_one_or_none()
    bt = await db.get(BookingType, b.type_id) if b else None; owner = await db.get(User, b.owner_id) if b else None
    if not b or not bt or not owner: raise HTTPException(404, "This booking link is not valid.")
    return b, bt, owner

async def _join_url(db: AsyncSession, b: Booking) -> str | None:
    m = await db.get(Meeting, b.meeting_id) if b.meeting_id else None
    return m.join_url if m else None

@router.get("/public/booking/{token}")
async def public_booking(token: str, db: AsyncSession = Depends(get_db)):
    b, bt, owner = await _by_token(db, token)
    return {"title": bt.title, "slug": bt.slug, "host": _host_name(owner), "guest_name": b.guest_name, "start_at": _aware(b.start_at).isoformat(), "end_at": _aware(b.end_at).isoformat(), "status": b.status,
            "duration_minutes": bt.duration_minutes, "join_url": await _join_url(db, b) if b.status == "booked" else None, "past": _aware(b.end_at) < datetime.now(timezone.utc), "can_rebook": bt.active}

async def _end_meeting(db: AsyncSession, b: Booking) -> None:
    m = await db.get(Meeting, b.meeting_id) if b.meeting_id else None
    if not m: return
    room = (await db.execute(select(Room).where(Room.code == b.room_code))).scalar_one_or_none() if b.room_code else None
    if room:
        from app.api.routes_rooms import end_room
        await end_room(db, room, True)
    m.status = "cancelled"

async def cancel_booking(db: AsyncSession, b: Booking, bt: BookingType, owner: User, base: str) -> str:
    if b.status == "cancelled": return "sent"
    join = await _join_url(db, b) or ""
    b.status = "cancelled"; await _end_meeting(db, b); await db.commit()
    return await _email_both(db, owner, bt, b, join or base, "cancelled")

@router.post("/public/booking/{token}/cancel")
async def public_cancel(token: str, payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    _limit(request, "cancel", 30)
    b, bt, owner = await _by_token(db, token)
    if _aware(b.end_at) < datetime.now(timezone.utc): raise HTTPException(409, "This meeting has already happened.")
    return {"ok": True, "email": await cancel_booking(db, b, bt, owner, _base(payload))}

@router.post("/public/booking/{token}/reschedule")
async def public_reschedule(token: str, payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    _limit(request, "resched", 20)
    b, bt, owner = await _by_token(db, token)
    if b.status != "booked": raise HTTPException(409, "This booking was cancelled. Book a new time instead.")
    if not bt.active: raise HTTPException(409, "This booking page is no longer taking bookings.")
    start = _parse_start(payload.get("start")); base = _base(payload)
    z = _zone(bt.timezone); d = start.astimezone(z).date()
    free = await free_slots(db, bt, d - timedelta(days=1), d + timedelta(days=1), skip_meeting=b.meeting_id or "")
    if start not in free: raise HTTPException(409, "Sorry, that time is not available. Please pick another.")
    m = await db.get(Meeting, b.meeting_id) if b.meeting_id else None
    b.start_at, b.end_at = start, start + timedelta(minutes=bt.duration_minutes)
    if m: m.start_at, m.end_at = b.start_at, b.end_at
    await db.commit()
    join = await _join_url(db, b) or base
    return {"ok": True, "start_at": _aware(b.start_at).isoformat(), "end_at": _aware(b.end_at).isoformat(), "join_url": join, "email": await _email_both(db, owner, bt, b, join, "rescheduled")}

@router.get("/public/booking/{token}/ics")
async def public_ics(token: str, db: AsyncSession = Depends(get_db)):
    from app.services.invites import build_ics
    b, bt, owner = await _by_token(db, token)
    data = build_ics(b.id, f"{bt.title}: {b.guest_name} and {_host_name(owner)}", _aware(b.start_at), _aware(b.end_at), (host_email(owner) or owner.email), [b.guest_email], await _join_url(db, b), bt.description)
    return Response(data, media_type="text/calendar", headers={"Content-Disposition": 'attachment; filename="meeting.ics"'})

# ---------------- owner: cancel a booking from iSift ----------------
@router.post("/bookings/{bid}/cancel")
async def owner_cancel(bid: str, payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    b = await db.get(Booking, bid)
    if not b or b.owner_id != user.id: raise HTTPException(404, "Booking not found.")
    bt = await db.get(BookingType, b.type_id)
    sent = await cancel_booking(db, b, bt, user, _base(payload))
    return {"ok": True, "email": sent}
