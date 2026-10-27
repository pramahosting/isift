"""Work out mail server settings from an email address, so adding an account only needs the password (like Outlook).

Order: well-known providers, then the domain's MX records, then the Mozilla/Thunderbird autoconfig database and the
domain's own autoconfig file, then a checked guess (imap./mail. + the domain). Nothing here signs in or sends anything."""
import asyncio, re, socket
import xml.etree.ElementTree as ET
import httpx
from app.integrations import ics_feed

# (MX host suffix) -> (label, imap host, imap port, smtp host, smtp port, note)
MX_MAP = [
    ("secureserver.net", ("GoDaddy Workspace Email", "imap.secureserver.net", 993, "smtpout.secureserver.net", 465)),
    ("titan.email", ("Titan Email", "imap.titan.email", 993, "smtp.titan.email", 465)),
    ("fastmail.com", ("Fastmail", "imap.fastmail.com", 993, "smtp.fastmail.com", 465)),
    ("messagingengine.com", ("Fastmail", "imap.fastmail.com", 993, "smtp.fastmail.com", 465)),
    ("privateemail.com", ("Namecheap Private Email", "mail.privateemail.com", 993, "mail.privateemail.com", 465)),
    ("hostinger.com", ("Hostinger Email", "imap.hostinger.com", 993, "smtp.hostinger.com", 465)),
    ("ionos.com", ("IONOS", "imap.ionos.com", 993, "smtp.ionos.com", 587)),
    ("kundenserver.de", ("IONOS", "imap.ionos.com", 993, "smtp.ionos.com", 587)),
    ("icloud.com", ("Apple iCloud Mail", "imap.mail.me.com", 993, "smtp.mail.me.com", 587)),
]
OAUTH_MX = [("google.com", "google"), ("googlemail.com", "google"), ("protection.outlook.com", "microsoft"), ("outlook.com", "microsoft")]
ZOHO = re.compile(r"(?:^|\.)(zoho\.(com\.au|com\.cn|com|eu|in|jp|sa))$")

def _domain(addr: str) -> str:
    d = addr.rsplit("@", 1)[-1].strip().lower().strip(".")
    return d if re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+", d) else ""

def _mx(domain: str) -> list[str]:
    try:
        import dns.resolver
        r = dns.resolver.Resolver(); r.lifetime = 4
        return [str(a.exchange).rstrip(".").lower() for a in sorted(r.resolve(domain, "MX"), key=lambda a: a.preference)]
    except Exception: return []

def _from_xml(text: str) -> dict | None:
    try: root = ET.fromstring(text)
    except ET.ParseError: return None
    def pick(kind):
        for el in root.iter(kind + "Server"):
            if el.get("type") != ("imap" if kind == "incoming" else "smtp"): continue
            host = (el.findtext("hostname") or "").strip(); port = (el.findtext("port") or "").strip()
            if host and port.isdigit() and "%" not in host: return host.lower(), int(port)
        return None
    i, o = pick("incoming"), pick("outgoing")
    if not i or not o: return None
    name = (root.findtext(".//displayName") or "").strip()[:60]
    return {"imap": i, "smtp": o, "label": name}

async def _http_config(domain: str) -> dict | None:
    urls = [f"https://autoconfig.thunderbird.net/v1.1/{domain}"]
    try:
        if ics_feed._public(f"autoconfig.{domain}"): urls.append(f"https://autoconfig.{domain}/mail/config-v1.1.xml")
    except Exception: pass
    async with httpx.AsyncClient(timeout=4, follow_redirects=False) as c:
        for u in urls:
            try:
                r = await c.get(u)
                if r.status_code == 200 and len(r.content) < 200_000:
                    d = _from_xml(r.text)
                    if d: return d
            except Exception: continue
    return None

def _resolves(host: str) -> bool:
    try: socket.getaddrinfo(host, None); return True
    except OSError: return False

def _result(label, imap, smtp, source, provider="other", **extra):
    return {"provider": provider, "label": label, "imap_host": imap[0], "imap_port": imap[1], "smtp_host": smtp[0], "smtp_port": smtp[1], "source": source, **extra}

async def detect(address: str) -> dict:
    """Returns {found: bool, oauth: 'google'|'microsoft'|None, provider, label, imap_host, imap_port, smtp_host, smtp_port, source}."""
    from app.integrations import oauth
    d = _domain(address)
    if not d: return {"found": False}
    known = oauth.detect(address)
    if known: return {"found": True, "oauth": known, "source": "domain"}
    mx = await asyncio.to_thread(_mx, d)
    for host in mx:
        for suf, p in OAUTH_MX:
            if host == suf or host.endswith("." + suf): return {"found": True, "oauth": p, "source": "mx"}
        for suf, (label, ih, ip, sh, sp) in MX_MAP:
            if host == suf or host.endswith("." + suf): return {"found": True, "oauth": None, **_result(label, (ih, ip), (sh, sp), "mx")}
        m = ZOHO.search(host)
        if m: z = m.group(1); return {"found": True, "oauth": None, **_result("Zoho Mail", (f"imap.{z}", 993), (f"smtp.{z}", 465), "mx")}
    cfg = await _http_config(d)
    if cfg: return {"found": True, "oauth": None, **_result(cfg["label"] or d, cfg["imap"], cfg["smtp"], "autoconfig")}
    for ih, sh in ((f"imap.{d}", f"smtp.{d}"), (f"mail.{d}", f"mail.{d}")):
        if await asyncio.to_thread(_resolves, ih) and await asyncio.to_thread(_resolves, sh):
            return {"found": True, "oauth": None, "guess": True, **_result(d, (ih, 993), (sh, 465), "guess")}
    return {"found": False}
