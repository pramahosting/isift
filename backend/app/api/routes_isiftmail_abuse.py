"""isiftmail abuse handling: notices from the outbound relay, a public abuse report, and the administrator's list of mailboxes.

The relay notice and the abuse report are open to the internet on purpose (the relay and strangers must reach them), so they are
protected by a secret (relay) or by a small rate limit (report), and they only ever count events; the administrator decides the rest.
"""
import hmac, re, time
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.db import get_db
from app.core.security import require_admin
from app.models import User
from app.integrations import isiftmail as im
from app.services import isiftmail_abuse as abuse

router = APIRouter(tags=["isiftmail"])
ADDR = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_REPORTS: dict[str, list[float]] = {}

def _find(x) -> str:
    m = ADDR.search(str(x or "")); return m.group(0).lower() if m else ""

def _events(body) -> list[tuple[str, str]]:
    """Understands a simple list, e.g. {"events":[{"type":"complaint","from":"a@b"}]}, one event, and the common relay shapes
    (type/event/notificationType = complaint|spam|bounce, sender in from/sender/mail.source/address)."""
    items = body.get("events") if isinstance(body, dict) and isinstance(body.get("events"), list) else [body]
    out = []
    for e in items:
        if not isinstance(e, dict): continue
        t = str(e.get("type") or e.get("event") or e.get("notificationType") or "").lower()
        kind = "complaint" if any(w in t for w in ("complaint", "spam", "abuse")) else "bounce" if "bounce" in t else ""
        if kind == "bounce" and str(e.get("bounceType") or (e.get("bounce") or {}).get("bounceType") or "Permanent").lower().startswith("trans"): continue   # only hard bounces count
        who = _find(e.get("from") or e.get("sender") or e.get("address") or (e.get("mail") or {}).get("source") or "")
        if kind and who: out.append((kind, who))
    return out

@router.post("/api/v1/isiftmail/hooks/relay")
async def relay_notice(request: Request, secret: str = "", db: AsyncSession = Depends(get_db)):
    want = settings.isiftmail_hook_secret or ""
    if not want or not hmac.compare_digest(secret.encode(), want.encode()): raise HTTPException(403, "Not allowed.")
    try: body = await request.json()
    except Exception: raise HTTPException(422, "Send the notice as JSON.")
    done = [{"address": a, "kind": k, **await abuse.note_event(db, a, k)} for k, a in _events(body)[:100]]
    return {"ok": True, "handled": len(done), "events": done}

@router.post("/api/v1/isiftmail/report")
async def report(payload: dict, request: Request, db: AsyncSession = Depends(get_db)):
    """Anyone (no sign-in) can report spam from an isiftmail address. Each report counts as a complaint."""
    if not im.configured(): raise HTTPException(404, "Not found.")
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    now = time.time(); hits = [t for t in _REPORTS.get(fwd, []) if now - t < 3600]
    if len(hits) >= 5: raise HTTPException(429, "Too many reports from here. Please try again later.")
    _REPORTS[fwd] = hits + [now]
    who = _find(payload.get("address"))
    if not who: raise HTTPException(422, "Enter the email address the spam came from.")
    r = await abuse.note_event(db, who, "complaint") if who.rsplit("@", 1)[-1] in await _hosted(db) else {"known": False}
    return {"ok": True, "message": "Thank you. We look at every report."}

async def _hosted(db: AsyncSession) -> set[str]:
    from sqlalchemy import select
    from app.models import IntegrationSetting
    doms = {im.domain()} if im.domain() else set()
    for r in (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like("isiftmail_dom:%")))).scalars().all():
        if (r.value or {}).get("status") == "verified": doms.add(r.key.split(":")[1])
    return doms

@router.get("/api/v1/admin/isiftmail/mailboxes")
async def mailboxes(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await abuse.overview(db)
    return {"mailboxes": rows, "limits": {"hour": settings.isiftmail_send_per_hour, "day": settings.isiftmail_send_per_day, "complaints": settings.isiftmail_complaint_limit, "bounces": settings.isiftmail_bounce_limit}}

@router.post("/api/v1/admin/isiftmail/suspend")
async def suspend(payload: dict, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = _find(payload.get("address"))
    if not a or not await abuse.suspend(db, a, str(payload.get("reason") or "Suspended by an administrator")[:200], admin.email): raise HTTPException(404, "That mailbox was not found.")
    return {"ok": True, "message": f"{a} is suspended."}

@router.post("/api/v1/admin/isiftmail/unsuspend")
async def unsuspend(payload: dict, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    a = _find(payload.get("address"))
    if not a or not await abuse.unsuspend(db, a, admin.email): raise HTTPException(404, "That mailbox is not suspended.")
    return {"ok": True, "message": f"{a} is active again."}


# ---------------------------------------------------------------- "Test my mail server" for the administrator
def _port(host: str, port: int, tls: bool = False, greet: bool = True) -> tuple[bool, str]:
    import socket, ssl
    try:
        s = socket.create_connection((host, port), timeout=6)
        try:
            if tls: s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
            s.settimeout(6); banner = s.recv(120).decode("utf-8", "ignore").strip() if greet else ""
        finally: s.close()
        return True, banner[:80] or "connected"
    except ssl.SSLCertVerificationError: return False, "connected, but the certificate is not valid for this name"
    except Exception as exc: return False, f"could not connect ({type(exc).__name__})"

@router.get("/api/v1/admin/isiftmail/test")
async def test_server(admin: User = Depends(require_admin)):
    """Checks every part of the isiftmail setup and says in plain words what to fix. Nothing is changed."""
    import asyncio
    from app.integrations import mail as mailer
    out = []
    def add(key, label, ok, detail, fix=""): out.append({"key": key, "label": label, "ok": bool(ok), "detail": detail, "fix": "" if ok else fix})
    dom = im.domain()
    add("domain", "Address domain", dom, dom or "Not set", "Enter the domain people get addresses on (for example isiftmail.com) in the isiftmail settings.")
    host = (settings.isiftmail_imap_host or "").strip(); smtp = (settings.isiftmail_smtp_host or "").strip()
    add("hosts", "Mail server names", host and smtp, f"{host or '–'} / {smtp or '–'}", "Enter the mailbox (IMAP) and sending (SMTP) server names in the isiftmail settings.")
    if (settings.isiftmail_api_url or "").strip():
        try:
            r = await im._api("GET", "/api/principal?limit=1")
            add("api", "Mail server management login", r.status_code < 400, "iSift can sign in" if r.status_code < 400 else f"the server answered {r.status_code}", "Check the management address, administrator name and password in the isiftmail settings.")
        except mailer.MailError as exc: add("api", "Mail server management login", False, str(exc), "Check the management address, administrator name and password in the isiftmail settings.")
    else: add("api", "Mail server management login", False, "Not set", "Enter the mail server's management address (for example https://mail.isiftmail.com).")
    if host:
        ok, d = await asyncio.to_thread(_port, host, int(settings.isiftmail_imap_port or 993), True, True); add("imap", f"Mailboxes (IMAP, port {settings.isiftmail_imap_port})", ok, d, "Open the port on the server's firewall and install a valid certificate for the name.")
        ok, d = await asyncio.to_thread(_port, host, int(settings.isiftmail_sieve_port or 4190), False, True); add("sieve", f"Auto-reply (port {settings.isiftmail_sieve_port})", ok, d, "Open the port on the server's firewall. Without it, auto-reply will not work, everything else will.")
    if smtp:
        ok, d = await asyncio.to_thread(_port, smtp, int(settings.isiftmail_smtp_port or 587), False, True); add("smtp", f"Sending (SMTP, port {settings.isiftmail_smtp_port})", ok, d, "Open the port on the server's firewall.")
    if dom and im.mx_host():
        try: mx = await im.lookup(dom, "MX"); add("mx", "Mail for your domain arrives (MX)", im.mx_host() in mx, ", ".join(mx) or "no MX record", f"At your domain registrar add an MX record for {dom} pointing to {im.mx_host()}.")
        except mailer.MailError as exc: add("mx", "Mail for your domain arrives (MX)", False, str(exc), "Try again in a minute.")
        try:
            spf = [t for t in await im.lookup(dom, "TXT") if t.lower().startswith("v=spf1")]; add("spf", "SPF (others trust your mail)", bool(spf), spf[0][:80] if spf else "no SPF record", f"Add a TXT record for {dom}: {settings.isiftmail_spf}")
            dm = [t for t in await im.lookup(f"_dmarc.{dom}", "TXT") if t.lower().startswith("v=dmarc1")]; add("dmarc", "DMARC", bool(dm), dm[0][:80] if dm else "no DMARC record", f"Add a TXT record named _dmarc.{dom} with: v=DMARC1; p=none")
        except mailer.MailError: pass
    add("hook", "Complaint and bounce notices", bool(settings.isiftmail_hook_secret), "secret set" if settings.isiftmail_hook_secret else "no secret yet", "Make up a long random secret in the isiftmail settings and give your outbound relay the notice address (see docs/ISIFTMAIL.md).")
    required = [x for x in out if x["key"] in ("domain", "hosts", "api", "imap", "smtp", "mx")]
    return {"checks": out, "ready": all(x["ok"] for x in required), "message": "Everything needed is working. People can now open addresses." if all(x["ok"] for x in required) else "Some things need your attention. Fix the items marked below, then test again."}
