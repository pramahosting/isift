"""Reading and organising a person's mail over IMAP (Gmail, Yahoo, iCloud, Outlook.com or any server) and sending through SMTP.
Used by the Mail page. Messages are fetched live and are not stored in iSift; only the account details are (the password encrypted)."""
import asyncio, base64, email, imaplib, re, time
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime, formatdate, make_msgid
from html.parser import HTMLParser
from app.integrations import mail as base
from app.integrations.mail import MailError

# ---- folder names use "modified UTF-7" ----
def utf7_decode(s: str) -> str:
    def rep(m):
        b = m.group(1)
        if b == "": return "&"
        b = b.replace(",", "/")
        try: return base64.b64decode(b + "=" * (-len(b) % 4)).decode("utf-16-be")
        except Exception: return m.group(0)
    return re.sub(r"&([^-]*)-", rep, s)

def utf7_encode(s: str) -> str:
    out, buf = [], ""
    def flush():
        nonlocal buf
        if buf:
            out.append("&" + base64.b64encode(buf.encode("utf-16-be")).decode().rstrip("=").replace("/", ",") + "-"); buf = ""
    for ch in s:
        if 0x20 <= ord(ch) <= 0x7e:
            flush(); out.append("&-" if ch == "&" else ch)
        else: buf += ch
    flush(); return "".join(out)

def _q(name: str) -> str:
    return '"' + utf7_encode(name).replace("\\", "\\\\").replace('"', '\\"') + '"'

ROLE_FLAGS = {"\\sent": "sent", "\\drafts": "drafts", "\\trash": "trash", "\\junk": "junk", "\\archive": "archive", "\\all": "all", "\\flagged": "flagged"}
ROLE_NAMES = {"inbox": "inbox", "sent": "sent", "sent items": "sent", "sent mail": "sent", "sent messages": "sent", "drafts": "drafts", "draft": "drafts",
              "trash": "trash", "deleted": "trash", "deleted items": "trash", "deleted messages": "trash", "bin": "trash",
              "junk": "junk", "junk email": "junk", "junk e-mail": "junk", "spam": "junk", "bulk mail": "junk", "archive": "archive", "archives": "archive", "all mail": "all"}
ROLE_ORDER = ["inbox", "drafts", "sent", "archive", "junk", "trash"]
LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\)\s+(?P<delim>"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$')

def parse_list(lines) -> list[dict]:
    out = []
    for ln in lines or []:
        if not isinstance(ln, (bytes, bytearray)): continue
        m = LIST_RE.match(bytes(ln).strip())
        if not m: continue
        flags = [f.lower() for f in m["flags"].decode("ascii", "ignore").split()]
        if "\\noselect" in flags or "\\nonexistent" in flags: continue
        raw = m["name"].decode("utf-8", "ignore").strip()
        if raw.startswith('"') and raw.endswith('"'): raw = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        name = utf7_decode(raw); role = next((ROLE_FLAGS[f] for f in flags if f in ROLE_FLAGS), "")
        if not role: role = ROLE_NAMES.get(name.split("/")[-1].split(".")[-1].strip().lower() if name.upper() != "INBOX" else "inbox", "")
        if name.upper() == "INBOX": role = "inbox"
        out.append({"name": name, "role": role, "raw": raw})
    return out

def _plain(html: str) -> str:
    class P(HTMLParser):
        def __init__(s): super().__init__(); s.t = []; s.skip = 0
        def handle_starttag(s, tag, a):
            if tag in ("script", "style", "head"): s.skip += 1
            if tag in ("br", "p", "div", "tr", "li", "h1", "h2", "h3"): s.t.append("\n")
        def handle_endtag(s, tag):
            if tag in ("script", "style", "head") and s.skip: s.skip -= 1
        def handle_data(s, d):
            if not s.skip: s.t.append(d)
    p = P()
    try: p.feed(html)
    except Exception: pass
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t ]+", " ", "".join(p.t))).strip()

def _hdr(msg, name: str) -> str:
    try: return str(msg.get(name, "") or "").replace("\r", "").replace("\n", " ").strip()
    except Exception: return ""

def _who(value: str) -> str:
    from email.utils import parseaddr
    n, a = parseaddr(value or ""); return n or a or ""

def _iso(value: str) -> str | None:
    try: return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception: return None

def _preview(raw: bytes) -> str:
    import quopri
    t = raw.decode("utf-8", "ignore")
    if re.search(r"=[0-9A-F]{2}", t):
        try: t = quopri.decodestring(raw).decode("utf-8", "ignore")
        except Exception: pass
    if "<" in t and ">" in t: t = _plain(t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > 60 and " " not in t[:60]: return ""      # an encoded blob, not text
    return t[:160]

def _connect(acct): return base._imap_connect(acct)

def _open(m, folder: str, readonly=True):
    typ, _ = m.select(_q(folder), readonly=readonly)
    if typ != "OK": raise MailError("That folder could not be opened.")

# ---------------------------------------------------------------- folders
def folders_sync(acct: dict) -> list[dict]:
    m = _connect(acct)
    try:
        typ, data = m.list()
        fs = parse_list(data if typ == "OK" else [])
        if not any(f["role"] == "inbox" for f in fs): fs.insert(0, {"name": "INBOX", "role": "inbox", "raw": "INBOX"})
        fs = [f for f in fs if f["role"] not in ("all", "flagged")]      # Gmail's "All Mail" and "Starred" are duplicate views
        for f in fs[:40]:
            try:
                typ, d = m.status(_q(f["name"]), "(UNSEEN)"); mm = re.search(rb"UNSEEN (\d+)", d[0] or b"") if typ == "OK" else None
                f["unread"] = int(mm.group(1)) if mm else 0
            except Exception: f["unread"] = 0
        fs.sort(key=lambda f: (ROLE_ORDER.index(f["role"]) if f["role"] in ROLE_ORDER else 99, f["name"].lower()))
        return [{"name": f["name"], "role": f["role"], "unread": f.get("unread", 0)} for f in fs]
    except imaplib.IMAP4.error as exc: raise MailError(f"The folders could not be read ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass

# ---------------------------------------------------------------- message list
def _parse_fetch(data) -> list[dict]:
    """Turns imaplib's FETCH reply into rows. UID and FLAGS may come before or after the literals, depending on the server."""
    out: list[dict] = []
    def meta_into(row, text: str):
        um = re.search(r"UID (\d+)", text)
        if um and not row.get("uid"): row["uid"] = int(um.group(1))
        fm = re.search(r"FLAGS \(([^)]*)\)", text)
        if fm:
            flags = fm.group(1).lower().split(); row["unread"] = "\\seen" not in flags; row["flagged"] = "\\flagged" in flags
    for item in data or []:
        if isinstance(item, tuple):
            meta = item[0].decode("ascii", "ignore"); up = meta.upper()
            if "HEADER.FIELDS" in up:
                msg = email.message_from_bytes(item[1], policy=policy.default)
                row = {"uid": 0, "from": _who(_hdr(msg, "From")), "from_addr": _hdr(msg, "From"), "subject": _hdr(msg, "Subject") or "(no subject)", "at": _iso(_hdr(msg, "Date")), "unread": True, "flagged": False, "preview": ""}
                meta_into(row, meta); out.append(row)
            elif "BODY[TEXT]" in up and out:
                out[-1]["preview"] = _preview(item[1]); meta_into(out[-1], meta)
        elif isinstance(item, (bytes, bytearray)) and out:
            meta_into(out[-1], bytes(item).decode("ascii", "ignore"))
    return [r for r in out if r["uid"]]

def messages_sync(acct: dict, folder: str, q: str = "", limit: int = 40, before_uid: int = 0) -> dict:
    m = _connect(acct)
    try:
        _open(m, folder)
        q = re.sub(r'["\\\r\n]', " ", q or "").strip()
        crit = ["ALL"]
        if q and q.isascii(): crit = ["OR", "OR", "SUBJECT", f'"{q}"', "FROM", f'"{q}"', "BODY", f'"{q}"']
        typ, d = m.uid("search", None, *crit)
        uids = [int(x) for x in (d[0].split() if typ == "OK" and d and d[0] else [])]
        uids.sort(reverse=True)
        if before_uid: uids = [u for u in uids if u < before_uid]
        total_more = len(uids) > limit; pick = uids[:limit]
        if not pick: return {"messages": [], "more": False}
        typ, data = m.uid("fetch", ",".join(map(str, pick)), "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] BODY.PEEK[TEXT]<0.400>)")
        rows = _parse_fetch(data if typ == "OK" else [])
        rows.sort(key=lambda r: -r["uid"])
        if q and not q.isascii(): rows = [r for r in rows if q.lower() in (r["subject"] + " " + r["from"] + " " + r["preview"]).lower()]
        return {"messages": rows, "more": total_more}
    except imaplib.IMAP4.error as exc: raise MailError(f"The messages could not be read ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass

# ---------------------------------------------------------------- one message
def message_sync(acct: dict, folder: str, uid: int, mark_read: bool = True) -> dict:
    m = _connect(acct)
    try:
        _open(m, folder, readonly=not mark_read)
        typ, data = m.uid("fetch", str(uid), "(FLAGS BODY.PEEK[])")
        raw = next((p[1] for p in data or [] if isinstance(p, tuple)), None)
        if typ != "OK" or raw is None: raise MailError("That message was not found. It may have been moved.")
        if len(raw) > 8_000_000: raise MailError("That message is too large to show here.")
        msg = email.message_from_bytes(raw, policy=policy.default)
        body = msg.get_body(preferencelist=("plain", "html")); text = ""; was_html = False
        if body is not None:
            try: text = body.get_content()
            except Exception: text = ""
            if body.get_content_subtype() == "html": text = _plain(text); was_html = True
        atts = []
        for part in msg.iter_attachments():
            try: atts.append({"name": part.get_filename() or "attachment", "size": len(part.get_payload(decode=True) or b"")})
            except Exception: pass
        if mark_read:
            try: m.uid("store", str(uid), "+FLAGS", "(\\Seen)")
            except Exception: pass
        return {"uid": uid, "from": _hdr(msg, "From"), "to": _hdr(msg, "To"), "cc": _hdr(msg, "Cc"), "subject": _hdr(msg, "Subject") or "(no subject)", "at": _iso(_hdr(msg, "Date")),
                "message_id": _hdr(msg, "Message-ID"), "text": text[:200_000], "attachments": atts, "reply_to": _hdr(msg, "Reply-To") or _hdr(msg, "From"), "html": was_html}
    except imaplib.IMAP4.error as exc: raise MailError(f"The message could not be read ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass

# ---------------------------------------------------------------- actions
def _folder_for(m, acct, role: str) -> str:
    typ, data = m.list(); fs = parse_list(data if typ == "OK" else [])
    for want in ([role, "all"] if role == "archive" else [role]):
        f = next((f for f in fs if f["role"] == want), None)
        if f: return f["name"]
    default = {"archive": "Archive", "junk": "Junk", "trash": "Trash"}.get(role, role.title())
    m.create(_q(default)); return default

def act_sync(acct: dict, folder: str, uids: list[int], action: str, target: str = "") -> dict:
    uids = [int(u) for u in uids][:200]
    if not uids: return {"ok": True, "count": 0}
    s = ",".join(map(str, uids)); m = _connect(acct)
    try:
        _open(m, folder, readonly=False)
        if action in ("read", "unread"):
            m.uid("store", s, "+FLAGS" if action == "read" else "-FLAGS", "(\\Seen)"); return {"ok": True, "count": len(uids)}
        if action in ("flag", "unflag"):
            m.uid("store", s, "+FLAGS" if action == "flag" else "-FLAGS", "(\\Flagged)"); return {"ok": True, "count": len(uids)}
        typ, data = m.list(); fs = parse_list(data if typ == "OK" else [])
        here = next((f for f in fs if f["name"] == folder), {"role": ""})
        if action == "delete":
            if here["role"] == "trash":
                m.uid("store", s, "+FLAGS", "(\\Deleted)"); m.expunge(); return {"ok": True, "count": len(uids), "permanent": True}
            dest = _folder_for(m, acct, "trash")
        elif action == "archive": dest = _folder_for(m, acct, "archive")
        elif action == "junk": dest = _folder_for(m, acct, "junk")
        elif action == "move":
            if not any(f["name"] == target for f in fs): raise MailError("That folder does not exist.")
            dest = target
        else: raise MailError("Unknown action.")
        if dest == folder: return {"ok": True, "count": 0}
        caps = b" ".join(getattr(m, "capabilities", ()) and [c if isinstance(c, bytes) else str(c).encode() for c in m.capabilities] or [])
        if b"MOVE" in caps.upper(): typ, _ = m.uid("MOVE", s, _q(dest))
        else:
            typ, _ = m.uid("copy", s, _q(dest))
            if typ == "OK": m.uid("store", s, "+FLAGS", "(\\Deleted)"); m.expunge()
        if typ != "OK": raise MailError("The messages could not be moved.")
        return {"ok": True, "count": len(uids), "to": dest}
    except imaplib.IMAP4.error as exc: raise MailError(f"That could not be done ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass

# ---------------------------------------------------------------- sending
def send_sync(acct: dict, to: list[str], cc: list[str], subject: str, body: str, in_reply_to: str = "") -> None:
    msg = EmailMessage(); msg["From"] = acct["address"]; msg["To"] = ", ".join(to)
    if cc: msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject; msg["Date"] = formatdate(localtime=True); msg["Message-ID"] = make_msgid()
    if in_reply_to: msg["In-Reply-To"] = in_reply_to; msg["References"] = in_reply_to
    msg.set_content(body)
    s = base._smtp_connect(acct)
    try: s.send_message(msg, to_addrs=to + cc)
    except Exception as exc: raise MailError(f"The message could not be sent ({type(exc).__name__}).")
    finally:
        try: s.quit()
        except Exception: pass
    if acct.get("provider") != "gmail":                    # Gmail files sent mail itself; others need a copy in Sent
        try:
            m = _connect(acct)
            try:
                typ, data = m.list(); sent = next((f["name"] for f in parse_list(data if typ == "OK" else []) if f["role"] == "sent"), "")
                if sent: m.append(_q(sent), "\\Seen", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            finally:
                try: m.logout()
                except Exception: pass
        except Exception: pass

async def folders(acct): return await asyncio.to_thread(folders_sync, acct)
async def messages(acct, folder, q="", limit=40, before_uid=0): return await asyncio.to_thread(messages_sync, acct, folder, q, limit, before_uid)
async def message(acct, folder, uid, mark_read=True): return await asyncio.to_thread(message_sync, acct, folder, uid, mark_read)
async def act(acct, folder, uids, action, target=""): return await asyncio.to_thread(act_sync, acct, folder, uids, action, target)
async def send(acct, to, cc, subject, body, in_reply_to=""): return await asyncio.to_thread(send_sync, acct, to, cc, subject, body, in_reply_to)
