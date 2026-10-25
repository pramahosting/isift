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
