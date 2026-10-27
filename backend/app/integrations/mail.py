"""A person's own mailbox (Gmail, Yahoo, Outlook.com, iCloud or any SMTP/IMAP server), used for two things only:
sending meeting invitations on their behalf, and picking up calendar invitations (iCalendar attachments) from the inbox.
Message text is never stored: only the calendar data inside invitations is read.
"""
import asyncio, base64, email, imaplib, re, smtplib, socket, ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email import policy
from app.integrations import ics_feed
from app.core.config import settings

class MailError(RuntimeError): pass

PRESETS = {
    "gmail": {"label": "Gmail", "smtp": ("smtp.gmail.com", 587), "imap": ("imap.gmail.com", 993), "how": "Google Account > Security > 2-Step Verification > App passwords. Use your full Gmail address and the 16-letter app password."},
    "yahoo": {"label": "Yahoo Mail", "smtp": ("smtp.mail.yahoo.com", 587), "imap": ("imap.mail.yahoo.com", 993), "how": "Yahoo Account Security > Generate app password."},
    "outlook": {"label": "Outlook.com / Hotmail", "smtp": ("smtp-mail.outlook.com", 587), "imap": ("outlook.office365.com", 993), "how": "account.microsoft.com > Security > Advanced security options > App passwords (needs two-step verification). Work/school Microsoft 365 accounts usually block this; ask your administrator."},
    "icloud": {"label": "Apple iCloud Mail", "smtp": ("smtp.mail.me.com", 587), "imap": ("imap.mail.me.com", 993), "how": "appleid.apple.com > App-Specific Passwords."},
    "isiftmail": {"label": "isiftmail", "smtp": ("", 587), "imap": ("", 993), "how": "A free iSift address. It is created and managed by iSift, not added by hand."},
    "other": {"label": "Other (SMTP / IMAP)", "smtp": ("", 587), "imap": ("", 993), "how": "Your mail provider's SMTP (sending) and IMAP (reading) server names and ports."},
}
ALLOWED_PORTS = {25, 465, 587, 2525, 143, 993}

def clean_host(host: str) -> str:
    """Tidy a pasted server name: drop scheme, path, :port, spaces and invisible characters."""
    h = "".join(ch for ch in str(host or "") if ch.isprintable() and not ch.isspace() and ch not in "\u200b\u200c\u200d\ufeff\u00a0")
    h = re.sub(r"^[a-z][a-z0-9+.-]*://", "", h, flags=re.I).split("/")[0].split("?")[0]
    if "@" in h: h = h.rsplit("@", 1)[1]
    if h.count(":") == 1: h = h.split(":")[0]
    return h.strip(".").lower()

def _check(host: str, port: int):
    if not host or port not in ALLOWED_PORTS: raise MailError("That mail server address or port is not allowed.")
    own = {h.strip().lower() for h in (settings.isiftmail_imap_host, settings.isiftmail_smtp_host) if (h or "").strip()}      # iSift's own mail server (isiftmail) may sit on a private network
    if not settings.calendar_feed_allow_private and host.lower() not in own:
        try: public = ics_feed._public(host)
        except ics_feed.FeedError: raise MailError(f"The server name \"{host}\" was not found. Check it for typos.")
        if not public: raise MailError("That mail server is not a public address, so it was refused.")

def _smtp_connect(acct: dict):
    host, port = clean_host(acct["smtp_host"]), int(acct["smtp_port"]); _check(host, port)
    try:
        if port == 465: s = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            s = smtplib.SMTP(host, port, timeout=20); s.ehlo()
            if s.has_extn("starttls"): s.starttls(context=ssl.create_default_context()); s.ehlo()   # encrypt whenever the server offers it
        if acct.get("access_token"):
            from app.integrations import oauth
            code, resp = s.docmd("AUTH", "XOAUTH2 " + base64.b64encode(oauth.xoauth2(acct["address"], acct["access_token"]).encode()).decode())
            if code != 235: raise MailError("The mail server refused the sign-in. Sign in to this account again.")
        elif acct.get("username"): s.login(acct["username"], acct["password"])
        return s
    except smtplib.SMTPAuthenticationError: raise MailError("The mail server refused the sign-in. Use an app password and your full address.")
    except socket.gaierror: raise MailError(f"The sending server name \"{host}\" was not found. Check it for typos (for example smtpout.secureserver.net).")
    except (smtplib.SMTPException, OSError) as exc: raise MailError(f"Could not use the sending server {host}:{port} ({type(exc).__name__}).")

def _send_sync(acct: dict, to: list[str], subject: str, body: str, ics: bytes | None = None, method: str = "REQUEST", attachments: list | None = None, html: str | None = None):
    msg = EmailMessage(); msg["From"] = acct.get("from") or acct["address"];
    if acct.get("reply_to"): msg["Reply-To"] = acct["reply_to"]
    msg["To"] = ", ".join(to); msg["Subject"] = subject; msg.set_content(body)
    # Headers that mail filters expect from a genuine sender: a date and a message id from the sender's own domain.
    msg["Date"] = email.utils.formatdate(localtime=False); msg["Message-ID"] = email.utils.make_msgid(domain=(msg["From"].rsplit("@", 1)[-1].strip(" >") or "isift.au"))
    msg["Auto-Submitted"] = "auto-generated"
    if html: msg.add_alternative(html, subtype="html")
    if ics:
        # The calendar part sits inline beside the text (multipart/alternative) so Gmail, Outlook and Apple Mail show Accept / Decline / Maybe
        # and put the event in the person's calendar; the same file is attached for programs that only look for an attachment.
        msg.add_alternative(ics.decode("utf-8"), subtype="calendar", params={"method": method})
        msg.add_attachment(ics, maintype="application", subtype="ics", filename="invite.ics")
    for fname, data, mime in attachments or []:                      # (file name, bytes, "type/subtype")
        mt, st = mime.split("/", 1); msg.add_attachment(data, maintype=mt, subtype=st, filename=fname)
    s = _smtp_connect(acct)
    try: s.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc: raise MailError(f"The message could not be sent ({type(exc).__name__}).")
    finally:
        try: s.quit()
        except Exception: pass

async def _send_resend(acct: dict, to: list[str], subject: str, body: str, ics: bytes | None, attachments: list | None, html: str | None = None):
    import httpx
    j = {"from": acct.get("from") or acct["address"], "to": to, "subject": subject, "text": body}
    if html: j["html"] = html
    if acct.get("reply_to"): j["reply_to"] = acct["reply_to"]
    files = [{"filename": "invite.ics", "content": base64.b64encode(ics).decode(), "content_type": "text/calendar"}] if ics else []
    files += [{"filename": f, "content": base64.b64encode(d).decode()} for f, d, _m in attachments or []]
    if files: j["attachments"] = files
    try:
        async with httpx.AsyncClient(timeout=20) as c: r = await c.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {acct['resend_key']}"}, json=j)
    except httpx.HTTPError as exc: raise MailError(f"Could not reach the email service ({type(exc).__name__}).")
    if r.status_code >= 400:
        try: why = r.json().get("message") or r.text
        except Exception: why = r.text
        raise MailError(f"The email service refused the message: {str(why)[:160]}")

async def send(acct: dict, to: list[str], subject: str, body: str, ics: bytes | None = None, attachments: list | None = None, html: str | None = None):
    if acct.get("resend_key"): return await _send_resend(acct, to, subject, body, ics, attachments, html)
    await asyncio.to_thread(_send_sync, acct, to, subject, body, ics, "REQUEST", attachments, html)

def _imap_connect(acct: dict):
    host, port = clean_host(acct["imap_host"]), int(acct["imap_port"]); _check(host, port)
    try:
        m = imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context(), timeout=25) if port != 143 else imaplib.IMAP4(host, port, timeout=25)
        if acct.get("access_token"):
            from app.integrations import oauth
            m.authenticate("XOAUTH2", lambda _: oauth.xoauth2(acct["address"], acct["access_token"]).encode())
        else: m.login(acct["username"], acct["password"])
        return m
    except imaplib.IMAP4.error: raise MailError("The mailbox refused the sign-in. Use an app password and your full address.")
    except socket.gaierror: raise MailError(f"The reading server name \"{host}\" was not found. Check it for typos (for example imap.secureserver.net).")
    except OSError as exc: raise MailError(f"Could not reach the mailbox at {host}:{port} ({type(exc).__name__}).")

def _calendar_parts(raw: bytes) -> list[str]:
    msg = email.message_from_bytes(raw, policy=policy.default); out = []
    for part in msg.walk():
        name = (part.get_filename() or "").lower()
        if part.get_content_type() == "text/calendar" or name.endswith(".ics"):
            try: txt = part.get_content() if part.get_content_maintype() == "text" else part.get_payload(decode=True).decode("utf-8", "ignore")
            except Exception: continue
            if isinstance(txt, str) and "BEGIN:VEVENT" in txt.upper(): out.append(txt)
    return out

def _find_invites_sync(acct: dict, days: int = 30, limit: int = 60) -> list[str]:
    m = _imap_connect(acct); out = []
    try:
        m.select("INBOX", readonly=True)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = m.search(None, "SINCE", since, "TEXT", "BEGIN:VCALENDAR")
        ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-limit:]
        for i in ids:
            typ, parts = m.fetch(i, "(BODY.PEEK[])")          # PEEK: never marks mail as read
            if typ != "OK": continue
            for p in parts:
                if isinstance(p, tuple) and len(p[1]) < 3_000_000: out += _calendar_parts(p[1])
    except imaplib.IMAP4.error as exc: raise MailError(f"The mailbox could not be searched ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass
    return out

async def find_invites(acct: dict, days: int = 30) -> str:
    texts = await asyncio.to_thread(_find_invites_sync, acct, days)
    return "\n".join(texts) if texts else "BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n"

def _find_replies_sync(acct: dict, days: int = 14, limit: int = 80) -> list[str]:
    """Calendar replies (Yes / No / Maybe pressed inside Gmail, Outlook, Apple Mail, Yahoo) that reached this mailbox."""
    m = _imap_connect(acct); out = []
    try:
        m.select("INBOX", readonly=True)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = m.search(None, "SINCE", since, "TEXT", "METHOD:REPLY")
        ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-limit:]
        for i in ids:
            typ, parts = m.fetch(i, "(BODY.PEEK[])")
            if typ != "OK": continue
            for p in parts:
                if isinstance(p, tuple) and len(p[1]) < 3_000_000: out += [t for t in _calendar_parts(p[1]) if "METHOD:REPLY" in t.upper()]
    except imaplib.IMAP4.error as exc: raise MailError(f"The mailbox could not be searched ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass
    return out

def _find_button_replies_sync(acct: dict, days: int = 14, limit: int = 80) -> list[tuple[str, str]]:
    """Answers sent with the Yes / No / Maybe buttons at the bottom of the invitation email: (sender address, message text)."""
    m = _imap_connect(acct); out = []
    try:
        m.select("INBOX", readonly=True)
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = m.search(None, "SINCE", since, "TEXT", "isift-reply")
        ids = (data[0].split() if typ == "OK" and data and data[0] else [])[-limit:]
        for i in ids:
            typ, parts = m.fetch(i, "(BODY.PEEK[])")
            if typ != "OK": continue
            for p in parts:
                if isinstance(p, tuple) and len(p[1]) < 3_000_000:
                    msg = email.message_from_bytes(p[1], policy=policy.default); body = msg.get_body(preferencelist=("plain",))
                    try: text = body.get_content() if body else ""
                    except Exception: text = ""
                    out.append((email.utils.parseaddr(str(msg.get("From", "")))[1].lower(), text))
    except imaplib.IMAP4.error as exc: raise MailError(f"The mailbox could not be searched ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass
    return out

async def find_button_replies(acct: dict, days: int = 14) -> list[tuple[str, str]]: return await asyncio.to_thread(_find_button_replies_sync, acct, days)

async def find_replies(acct: dict, days: int = 14) -> list[str]: return await asyncio.to_thread(_find_replies_sync, acct, days)

def _test_sync(acct: dict):
    s = _smtp_connect(acct)
    try: s.quit()
    except Exception: pass
    if acct.get("imap_host"):
        m = _imap_connect(acct)
        try: m.logout()
        except Exception: pass

async def test(acct: dict): await asyncio.to_thread(_test_sync, acct)
