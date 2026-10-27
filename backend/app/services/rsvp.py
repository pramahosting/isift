"""Replies to meeting invitations (accept / maybe / decline / propose another time) and the links that go in the invitation email.

A reply link carries a signed token (meeting + recipient), so the recipient needs no account. The replies are kept in one
settings row per meeting, and the host is emailed as each one arrives."""
import base64, hashlib, hmac, logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode
from app.core.config import settings
from app.models import IntegrationSetting

log = logging.getLogger("isift.rsvp")
STATUSES = ("accepted", "tentative", "declined", "proposed")
LABEL = {"accepted": "accepted", "tentative": "replied maybe to", "declined": "declined", "proposed": "proposed another time for"}

def _sig(body: str) -> str: return hmac.new(settings.local_auth_secret.encode(), ("rsvp:" + body).encode(), hashlib.sha256).hexdigest()[:32]

def make_token(meeting_id: str, email: str) -> str:
    body = base64.urlsafe_b64encode(f"{meeting_id}|{email.lower()}".encode()).decode().rstrip("=")
    return f"{body}.{_sig(body)}"

def read_token(token: str) -> tuple[str, str] | None:
    try:
        body, sig = str(token).split(".", 1)
        if not hmac.compare_digest(sig, _sig(body)): return None
        mid, email = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode().split("|", 1)
        return (mid, email) if mid and "@" in email else None
    except Exception: return None

def public_base(request=None) -> str:
    o = (settings.frontend_origin or "").rstrip("/")
    if o and not o.startswith(("http://localhost", "http://127.")): return o
    return str(request.base_url).rstrip("/") if request is not None else o

def _utc(d: datetime) -> datetime: return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)

def calendar_links(title: str, start: datetime, end: datetime, join_url: str | None, details: str = "") -> dict:
    s, e = _utc(start), _utc(end); f = lambda d: d.strftime("%Y%m%dT%H%M%SZ")
    note = (details + "\n\n" if details else "") + (f"Join: {join_url}" if join_url else "")
    return {
        "google": "https://calendar.google.com/calendar/render?" + urlencode({"action": "TEMPLATE", "text": title, "dates": f"{f(s)}/{f(e)}", "details": note, "location": join_url or ""}, quote_via=quote),
        "outlook": "https://outlook.live.com/calendar/0/deeplink/compose?" + urlencode({"path": "/calendar/action/compose", "rru": "addevent", "subject": title, "startdt": s.strftime("%Y-%m-%dT%H:%M:%SZ"), "enddt": e.strftime("%Y-%m-%dT%H:%M:%SZ"), "body": note, "location": join_url or ""}, quote_via=quote),
        "office365": "https://outlook.office.com/calendar/0/deeplink/compose?" + urlencode({"path": "/calendar/action/compose", "rru": "addevent", "subject": title, "startdt": s.strftime("%Y-%m-%dT%H:%M:%SZ"), "enddt": e.strftime("%Y-%m-%dT%H:%M:%SZ"), "body": note, "location": join_url or ""}, quote_via=quote),
        "yahoo": "https://calendar.yahoo.com/?" + urlencode({"v": "60", "title": title, "st": f(s), "et": f(e), "desc": note, "in_loc": join_url or ""}, quote_via=quote),
    }

def footer(base: str, m, email: str, join_url: str | None, details: str = "") -> str:
    """Plain-text end of the invitation: one short link to answer or add the event to a calendar."""
    return f"\nAccept, decline or add to your calendar: {base}/#/rsvp/{make_token(m.id, email)}\n"

def html_body(text: str, base: str, m, email: str, join_url: str | None) -> str:
    """The same invitation as a small HTML page: the message, then one-word links (Accept, Maybe, Decline, Suggest a time, Add to calendar)."""
    from html import escape
    r = f"{base}/#/rsvp/{make_token(m.id, email)}"
    body = escape(text.strip()).replace("\n", "<br>")
    if join_url: body = body.replace(escape(join_url), f'<a href="{escape(join_url)}">{escape(join_url)}</a>')
    a = lambda label, q, bg="#fff", fg="#1a56db": f'<a href="{r}?r={q}" style="display:inline-block;margin:0 6px 8px 0;padding:8px 16px;border:1px solid #1a56db;border-radius:6px;background:{bg};color:{fg};text-decoration:none;font-weight:600">{label}</a>'
    return ('<div style="font:15px/1.5 Arial,Helvetica,sans-serif;color:#202124">' + body +
            '<p style="margin:18px 0 6px;color:#5f6368">Will you come?</p><div>' + a("Accept", "accepted", "#1a56db", "#fff") + a("Maybe", "tentative") + a("Decline", "declined") + a("Suggest a time", "proposed") + a("Add to calendar", "calendar") + "</div></div>")

def _key(meeting_id: str) -> str: return f"rsvp:{meeting_id}"

async def load(db, meeting_id: str) -> dict:
    row = await db.get(IntegrationSetting, _key(meeting_id)); v = dict(row.value or {}) if row else {}
    v.setdefault("invited", []); v.setdefault("responses", {}); return v

async def save(db, meeting_id: str, v: dict) -> None:
    row = await db.get(IntegrationSetting, _key(meeting_id))
    if row: row.value = v
    else: db.add(IntegrationSetting(key=_key(meeting_id), value=v))
    await db.commit()

async def note_invited(db, meeting_id: str, emails: list[str]) -> None:
    v = await load(db, meeting_id); v["invited"] = sorted(set(v["invited"]) | {e.lower() for e in emails}); await save(db, meeting_id, v)

async def record(db, meeting_id: str, email: str, status: str, proposed: str = "", note: str = "") -> dict:
    v = await load(db, meeting_id)
    v["invited"] = sorted(set(v["invited"]) | {email.lower()})
    v["responses"][email.lower()] = {"status": status, "at": datetime.now(timezone.utc).isoformat(), "proposed_start": proposed, "note": note[:500]}
    await save(db, meeting_id, v); return v["responses"][email.lower()]

async def reset(db, meeting_id: str) -> None:
    v = await load(db, meeting_id); v["responses"] = {}; await save(db, meeting_id, v)

async def senders(db, user) -> list[dict]:
    """Where invitations are sent from: the host's own mailboxes first (so Accept / Decline pressed inside Gmail or Outlook comes back to the host),
    then the app's own sender as a fallback."""
    from app.api.routes_booking import _senders
    out = await _senders(db, user)
    own = [a for a in out if not a.get("platform")]
    own.sort(key=lambda a: (a.get("address") or "").lower() != (user.email or "").lower())          # the mailbox that is the host's sign-in address goes first
    name = (getattr(user, "display_name", "") or "").replace('"', "").strip()
    app = []
    for a in out:
        if a.get("platform"):                                   # the app's sender: show the host's name, and send replies to the host's own address
            a = dict(a); a["from"] = f'{name or user.email} via iSift <{a.get("address")}>'; a["reply_to"] = user.email; app.append(a)
    return own + app

async def send_each(acct, recipients: list[str], subject: str, body: str, m, base: str, join_url: str | None, ics: bytes | None, details: str = "") -> None:
    """One email per person, each with that person's own reply links (so the host knows who answered). `acct` is one account or a list to try in turn."""
    from app.integrations import mail as mailer
    accts = acct if isinstance(acct, list) else [acct]
    for r in recipients:
        err = None
        for a in accts:
            try: await mailer.send(a, [r], subject, body + footer(base, m, r, join_url, details), ics, html=html_body(body, base, m, r, join_url)); err = None; break
            except mailer.MailError as exc: err = exc
        if err: raise err

async def tell_host(db, m, host, who: str, status: str, proposed: str, note: str, tz_name: str) -> None:
    """Email the host that someone replied. Uses the app's own sender, or the host's connected mail account."""
    from app.integrations import mail as mailer
    from app.services import signup, calendar_sync as cal
    accts = await senders(db, host)
    if not accts:
        log.warning("Reply from %s to %s not emailed: no mail account is set up", who, m.title); return
    body = f"{who} {LABEL.get(status, status)} your meeting: {m.title}\n"
    if status == "proposed" and proposed: body += f"Suggested time: {proposed}\n"
    if note: body += f"Note: {note}\n"
    body += "\nOpen the meeting in iSift (Meetings, then the meeting) to see every reply"
    body += " and use the suggested time." if status == "proposed" else "."
    for a in accts:
        try: await mailer.send(a, [host.email], f"{who} {LABEL.get(status, status)}: {m.title}", body); return
        except Exception: log.exception("Could not email the host about a reply (from %s)", a.get("address"))
