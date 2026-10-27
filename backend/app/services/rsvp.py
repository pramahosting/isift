"""Replies to meeting invitations (accept / maybe / decline / propose another time) and the links that go in the invitation email.

A reply link carries a signed token (meeting + recipient), so the recipient needs no account. The replies are kept in one
settings row per meeting, and the host is emailed as each one arrives."""
import base64, hashlib, hmac, logging, re
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
    """Plain-text end of the invitation. Yes / No / Maybe are the buttons the mail program shows at the top of the email; this link is only for suggesting another time or adding the event elsewhere."""
    return f"\nUse the Yes, No or Maybe buttons at the top of this email to reply. To suggest another time or add this to a different calendar: {base}/#/rsvp/{make_token(m.id, email)}\n"

def html_body(text: str, base: str, m, email: str, join_url: str | None) -> str:
    """The same invitation as a small HTML page. Replying is done with the mail program's own Yes / No / Maybe buttons (from the attached calendar invitation), so no reply button opens a web page."""
    from html import escape
    r = f"{base}/#/rsvp/{make_token(m.id, email)}"
    body = escape(text.strip()).replace("\n", "<br>")
    if join_url: body = body.replace(escape(join_url), f'<a href="{escape(join_url)}">{escape(join_url)}</a>')
    lk = lambda label, q: f'<a href="{r}?r={q}" style="color:#1a56db">{label}</a>'
    return ('<div style="font:15px/1.5 Arial,Helvetica,sans-serif;color:#202124">' + body +
            '<p style="margin:18px 0 0;color:#5f6368;font-size:13px">To reply, use the <b>Yes / No / Maybe</b> buttons at the top of this email. '
            'You can also ' + lk("suggest another time", "proposed") + " or " + lk("add it to a different calendar", "calendar") + ".</p></div>")

def set_organizer(ics: bytes | None, email: str, name: str = "") -> bytes | None:
    """Make the host's own address the organizer, so a Yes / No / Maybe pressed in the guest's mail program is emailed back to the host."""
    if not ics: return ics
    cn = f';CN="{name.replace(chr(34), "")}"' if name else ""
    return re.sub(rb"ORGANIZER[^\r\n]*", f"ORGANIZER{cn}:mailto:{email}".encode(), ics, count=1)

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

NO_MAILBOX = "Connect your email so invitations go from your own address: open Mail, choose Add account and enter your login email."

async def senders(db, user, allow_app: bool = False) -> list[dict]:
    """Where invitations are sent from: always the host's own address. The mailbox that matches the sign-in email is used alone when it is connected
    (Gmail, Outlook, Microsoft 365, Yahoo, a company mailbox: any kind). Otherwise the host's other connected mailboxes. The app's own sender is used only
    when allow_app is set, for notices to the host themselves."""
    from app.api.routes_booking import _senders
    out = await _senders(db, user)
    own = [a for a in out if not a.get("platform")]
    mine = [a for a in own if (a.get("address") or "").lower() == (user.email or "").lower()]
    if mine: return mine[:1]
    if own or not allow_app: return own
    name = (getattr(user, "display_name", "") or "").replace('"', "").strip()
    app = []
    for a in out:
        if a.get("platform"):
            a = dict(a); a["from"] = f'{name or user.email} via iSift <{a.get("address")}>'; a["reply_to"] = user.email; app.append(a)
    return app

async def send_each(acct, recipients: list[str], subject: str, body: str, m, base: str, join_url: str | None, ics: bytes | None, details: str = "") -> dict:
    """One email per person, each with that person's own reply links (so the host knows who answered). `acct` is one account or a list to try in turn."""
    from app.integrations import mail as mailer
    accts = acct if isinstance(acct, list) else [acct]
    used, skipped = [], []
    for r in recipients:
        err = None
        for a in accts:
            try:
                oi = set_organizer(ics, a["reply_to"]) if a.get("platform") and a.get("reply_to") else ics        # the app's sender: replies still go to the host
                await mailer.send(a, [r], subject, body + footer(base, m, r, join_url, details), oi, html=html_body(body, base, m, r, join_url)); err = None; used.append((r, a.get("address"))); break
            except mailer.MailError as exc: err = exc; skipped.append(f"{a.get('address')}: {exc}")
        if err: raise err
    return {"used": used, "skipped": skipped}

async def tell_host(db, m, host, who: str, status: str, proposed: str, note: str, tz_name: str) -> None:
    """Email the host that someone replied. Uses the app's own sender, or the host's connected mail account."""
    from app.integrations import mail as mailer
    from app.services import signup, calendar_sync as cal
    accts = await senders(db, host, allow_app=True)
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


def _ics_fields(txt: str) -> dict:
    t = re.sub(r"\r?\n[ \t]", "", txt); out = {"uid": "", "who": "", "status": ""}
    for line in t.splitlines():
        u = line.upper()
        if u.startswith("UID:"): out["uid"] = line[4:].strip()
        elif u.startswith("ATTENDEE"):
            mm = re.search(r"mailto:([^\s;]+)", line, re.I); ps = re.search(r"PARTSTAT=([A-Z-]+)", u)
            if mm: out["who"] = mm.group(1).strip().lower(); out["status"] = ps.group(1) if ps else ""
    return out

PARTSTAT = {"ACCEPTED": "accepted", "TENTATIVE": "tentative", "DECLINED": "declined"}

async def pull_replies(db, user, m) -> int:
    """Read Yes / No / Maybe answers that came back to the host's mailboxes as calendar replies and record them on the meeting."""
    import asyncio
    from app.integrations import mail as mailer
    n = 0; v = await load(db, m.id)
    for a in [x for x in await senders(db, user) if not x.get("platform") and x.get("imap_host")][:3]:
        try: texts = await asyncio.wait_for(mailer.find_replies(a), 20)
        except Exception: continue
        for t in texts:
            f = _ics_fields(t)
            if f["uid"] != f"{m.id}@isift" or f["status"] not in PARTSTAT or not f["who"]: continue
            new = PARTSTAT[f["status"]]; old = v["responses"].get(f["who"])
            if old and old.get("status") == new: continue
            await record(db, m.id, f["who"], new); v = await load(db, m.id); n += 1
    return n


def sent_from(res: dict, user) -> str:
    """A short phrase for the confirmation: which mailbox sent it, and why your own mailbox was skipped, if it was."""
    used = {a for _r, a in res.get("used", []) if a}
    out = f" (from {', '.join(sorted(used))})" if used else ""
    if used and (user.email or "").lower() not in {u.lower() for u in used} and res.get("skipped"):
        out += f". Your own mailbox could not send: {res['skipped'][0]}"
    return out
