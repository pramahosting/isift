"""isiftmail: free iSift email addresses (name@your-domain) for people who have no email of their own.

The mail itself lives on a Stalwart mail server that you run (see docs/ISIFTMAIL.md). iSift talks to it in three ways:
  * its management address, to create, change the password of and close a mailbox          (Stalwart REST API, version 0.15 and earlier)
  * IMAP and SMTP, exactly like any other account in Commbox (reading, sending, deleting, folders)
  * ManageSieve, to switch an auto-reply (vacation message) on and off for one person

Everything that depends on the mail server's version is in this one file, so a future Stalwart change touches only here.
Outgoing mail is passed on to the outbound relay by the mail server itself; iSift never holds the relay's login.
"""
import asyncio, base64, imaplib, re, secrets, socket, ssl, time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from app.core.config import settings
from app.integrations.mail import MailError
from app.integrations import mailbox as mb

PROVIDER = "isiftmail"

# People who sign in with one of these already have email, so isiftmail is not offered to them first.
KNOWN_PROVIDERS = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "office365.com", "yahoo.com", "ymail.com", "rocketmail.com",
                   "yahoo.com.au", "yahoo.co.uk", "hotmail.co.uk", "outlook.com.au", "hotmail.com.au", "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com",
                   "zoho.com", "gmx.com", "gmx.net", "mail.com", "fastmail.com", "bigpond.com", "optusnet.com.au", "tpg.com.au", "iinet.net.au"}
RESERVED = {"admin", "administrator", "root", "postmaster", "abuse", "hostmaster", "webmaster", "noreply", "no-reply", "mailer-daemon", "support", "info", "sales", "billing",
            "security", "help", "contact", "mail", "email", "isift", "isiftmail", "staff", "team", "ceo", "office", "accounts", "privacy", "legal", "www", "ftp", "smtp", "imap", "test"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,28}[a-z0-9]$")

# ---------------------------------------------------------------- settings
def domain() -> str: return (settings.isiftmail_domain or "").strip().lower().lstrip("@")
def configured() -> bool:
    return bool(domain() and (settings.isiftmail_api_url or "").strip() and (settings.isiftmail_imap_host or "").strip() and (settings.isiftmail_smtp_host or "").strip())
def trusted_hosts() -> set[str]:
    """The mail server is ours, so it may sit on a private address (same machine or private network)."""
    return {h.strip().lower() for h in (settings.isiftmail_imap_host, settings.isiftmail_smtp_host) if (h or "").strip()}

def valid_name(raw: str, reserved: bool = True) -> str:
    """reserved=False on a person's own domain, where info@ and postmaster@ are theirs to use."""
    n = str(raw or "").strip().lower().split("@")[0]
    if not NAME_RE.match(n): raise ValueError("Use 3 to 30 letters, numbers, dots, dashes or underscores, starting and ending with a letter or number.")
    if ".." in n or "--" in n or "__" in n or "._" in n or "_." in n or ".-" in n or "-." in n: raise ValueError("Please do not put two symbols next to each other.")
    if reserved and (n in RESERVED or n.startswith(("admin", "postmaster", "isift"))): raise ValueError("That name is reserved. Please choose another.")
    return n

def new_password() -> str: return secrets.token_urlsafe(18)

def principal_name(local: str, dom: str = "") -> str:
    """The login name on the mail server. On our own domain it is just the first part; on a person's own domain the domain is added so two people can both have 'info'."""
    dom = (dom or domain()).lower()
    return local if dom == domain() else f"{local}.{dom.replace('.', '-')}"

def account_dict(name: str, password_enc: str, address: str = "") -> dict:
    """The record Commbox keeps for the mailbox, in the same shape as any other account (the password is already encrypted)."""
    return {"provider": PROVIDER, "address": address or f"{name}@{domain()}", "username": name, "password": password_enc, "managed": True,
            "smtp_host": settings.isiftmail_smtp_host.strip(), "smtp_port": int(settings.isiftmail_smtp_port or 587),
            "imap_host": settings.isiftmail_imap_host.strip(), "imap_port": int(settings.isiftmail_imap_port or 993)}

# ---------------------------------------------------------------- the mail server's management address (Stalwart REST API)
async def _api(method: str, path: str, json=None):
    import httpx
    base = (settings.isiftmail_api_url or "").strip().rstrip("/")
    if not base: raise MailError("isiftmail is not set up yet.")
    user, pw = (settings.isiftmail_api_user or "").strip(), settings.isiftmail_api_password or ""
    headers = {} if user else {"Authorization": f"Bearer {pw}"}
    try:
        async with httpx.AsyncClient(timeout=15, auth=(user, pw) if user else None, headers=headers) as c:
            r = await c.request(method, base + path, json=json)
    except httpx.HTTPError as exc: raise MailError(f"The mail server could not be reached ({type(exc).__name__}).")
    if r.status_code in (401, 403): raise MailError("The mail server refused iSift's administrator login. Check it in Admin Console.")
    return r

def _err(r) -> str:
    try: j = r.json()
    except Exception: return ""
    return str(j.get("error") or "") if isinstance(j, dict) else ""

async def exists(name: str) -> bool:
    r = await _api("GET", f"/api/principal/{name}")
    if r.status_code == 404 or _err(r) == "notFound": return False
    if r.status_code >= 500: raise MailError("The mail server had a problem. Try again in a moment.")
    return r.status_code == 200 and not _err(r)

async def create(name: str, password: str, display: str = "", address: str = "") -> None:
    body = {"type": "individual", "name": name, "secrets": [password], "emails": [address or f"{name}@{domain()}"], "quota": int(settings.isiftmail_quota_mb or 2048) * 1048576,
            "description": (display or name)[:80]}
    r = await _api("POST", "/api/principal", body)
    e = _err(r)
    if e in ("fieldAlreadyExists", "alreadyExists") or r.status_code == 409: raise MailError("That name has just been taken. Please choose another.")
    if e or r.status_code >= 400: raise MailError(f"The mailbox could not be created ({e or r.status_code}).")

async def set_password(name: str, password: str) -> None:
    r = await _api("PATCH", f"/api/principal/{name}", [{"action": "set", "field": "secrets", "value": [password]}])
    if _err(r) or r.status_code >= 400: raise MailError("The password could not be changed.")

async def remove(name: str) -> None:
    r = await _api("DELETE", f"/api/principal/{name}")
    if r.status_code == 404 or _err(r) == "notFound": return
    if _err(r) or r.status_code >= 400: raise MailError("The mailbox could not be closed.")

# ---------------------------------------------------------------- people's own domains (pramod@prama-ai.com hosted here)
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
BLOCKED_DOMAINS = KNOWN_PROVIDERS | {"isift.au", "example.com", "example.org", "example.net", "localhost", "test.com"}
DKIM_SELECTOR = "isift"

def valid_domain(raw: str) -> str:
    d = str(raw or "").strip().lower().rstrip(".")
    if d.startswith("www."): d = d[4:]
    if not DOMAIN_RE.match(d) or ".." in d: raise ValueError("That does not look like a domain name. Use something like your-company.com.")
    if d == domain() or d.endswith("." + domain()) or d in BLOCKED_DOMAINS or d.endswith(".local") or d.endswith(".test") or d.endswith(".invalid"): raise ValueError("That domain cannot be used here.")
    return d

def mx_host() -> str: return (settings.isiftmail_mx_host or settings.isiftmail_imap_host or "").strip().lower().rstrip(".")
def autoconfig_host() -> str: return (settings.isiftmail_autoconfig_host or "").strip().lower().rstrip(".") or mx_host()
def verify_name(dom: str) -> str: return f"_isiftmail-verify.{dom}"
def verify_value(token: str) -> str: return f"isiftmail-verify={token}"
def new_token() -> str: return secrets.token_hex(16)

async def create_domain(dom: str) -> None:
    r = await _api("POST", "/api/principal", {"type": "domain", "name": dom, "description": "isiftmail customer domain"})
    e = _err(r)
    if e in ("fieldAlreadyExists", "alreadyExists") or r.status_code == 409: return          # already there: fine
    if e or r.status_code >= 400: raise MailError(f"The domain could not be set up on the mail server ({e or r.status_code}).")

async def create_dkim(dom: str) -> None:
    """Asks the mail server to make a signing key for the domain, so mail from it is signed (DKIM). Failing is not fatal: the person is told the record is not ready."""
    try:
        r = await _api("POST", "/api/dkim", {"id": None, "algorithm": "Ed25519", "domain": dom, "selector": DKIM_SELECTOR})
    except MailError: return
    _ = r

async def remove_domain(dom: str) -> None:
    r = await _api("DELETE", f"/api/principal/{dom}")
    if r.status_code == 404 or _err(r) == "notFound": return
    if _err(r) or r.status_code >= 400: raise MailError("The domain could not be removed from the mail server.")

async def server_dns_records(dom: str) -> list[dict]:
    """The records the mail server itself says the domain needs (including its DKIM key), when it can say."""
    try: r = await _api("GET", f"/api/dns/records/{dom}")
    except MailError: return []
    if r.status_code != 200 or _err(r): return []
    try: data = r.json().get("data") or []
    except Exception: return []
    out = []
    for x in data if isinstance(data, list) else []:
        t = str(x.get("type") or "").upper(); n = str(x.get("name") or "").rstrip("."); v = str(x.get("content") or x.get("value") or "")
        if t and n and v: out.append({"type": t, "name": n, "value": v.rstrip(".") if t == "MX" else v})
    return out

def dns_records(dom: str, token: str, server: list[dict] | None = None) -> list[dict]:
    """What the person adds at their domain registrar. Ownership proof first, then mail delivery, then the records that keep mail out of spam."""
    recs = [{"purpose": "owner", "type": "TXT", "name": verify_name(dom), "value": verify_value(token), "required": True,
             "help": "Proves the domain is yours. Add this first."},
            {"purpose": "mx", "type": "MX", "name": dom, "value": f"10 {mx_host()}", "required": True, "help": "Sends mail for your domain to isiftmail."},
            {"purpose": "spf", "type": "TXT", "name": dom, "value": settings.isiftmail_spf or "v=spf1 mx ~all", "required": False, "help": "Says isiftmail may send mail for your domain. Replace any older SPF record, do not add a second one."}]
    dkim = next((x for x in (server or []) if x["type"] == "TXT" and "_domainkey" in x["name"]), None)
    if dkim: recs.append({"purpose": "dkim", "type": "TXT", "name": dkim["name"], "value": dkim["value"], "required": False, "help": "Signs your mail so others can trust it."})
    recs.append({"purpose": "dmarc", "type": "TXT", "name": f"_dmarc.{dom}", "value": f"v=DMARC1; p=none; rua=mailto:postmaster@{dom}", "required": False, "help": "Tells receivers what to do with mail that fails the checks. Start with p=none."})
    h = autoconfig_host()
    recs += [{"purpose": "autodiscover", "type": "CNAME", "name": f"autodiscover.{dom}", "value": h, "required": False, "help": "Lets Outlook set itself up from just the email address and password."},
             {"purpose": "autoconfig", "type": "CNAME", "name": f"autoconfig.{dom}", "value": h, "required": False, "help": "Lets Thunderbird, Apple Mail and phones set themselves up."},
             {"purpose": "srv", "type": "SRV", "name": f"_autodiscover._tcp.{dom}", "value": f"0 0 443 {h}", "required": False, "help": "A second way for Outlook to find its settings. It asks you to allow it once."}]
    return recs

def _resolve(name: str, rtype: str) -> list[str]:
    import dns.resolver, dns.exception
    try: ans = dns.resolver.resolve(name, rtype, lifetime=6)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers): return []
    except dns.exception.DNSException: raise MailError("The domain name system did not answer. Try again in a minute.")
    out = []
    for r in ans:
        if rtype == "TXT": out.append(b"".join(r.strings).decode("utf-8", "ignore"))
        elif rtype == "MX": out.append(str(r.exchange).rstrip(".").lower())
        elif rtype == "CNAME": out.append(str(r.target).rstrip(".").lower())
        elif rtype == "SRV": out.append(f"{r.priority} {r.weight} {r.port} {str(r.target).rstrip('.').lower()}")
    return out

async def lookup(name: str, rtype: str) -> list[str]: return await asyncio.to_thread(_resolve, name, rtype)

async def check_dns(dom: str, token: str, server: list[dict] | None = None) -> dict:
    """Looks each record up on the internet. 'owner' decides whether the domain is the person's; the rest say whether mail will flow and be trusted."""
    res = {}
    res["owner"] = verify_value(token) in await lookup(verify_name(dom), "TXT")
    mx = await lookup(dom, "MX"); res["mx"] = mx_host() in mx
    spf = [t for t in await lookup(dom, "TXT") if t.lower().startswith("v=spf1")]; res["spf"] = bool(spf) and all(tok in spf[0].split() for tok in (settings.isiftmail_spf or "").split() if tok.startswith("include:"))
    dk = next((x for x in (server or []) if x["type"] == "TXT" and "_domainkey" in x["name"]), None)
    res["dkim"] = bool(dk) and any(t.replace(" ", "") == dk["value"].replace(" ", "") for t in await lookup(dk["name"], "TXT"))
    res["dmarc"] = any(t.lower().startswith("v=dmarc1") for t in await lookup(f"_dmarc.{dom}", "TXT"))
    h = autoconfig_host()
    res["autodiscover"] = h in await lookup(f"autodiscover.{dom}", "CNAME")
    res["autoconfig"] = h in await lookup(f"autoconfig.{dom}", "CNAME")
    res["srv"] = any(x.split()[-1:] == [h] and x.split()[2:3] == ["443"] for x in await lookup(f"_autodiscover._tcp.{dom}", "SRV"))
    return res

# ---------------------------------------------------------------- auto-reply (a Sieve "vacation" rule, set over ManageSieve)
def _q(s: str) -> str: return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def vacation_script(subject: str, message: str, start: str = "", end: str = "") -> str:
    subject = re.sub(r"[\r\n]+", " ", str(subject or "Automatic reply")).strip()[:120] or "Automatic reply"
    message = str(message or "").replace("\r\n", "\n").strip()[:2000]
    if not message: raise ValueError("Write the message people will receive.")
    need, tests = ["vacation"], []
    if start:
        if not DATE.match(start): raise ValueError("The start date is not valid.")
        tests.append(f'currentdate :value "ge" "date" {_q(start)}')
    if end:
        if not DATE.match(end): raise ValueError("The end date is not valid.")
        tests.append(f'currentdate :value "le" "date" {_q(end)}')
    if start and end and end < start: raise ValueError("The end date is before the start date.")
    act = f"vacation :days 1 :subject {_q(subject)} {_q(message)};"
    if tests:
        need += ["date", "relational"]
        cond = tests[0] if len(tests) == 1 else "allof(" + ", ".join(tests) + ")"
        return "require [" + ", ".join(_q(n) for n in need) + f"];\r\nif {cond} {{\r\n  {act}\r\n}}\r\n"
    return "require [" + ", ".join(_q(n) for n in need) + f"];\r\n{act}\r\n"

class _Sieve:
    """The few ManageSieve (RFC 5804) commands needed, over a plain socket that is upgraded with STARTTLS."""
    def __init__(self, host: str, port: int, user: str, password: str):
        self.s = socket.create_connection((host, port), timeout=15); self.f = self.s.makefile("rwb"); self.host = host
        self._until_ok()
        self.s.sendall(b"STARTTLS\r\n"); self._until_ok()
        ctx = ssl.create_default_context(); self.s = ctx.wrap_socket(self.s, server_hostname=host); self.f = self.s.makefile("rwb")
        self._until_ok()                                                           # the capability list again, now encrypted
        tok = base64.b64encode(f"\0{user}\0{password}".encode()).decode()
        self.cmd(f'AUTHENTICATE "PLAIN" "{tok}"')
    def _until_ok(self) -> str:
        while True:
            line = self.f.readline()
            if not line: raise MailError("The mail server closed the connection.")
            t = line.decode("utf-8", "replace").strip()
            if t[:2].upper() == "OK": return t
            if t[:2].upper() in ("NO", "BY"): raise MailError("The mail server did not accept the auto-reply settings.")
    def cmd(self, line: str, literal: str | None = None) -> str:
        data = line.encode()
        if literal is not None:
            raw = literal.encode(); data += b" {%d+}\r\n" % len(raw) + raw
        self.f.write(data + b"\r\n"); self.f.flush(); return self._until_ok()
    def close(self):
        try: self.cmd("LOGOUT")
        except Exception: pass
        try: self.s.close()
        except Exception: pass

SCRIPT_NAME = "isift-autoreply"

def _sieve_sync(acct: dict, script: str | None) -> None:
    """script=None switches the auto-reply off; otherwise it is stored and made the active rule."""
    host = settings.isiftmail_imap_host.strip(); port = int(settings.isiftmail_sieve_port or 4190)
    try:
        c = _Sieve(host, port, acct["username"], acct["password"])
        try:
            if script is None: c.cmd('SETACTIVE ""')
            else:
                c.cmd(f'PUTSCRIPT "{SCRIPT_NAME}"', script); c.cmd(f'SETACTIVE "{SCRIPT_NAME}"')
        finally: c.close()
    except MailError: raise
    except (OSError, ssl.SSLError) as exc: raise MailError(f"Could not reach the mail server's auto-reply service ({type(exc).__name__}).")

async def apply_autoreply(acct: dict, script: str | None) -> None: await asyncio.to_thread(_sieve_sync, acct, script)

# ---------------------------------------------------------------- drafts
def save_draft_sync(acct: dict, to: list[str], cc: list[str], subject: str, body: str, replace_uid: int = 0) -> int:
    msg = EmailMessage(); msg["From"] = acct["address"]
    if to: msg["To"] = ", ".join(to)
    if cc: msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject or ""; msg["Date"] = formatdate(localtime=True); msg["Message-ID"] = make_msgid(); msg.set_content(body or "")
    m = mb._connect(acct)
    try:
        typ, data = m.list(); fs = mb.parse_list(data if typ == "OK" else [])
        name = next((f["name"] for f in fs if f["role"] == "drafts"), "")
        if not name:
            name = "Drafts"; m.create(mb._q(name))
        typ, resp = m.append(mb._q(name), "\\Draft", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
        if typ != "OK": raise MailError("The draft could not be saved.")
        uid = 0
        mm = re.search(rb"APPENDUID \d+ (\d+)", b" ".join(x for x in (resp or []) if isinstance(x, bytes)))
        if mm: uid = int(mm.group(1))
        if replace_uid:                                                            # the older copy of the same draft goes away
            try:
                m.select(mb._q(name)); m.uid("store", str(int(replace_uid)), "+FLAGS", "(\\Deleted)"); m.expunge()
            except Exception: pass
        return uid
    except imaplib.IMAP4.error as exc: raise MailError(f"The draft could not be saved ({exc}).")
    finally:
        try: m.logout()
        except Exception: pass

async def save_draft(acct, to, cc, subject, body, replace_uid=0) -> int: return await asyncio.to_thread(save_draft_sync, acct, to, cc, subject, body, replace_uid)
