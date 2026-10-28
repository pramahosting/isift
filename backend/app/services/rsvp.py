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
    return f"\nTo reply, use the Yes / No / Maybe buttons at the bottom of this email (or the ones your mail program shows at the top). To suggest another time or add this to a calendar: {base}/#/rsvp/{make_token(m.id, email)}\n"

def html_body(text: str, base: str, m, email: str, join_url: str | None, host: str = "") -> str:
    """The invitation as a small HTML page. Yes / No / Maybe sit at the bottom, below the meeting link: each opens a ready-written reply to the host's
    mailbox (press Send), so nothing opens a web page. The mail program's own Yes / No / Maybe buttons at the top work as well."""
    from html import escape
    r = f"{base}/#/rsvp/{make_token(m.id, email)}"
    body = escape(text.strip()).replace("\n", "<br>")
    if join_url: body = body.replace(escape(join_url), f'<a href="{escape(join_url)}">{escape(join_url)}</a>')
    def btn(label, word, status, strong=False):
        href = "mailto:" + quote(host) + "?" + urlencode({"subject": f"{word}: {m.title}", "body": f"Just press Send.\n\nisift-reply:{m.id}:{status}:"}, quote_via=quote) if host else f"{base}/api/v1/rsvp/{make_token(m.id, email)}/answer/{status}"
        st = "background:#1a56db;color:#fff" if strong else "background:#fff;color:#1a56db"
        return f'<a href="{href}" style="display:inline-block;margin:0 8px 8px 0;padding:9px 22px;border:1px solid #1a56db;border-radius:6px;{st};text-decoration:none;font-weight:600">{label}</a>'
    lk = lambda label, q: f'<a href="{r}?r={q}" style="color:#1a56db">{label}</a>'
    return ('<div style="font:15px/1.5 Arial,Helvetica,sans-serif;color:#202124">' + body +
            '<p style="margin:20px 0 8px;color:#5f6368">Will you join?</p><div>' + btn("Yes", "Accepted", "accepted", True) + btn("No", "Declined", "declined") + btn("Maybe", "Maybe", "tentative") + "</div>"
            '<p style="margin:6px 0 0;color:#5f6368;font-size:13px">' + ("Each button opens a short reply to the host: just press Send." if host else "One tap on a button records your answer and tells the host.") + ' You can also ' + lk("suggest another time", "proposed") + " or " + f'<a href="{base}/api/v1/rsvp/{make_token(m.id, email)}/calendar" target="_blank" style="color:#1a56db">add it to a calendar</a>' + ".</p></div>")

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
    (Gmail, Outlook, Microsoft 365, Yahoo, a company mailbox: any kind).
    If it is not connected, the invitation goes out the way Zoom's does: from the app's address as "Name via iSift", replies set to the host, and the
    Yes / No / Maybe links record the answer in iSift, which emails the host. allow_app is for notices to the host themselves, which may use any of their mailboxes or the app's sender."""
    from app.api.routes_booking import _senders
    out = await _senders(db, user)
    own = [a for a in out if not a.get("platform")]
    mine = [a for a in own if (a.get("address") or "").lower() == (user.email or "").lower()]
    if mine: return mine[:1]
    name = (getattr(user, "display_name", "") or "").replace('"', "").strip()
    app = []
    for a in out:
        if a.get("platform"):
            a = dict(a); a["from"] = f'{name or user.email} via iSift <{a.get("address")}>'; a["reply_to"] = user.email; app.append(a)
    return app + (own if allow_app else [])         # notices to the host: iSift's own address first (signed for isift.au), their mailboxes only as a fallback

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
                await mailer.send(a, [r], subject, body + footer(base, m, r, join_url, details), oi, html=html_body(body, base, m, r, join_url, "" if a.get("platform") else (a.get("address") or ""))); err = None; used.append((r, a.get("address"))); break
            except mailer.MailError as exc: err = exc; skipped.append(f"{a.get('address')}: {exc}")
        if err: raise err
    return {"used": used, "skipped": skipped}

async def tell_host(db, m, host, who: str, status: str, proposed: str, note: str, tz_name: str) -> str:
    """Email the host that someone replied. Uses the app's own sender, or the host's connected mail account."""
    from app.integrations import mail as mailer
    from app.services import signup, calendar_sync as cal
    accts = await senders(db, host, allow_app=True)
    if not accts:
        log.warning("Reply from %s to %s not emailed: no mail account is set up", who, m.title); return "No email account is set up to send from, so the host was not emailed."
    try:
        from sqlalchemy import select, func
        from app.models import User as _U
        u = (await db.execute(select(_U).where(func.lower(_U.email) == who.lower()))).scalars().first()
        names = [(getattr(u, "display_name", "") or "").strip() if u else ""]
        from app.models import Contact as _C
        names += [(c.name or "").strip() for c in (await db.execute(select(_C).where(_C.owner_id == host.id, func.lower(_C.email) == who.lower()))).scalars().all()]
        names = [n for n in names if n and n.lower() != who.lower() and "@" not in n]
        nm = max(names, key=lambda n: (len(n.split()), len(n))) if names else ""        # the fullest name known: the guest's own profile or the host's contact card
    except Exception: nm = ""
    shown_who = f"{nm} ({who})" if nm and nm.lower() != who.lower() else who
    body = f"{shown_who} {LABEL.get(status, status)} your meeting: {m.title}\n"
    if status == "proposed" and proposed: body += f"Suggested time: {proposed}\n"
    if note: body += f"Note: {note}\n"
    body += "\nOpen the meeting in iSift (Meetings, then the meeting) to see every reply"
    body += " and use the suggested time." if status == "proposed" else "."
    why = []
    for a in accts:
        if a.get("platform"): a = dict(a); a["from"] = f'iSift Meetings <{a.get("address")}>'; a.pop("reply_to", None)      # a notice from iSift, not "via iSift" in the guest's name
        try: await mailer.send(a, [host.email], f"{nm or who} {LABEL.get(status, status)}: {m.title}", body); return ""
        except Exception as exc:
            log.exception("Could not email the host about a reply (from %s)", a.get("address")); why.append(f"{a.get('address')}: {str(exc)[:160]}")
    return "The host could not be emailed (" + " | ".join(why) + ")."


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
        try: pairs = await asyncio.wait_for(mailer.find_button_replies(a), 20)
        except Exception: continue
        for who, text in pairs:
            mm = re.search(r"isift-reply:([\w-]+):(accepted|declined|tentative):", text or "")
            if not mm or mm.group(1) != m.id or not who: continue
            old = v["responses"].get(who)
            if old and old.get("status") == mm.group(2): continue
            await record(db, m.id, who, mm.group(2)); v = await load(db, m.id); n += 1
    return n


def sent_from(res: dict, user) -> str:
    """A short phrase for the confirmation: which mailbox sent it, and why your own mailbox was skipped, if it was."""
    used = {a for _r, a in res.get("used", []) if a}
    out = f" (from {', '.join(sorted(used))})" if used else ""
    if used and (user.email or "").lower() not in {u.lower() for u in used} and res.get("skipped"):
        out += f". Your own mailbox could not send: {res['skipped'][0]}"
    return out
