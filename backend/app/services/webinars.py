"""Webinars: setup, registration, emails, reminders, attendance, Q&A, polls and reports.

A webinar is an ordinary meeting room (so video, chat, recording and the big-meeting video server all work as they do today) with
one extra record: who registered, who the panelists are, and the Q&A and polls. The live part (view-only attendees, Q&A and poll
messages) is in routes_rooms.py and uses the functions here for everything that touches the database.
"""
import csv, io, logging, secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings as cfg
from app.models import User, Webinar, WebinarRegistrant, WebinarQuestion, WebinarPoll
from app.services.invites import EMAIL

log = logging.getLogger("isift")

DEFAULTS = {"registration": True, "approval": "auto", "questions": [], "capacity": 0, "qa": True, "qa_view": "all", "qa_anonymous": True, "chat": "host",
            "hand": True, "practice": True, "reminders": {"day": True, "hour": True}, "recording_url": "", "auto_followup": False, "welcome": "", "base": ""}
CHAT_MODES = ("host", "panelists", "everyone", "off")   # who an attendee's chat message reaches: the host only, the host and panelists, everyone, or nobody (chat off)
MAX_QUESTIONS = 8

def now() -> datetime: return datetime.now(timezone.utc)
def aware(d: datetime | None) -> datetime | None: return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)

def clean_settings(raw, cur: dict | None = None) -> dict:
    """What the host chose, checked. Unknown keys are dropped."""
    out = {**DEFAULTS, **(cur or {})}; raw = raw if isinstance(raw, dict) else {}
    for k in ("registration", "qa", "qa_anonymous", "hand", "practice", "auto_followup"):
        if k in raw: out[k] = bool(raw[k])
    if raw.get("approval") in ("auto", "manual"): out["approval"] = raw["approval"]
    if raw.get("qa_view") in ("all", "answered"): out["qa_view"] = raw["qa_view"]
    if raw.get("chat") in CHAT_MODES: out["chat"] = raw["chat"]
    if "capacity" in raw:
        try: out["capacity"] = max(0, min(int(raw["capacity"] or 0), int(cfg.webinar_max_attendees or 500)))
        except (TypeError, ValueError): pass
    for k in ("welcome", "recording_url"):
        if k in raw: out[k] = str(raw[k] or "").strip()[:1000 if k == "welcome" else 500]
    if out["recording_url"] and not out["recording_url"].lower().startswith(("http://", "https://")): out["recording_url"] = ""
    if "base" in raw and str(raw["base"]).startswith(("http://", "https://")): out["base"] = str(raw["base"]).rstrip("/")[:200]
    if isinstance(raw.get("reminders"), dict): out["reminders"] = {"day": bool(raw["reminders"].get("day", True)), "hour": bool(raw["reminders"].get("hour", True))}
    if isinstance(raw.get("questions"), list):
        qs = []
        for i, q in enumerate(raw["questions"][:MAX_QUESTIONS]):
            if not isinstance(q, dict) or not str(q.get("label") or "").strip(): continue
            opts = [str(o).strip()[:80] for o in (q.get("options") or []) if str(o).strip()][:12]
            qs.append({"id": f"q{i + 1}", "label": str(q["label"]).strip()[:120], "required": bool(q.get("required")), "type": "choice" if q.get("type") == "choice" and opts else "text", "options": opts if q.get("type") == "choice" else []})
        out["questions"] = qs
    return out

def clean_panelists(raw, cur: list | None = None) -> list[dict]:
    keep = {p["email"]: p for p in (cur or [])}; out = []
    for p in (raw or [])[:20]:
        email = str((p or {}).get("email") or "").strip().lower()
        if not EMAIL.match(email) or any(x["email"] == email for x in out): continue
        out.append({"email": email, "name": str((p or {}).get("name") or "").strip()[:80], "token": (keep.get(email) or {}).get("token") or secrets.token_urlsafe(12)})
    return out

# ---------------------------------------------------------------- links, times and emails
def base_of(w: Webinar) -> str: return (w.settings or {}).get("base") or ""
def page_link(w: Webinar) -> str: return f"{base_of(w)}/#/webinar/{w.id}"
def join_link(w: Webinar, reg: WebinarRegistrant) -> str: return f"{page_link(w)}?k={reg.token}"
def panelist_link(w: Webinar, p: dict) -> str: return f"{page_link(w)}?p={p['token']}"

def when_text(w: Webinar, tz: str | None = None) -> str:
    try: z = ZoneInfo(tz or w.tz or "Australia/Sydney")
    except Exception: z = timezone.utc
    d = aware(w.start_at).astimezone(z)
    return f"{d.strftime('%A %d %B %Y, %I:%M %p').replace(' 0', ' ')} ({tz or w.tz})"

def ics_for(w: Webinar, to: str, link: str, cancel: bool = False) -> bytes:
    from app.services.invites import build_ics
    start = aware(w.start_at)
    return build_ics(f"webinar-{w.id}", w.title, start, start + timedelta(minutes=w.minutes or 60), "noreply@isift.au", [to], link, (w.description or "")[:500], cancel=cancel)

async def send_mail(to: str, subject: str, body: str, ics: bytes | None = None) -> bool:
    """Sends from the app's own email account (Admin Console > Email). Never raises: a failed email must not break the webinar."""
    from app.services.signup import app_sender
    from app.integrations import mail
    acct = app_sender()
    if not acct: log.warning("Webinar email to %s was not sent: no email account is set up in Admin Console.", to); return False
    try: await mail.send(acct, [to], subject, body, ics=ics); return True
    except Exception as exc: log.warning("Webinar email to %s failed: %s", to, exc); return False

async def host_of(db: AsyncSession, w: Webinar) -> User | None: return await db.get(User, w.host_id)

async def tell_registration(db: AsyncSession, w: Webinar, reg: WebinarRegistrant) -> bool:
    host = await host_of(db, w); by = (host.display_name or host.email) if host else "the host"
    if reg.status == "pending":
        return await send_mail(reg.email, f"Registration received: {w.title}", f"Hi {reg.name or 'there'},\n\nThank you for registering for {w.title}.\nThe host reviews each registration. You will get another email with your personal link as soon as you are approved.\n\nWhen: {when_text(w)}\n\n— {by}, with iSift")
    link = join_link(w, reg)
    extra = f"\n{(w.settings or {}).get('welcome')}\n" if (w.settings or {}).get("welcome") else ""
    return await send_mail(reg.email, f"You are registered: {w.title}", f"Hi {reg.name or 'there'},\n\nYou are registered for {w.title}.\n\nWhen: {when_text(w)}\nYour personal link (please do not share it): {link}\n{extra}\nThe link is also in the attached calendar invitation. Open it a few minutes early.\n\n— {by}, with iSift", ics_for(w, reg.email, link))

async def tell_decision(db: AsyncSession, w: Webinar, reg: WebinarRegistrant) -> bool:
    if reg.status == "approved": return await tell_registration(db, w, reg)
    if reg.status == "denied": return await send_mail(reg.email, f"About your registration: {w.title}", f"Hi {reg.name or 'there'},\n\nThe host was not able to approve your registration for {w.title}. Thank you for your interest.")
    return False

async def tell_panelist(w: Webinar, p: dict, host: User | None) -> bool:
    link = panelist_link(w, p); by = (host.display_name or host.email) if host else "the host"
    return await send_mail(p["email"], f"You are a panelist: {w.title}", f"Hi {p.get('name') or 'there'},\n\n{by} has invited you to speak as a panelist at {w.title}.\n\nWhen: {when_text(w)}\nYour panelist link (it gives you your microphone and camera, so please do not share it): {link}\n\nThe host may open a practice session before attendees are let in.", ics_for(w, p["email"], link))

async def run_reminders(db: AsyncSession) -> int:
    """Called about once a minute by the worker: reminder emails, and the optional thank-you after the webinar. Returns the number of emails sent."""
    sent = 0; t = now()
    for w in (await db.execute(select(Webinar).where(Webinar.status == "scheduled", Webinar.start_at > t - timedelta(hours=1), Webinar.start_at < t + timedelta(hours=25)))).scalars().all():
        until = (aware(w.start_at) - t).total_seconds(); st = dict(w.reminder_state or {}); rem = (w.settings or {}).get("reminders") or {}
        kind = "hour" if 0 < until <= 3600 and rem.get("hour", True) and "hour" not in st else "day" if 7200 < until <= 86400 and rem.get("day", True) and "day" not in st and "hour" not in st else ""
        if not kind: continue
        st[kind] = t.isoformat(); w.reminder_state = st; await db.commit()
        when = "in about an hour" if kind == "hour" else "tomorrow"
        regs = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.status == "approved"))).scalars().all()
        for r in regs:
            if await send_mail(r.email, f"Starts {when}: {w.title}", f"Hi {r.name or 'there'},\n\n{w.title} starts {when}.\n\nWhen: {when_text(w)}\nYour personal link: {join_link(w, r)}\n"): sent += 1
        if kind == "hour":
            for p in w.panelists or []:
                if await send_mail(p["email"], f"Starts {when}: {w.title}", f"Hi {p.get('name') or 'there'},\n\n{w.title} starts {when}.\nYour panelist link: {panelist_link(w, p)}\n"): sent += 1
    for w in (await db.execute(select(Webinar).where(Webinar.status == "ended", Webinar.ended_at > t - timedelta(days=3)))).scalars().all():
        st = dict(w.reminder_state or {})
        if (w.settings or {}).get("auto_followup") and "followup" not in st:
            st["followup"] = t.isoformat(); w.reminder_state = st; await db.commit()
            r = await send_followups(db, w, "attended"); r2 = await send_followups(db, w, "missed"); sent += r + r2
    return sent

async def send_followups(db: AsyncSession, w: Webinar, kind: str, subject: str = "", message: str = "") -> int:
    """kind: attended (thank you) or missed (sorry you missed it). Each person gets it once per kind."""
    regs = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id, WebinarRegistrant.status == "approved"))).scalars().all()
    rec = (w.settings or {}).get("recording_url") or ""; n = 0
    for r in regs:
        went = (r.seconds or 0) >= 60
        if (kind == "attended") != went: continue
        tag = f"followup_{kind}"
        if (r.answers or {}).get("_" + tag): continue
        default = (f"Thank you for joining {w.title}." if went else f"We missed you at {w.title}.") + (f"\n\nThe recording is here: {rec}" if rec else "")
        body = f"Hi {r.name or 'there'},\n\n{(message or default).strip()}" + (f"\n\nThe recording is here: {rec}" if message and rec and rec not in message else "")
        if await send_mail(r.email, (subject or ("Thank you for joining: " if went else "Sorry we missed you: ") + w.title)[:200], body):
            r.answers = {**(r.answers or {}), "_" + tag: now().isoformat()}; n += 1
    await db.commit(); return n

# ---------------------------------------------------------------- who may come in (used by the live room)
async def get_by_room(db: AsyncSession, code: str) -> Webinar | None:
    return (await db.execute(select(Webinar).where(Webinar.room_code == code))).scalar_one_or_none()

async def resolve_role(db: AsyncSession, w: Webinar, user: User | None, reg_token: str = "", panel_token: str = "") -> dict:
    """Returns {"role": host|panelist|attendee, "name", "rid"} or {"error", "code"}."""
    if w.status == "cancelled": return {"error": "This webinar was cancelled.", "code": "cancelled"}
    if user and user.id == w.host_id: return {"role": "host", "name": user.display_name or user.email}
    pan = next((p for p in (w.panelists or []) if panel_token and secrets.compare_digest(p["token"], panel_token)), None) or (next((p for p in (w.panelists or []) if user and p["email"] == user.email.lower()), None))
    if pan: return {"role": "panelist", "name": pan.get("name") or (user.display_name if user else "") or pan["email"], "email": pan["email"]}
    s = w.settings or {}
    if reg_token:
        r = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.token == reg_token, WebinarRegistrant.webinar_id == w.id))).scalar_one_or_none()
        if not r: return {"error": "That registration link is not valid. Register again to get a new one.", "code": "register"}
        if r.status == "pending": return {"error": "Your registration is waiting for the host's approval. You will get an email when it is approved.", "code": "pending"}
        if r.status != "approved": return {"error": "This registration is not active. Register again to get a new link.", "code": "register"}
        return {"role": "attendee", "name": r.name or r.email, "rid": r.id, "email": r.email}
    if s.get("registration", True): return {"error": "Register for this webinar first. Open the link in your confirmation email.", "code": "register"}
    return {"role": "attendee", "name": "", "rid": None, "email": ""}

async def attend_join(db: AsyncSession, rid: str | None):
    if not rid: return
    r = await db.get(WebinarRegistrant, rid)
    if r: r.joins = (r.joins or 0) + 1; r.joined_at = r.joined_at or now(); await db.commit()

async def attend_leave(db: AsyncSession, rid: str | None, seconds: float):
    if not rid: return
    r = await db.get(WebinarRegistrant, rid)
    if r: r.seconds = (r.seconds or 0) + int(max(0, seconds)); r.left_at = now(); await db.commit()

async def mark_ended(db: AsyncSession, code: str):
    w = await get_by_room(db, code)
    if w and w.status == "scheduled": w.status = "ended"; w.ended_at = now(); await db.commit()

# ---------------------------------------------------------------- Q&A and polls (live)
def _anon_name(q: WebinarQuestion, staff: bool) -> str:
    if q.anonymous and not staff: return "Anonymous attendee"
    return (q.name or "Attendee") + (" (anonymous)" if q.anonymous and staff else "")

def q_view(q: WebinarQuestion, me: str, staff: bool) -> dict:
    return {"id": q.id, "text": q.text, "name": _anon_name(q, staff), "up": len(q.upvoters or []), "upped": me in (q.upvoters or []), "status": q.status, "answer": q.answer, "by": q.answered_by,
            "at": aware(q.created_at).isoformat() if q.created_at else "", "mine": bool(me) and q.asker == me}

async def ask(db: AsyncSession, w: Webinar, key: str, name: str, email: str, text: str, anonymous: bool) -> WebinarQuestion | None:
    text = " ".join(str(text or "").split())[:500]
    if not text or not (w.settings or {}).get("qa", True): return None
    q = WebinarQuestion(webinar_id=w.id, asker=key, name=name[:120], email=email[:200], text=text, anonymous=bool(anonymous and (w.settings or {}).get("qa_anonymous", True)), upvoters=[])
    db.add(q); await db.commit(); return q

async def upvote(db: AsyncSession, wid: str, qid: str, key: str) -> bool:
    q = await db.get(WebinarQuestion, qid)
    if not q or q.webinar_id != wid or q.status == "dismissed": return False
    ups = list(q.upvoters or []); ups = [u for u in ups if u != key] if key in ups else ups + [key]; q.upvoters = ups; await db.commit(); return True

async def answer(db: AsyncSession, wid: str, qid: str, by: str, text: str = "", live: bool = False, dismiss: bool = False, reopen: bool = False) -> bool:
    q = await db.get(WebinarQuestion, qid)
    if not q or q.webinar_id != wid: return False
    if dismiss: q.status = "dismissed"
    elif reopen: q.status, q.answer, q.answered_by = "open", "", ""
    else: q.status = "answered"; q.answer = " ".join(str(text or "").split())[:1000] if not live else (q.answer or ""); q.answered_by = by[:120]
    await db.commit(); return True

def _counts(p: WebinarPoll) -> list[int]:
    c = [0] * len(p.options or [])
    for ch in (p.votes or {}).values():
        for i in ch:
            if 0 <= i < len(c): c[i] += 1
    return c

def poll_view(p: WebinarPoll, me: str, staff: bool) -> dict | None:
    if not staff and p.status == "draft": return None
    if not staff and p.status == "closed" and not p.share_results: return None
    d = {"id": p.id, "question": p.question, "options": p.options or [], "multi": p.multi, "status": p.status, "share": p.share_results, "mine": (p.votes or {}).get(me, [])}
    if staff or p.share_results: d["counts"] = _counts(p); d["total"] = len(p.votes or {})
    return d

async def vote(db: AsyncSession, wid: str, pid: str, key: str, choices) -> bool:
    p = await db.get(WebinarPoll, pid)
    if not p or p.webinar_id != wid or p.status != "open": return False
    ch = sorted({int(c) for c in (choices or []) if isinstance(c, int) and 0 <= c < len(p.options or [])})
    if not ch or (len(ch) > 1 and not p.multi): return False
    p.votes = {**(p.votes or {}), key: ch}; await db.commit(); return True

async def snapshot(db: AsyncSession, wid: str) -> tuple[list[WebinarQuestion], list[WebinarPoll]]:
    qs = (await db.execute(select(WebinarQuestion).where(WebinarQuestion.webinar_id == wid).order_by(WebinarQuestion.created_at))).scalars().all()
    ps = (await db.execute(select(WebinarPoll).where(WebinarPoll.webinar_id == wid).order_by(WebinarPoll.position, WebinarPoll.created_at))).scalars().all()
    return list(qs), list(ps)

def views_for(qs: list[WebinarQuestion], ps: list[WebinarPoll], me: str, staff: bool, qa_view: str) -> dict:
    """What one person sees: staff see every question; attendees see the public ones (all, or only answered) and their own."""
    out = []
    for q in qs:
        if q.status == "dismissed" and not staff: continue
        public = q.status == "answered" or (qa_view == "all" and q.status == "open")
        if staff or public or (me and q.asker == me): out.append(q_view(q, me, staff))
    return {"questions": out, "polls": [v for v in (poll_view(p, me, staff) for p in ps) if v]}

# ---------------------------------------------------------------- reports
def _row_dt(d): return aware(d).isoformat(timespec="seconds") if d else ""

def csv_text(rows: list[list]) -> str:
    buf = io.StringIO(); w = csv.writer(buf)
    for r in rows: w.writerow([("'" + str(c) if isinstance(c, str) and c[:1] in "=+-@" else c) for c in r])      # a cell that starts like a formula is made harmless in Excel
    return buf.getvalue()

async def report(db: AsyncSession, w: Webinar) -> dict:
    regs = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id).order_by(WebinarRegistrant.created_at))).scalars().all()
    qs, ps = await snapshot(db, w.id)
    went = [r for r in regs if (r.seconds or 0) >= 1 or r.joins]
    secs = [r.seconds or 0 for r in went]
    return {"registered": sum(1 for r in regs if r.status in ("approved", "pending")), "approved": sum(1 for r in regs if r.status == "approved"), "pending": sum(1 for r in regs if r.status == "pending"),
            "attended": len(went), "attend_rate": round(100 * len(went) / max(1, sum(1 for r in regs if r.status == "approved")), 1), "avg_minutes": round(sum(secs) / max(1, len(secs)) / 60, 1),
            "questions": len(qs), "answered": sum(1 for q in qs if q.status == "answered"), "polls": len(ps), "votes": sum(len(p.votes or {}) for p in ps)}

async def export(db: AsyncSession, w: Webinar, kind: str) -> tuple[str, str]:
    """(file name, csv text) for registrants, attendance, questions or polls."""
    slug = "".join(c if c.isalnum() else "-" for c in w.title.lower()).strip("-")[:40] or "webinar"
    qdefs = (w.settings or {}).get("questions") or []
    if kind in ("registrants", "attendance"):
        regs = (await db.execute(select(WebinarRegistrant).where(WebinarRegistrant.webinar_id == w.id).order_by(WebinarRegistrant.created_at))).scalars().all()
        head = ["Name", "Email", "Status", "Registered at"] + [q["label"] for q in qdefs] + ["Attended", "First joined", "Minutes watched", "Times joined"]
        rows = [head]
        for r in regs:
            if kind == "attendance" and not (r.seconds or r.joins): continue
            rows.append([r.name, r.email, r.status, _row_dt(r.created_at)] + [(r.answers or {}).get(q["id"], "") for q in qdefs] + ["Yes" if (r.seconds or r.joins) else "No", _row_dt(r.joined_at), round((r.seconds or 0) / 60, 1), r.joins or 0])
        return f"{slug}-{kind}.csv", csv_text(rows)
    qs, ps = await snapshot(db, w.id)
    if kind == "questions":
        rows = [["Asked at", "From", "Anonymous", "Question", "Upvotes", "Status", "Answer", "Answered by"]]
        for q in qs: rows.append([_row_dt(q.created_at), q.name, "Yes" if q.anonymous else "No", q.text, len(q.upvoters or []), q.status, q.answer, q.answered_by])
        return f"{slug}-questions.csv", csv_text(rows)
    rows = [["Poll", "Option", "Votes", "Share of votes"]]
    for p in ps:
        c = _counts(p); tot = sum(c)
        for o, n in zip(p.options or [], c): rows.append([p.question, o, n, f"{round(100 * n / tot)}%" if tot else "0%"])
    return f"{slug}-polls.csv", csv_text(rows)
