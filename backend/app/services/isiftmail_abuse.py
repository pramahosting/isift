"""isiftmail abuse controls: sending limits, new-address limits, and suspending a mailbox that spams.

Everything is kept in IntegrationSetting rows (no new tables):
  isiftmail_stat:{address}  -> {"sent": [iso times, last 24h], "complaints": n, "bounces": n}
  isiftmail_box:{address}   -> the mailbox register; a suspended mailbox gets "suspended": {"at", "reason"}
Suspending changes the mailbox's password on the mail server (so nobody can send or read), unsuspending restores the stored one.
"""
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core import runtime_settings as rs
from app.models import IntegrationSetting, AuditLog
from app.integrations import isiftmail as im, mail as mailer

STAT = "isiftmail_stat:"
BOX = "isiftmail_box:"

def _now() -> datetime: return datetime.now(timezone.utc)
def _n(name: str, default: int) -> int:
    try: return max(0, int(getattr(settings, name, default) or 0)) or default
    except (TypeError, ValueError): return default

async def _stat(db: AsyncSession, address: str) -> tuple[IntegrationSetting | None, dict]:
    row = await db.get(IntegrationSetting, STAT + address)
    v = dict(row.value or {}) if row else {}
    v.setdefault("sent", []); v.setdefault("complaints", 0); v.setdefault("bounces", 0)
    return row, v

async def _save_stat(db: AsyncSession, row: IntegrationSetting | None, address: str, v: dict):
    if row: row.value = v
    else: db.add(IntegrationSetting(key=STAT + address, value=v))

def _recent(v: dict, seconds: int) -> int:
    cut = _now() - timedelta(seconds=seconds)
    return sum(1 for t in v["sent"] if datetime.fromisoformat(t) > cut)

async def suspension(db: AsyncSession, address: str) -> dict | None:
    box = await db.get(IntegrationSetting, BOX + address)
    return (box.value or {}).get("suspended") if box else None

async def check_send(db: AsyncSession, address: str, recipients: int) -> None:
    """Called before a message from an isiftmail mailbox is sent. Raises when the mailbox is suspended or over a limit."""
    address = address.lower()
    if await suspension(db, address):
        raise HTTPException(403, "This mailbox has been suspended because of possible spam. Contact the iSift administrator.")
    if recipients > _n("isiftmail_max_recipients", 50):
        raise HTTPException(429, f"You can send a message to at most {_n('isiftmail_max_recipients', 50)} people at once.")
    box = await db.get(IntegrationSetting, BOX + address)
    day = _n("isiftmail_send_per_day", 200)
    try: new = box and _now() - datetime.fromisoformat((box.value or {}).get("created", "")) < timedelta(days=1)
    except ValueError: new = False
    if new: day = max(5, day // 4)
    _, v = await _stat(db, address)
    if _recent(v, 3600) >= _n("isiftmail_send_per_hour", 30):
        raise HTTPException(429, "You have reached the hourly sending limit for this mailbox. Please try again later.")
    if _recent(v, 86400) >= day:
        raise HTTPException(429, "You have reached the daily sending limit for this mailbox" + (" (new mailboxes start lower)." if new else ".") + " Please try again tomorrow.")

async def record_send(db: AsyncSession, address: str) -> None:
    address = address.lower()
    row, v = await _stat(db, address)
    cut = _now() - timedelta(days=1)
    v["sent"] = [t for t in v["sent"] if datetime.fromisoformat(t) > cut][-2000:] + [_now().isoformat()]
    await _save_stat(db, row, address, v); await db.commit()

async def suspend(db: AsyncSession, address: str, reason: str, actor: str = "automatic") -> bool:
    address = address.lower()
    box = await db.get(IntegrationSetting, BOX + address)
    if not box: return False
    val = dict(box.value or {})
    if val.get("suspended"): return True
    try: await im.set_password(val.get("login") or address.split("@")[0], secrets.token_urlsafe(24))
    except mailer.MailError: pass           # still mark it: sending from iSift is blocked either way
    val["suspended"] = {"at": _now().isoformat(), "reason": reason[:200], "by": actor}
    box.value = val
    db.add(AuditLog(actor=actor, action="isiftmail.suspend", resource_type="mail", safe_metadata={"address": address, "reason": reason[:200]}))
    await db.commit(); return True

async def unsuspend(db: AsyncSession, address: str, actor: str) -> bool:
    address = address.lower()
    box = await db.get(IntegrationSetting, BOX + address)
    if not box or not (box.value or {}).get("suspended"): return False
    val = dict(box.value)
    try: await im.set_password(val.get("login") or address.split("@")[0], rs._dec(val.get("password", "")))
    except mailer.MailError as exc: raise HTTPException(502, str(exc))
    val.pop("suspended", None); box.value = val
    row, v = await _stat(db, address); v["complaints"] = 0; v["bounces"] = 0; await _save_stat(db, row, address, v)
    db.add(AuditLog(actor=actor, action="isiftmail.unsuspend", resource_type="mail", safe_metadata={"address": address}))
    await db.commit(); return True

async def note_event(db: AsyncSession, address: str, kind: str) -> dict:
    """kind: 'complaint' (spam complaint or abuse report) or 'bounce'. Suspends the mailbox when the limit is reached."""
    address = address.lower()
    if not await db.get(IntegrationSetting, BOX + address): return {"known": False}
    row, v = await _stat(db, address)
    key = "complaints" if kind == "complaint" else "bounces"; v[key] += 1
    await _save_stat(db, row, address, v); await db.commit()
    limit = _n("isiftmail_complaint_limit", 3) if kind == "complaint" else _n("isiftmail_bounce_limit", 20)
    done = False
    if v[key] >= limit: done = await suspend(db, address, f"{v[key]} {'spam complaints' if kind == 'complaint' else 'bounced messages'}")
    return {"known": True, "count": v[key], "suspended": done}

async def overview(db: AsyncSession) -> list[dict]:
    from sqlalchemy import select
    boxes = (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like(BOX + "%")))).scalars().all()
    stats = {r.key[len(STAT):]: r.value or {} for r in (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like(STAT + "%")))).scalars().all()}
    out = []
    for b in boxes:
        v = b.value or {}; a = v.get("address", b.key[len(BOX):]); s = stats.get(a, {})
        cut = _now() - timedelta(days=1)
        out.append({"address": a, "owner": v.get("assignee", ""), "created": v.get("created", ""), "complaints": s.get("complaints", 0), "bounces": s.get("bounces", 0),
                    "sent_24h": sum(1 for t in s.get("sent", []) if datetime.fromisoformat(t) > cut), "suspended": v.get("suspended")})
    out.sort(key=lambda x: (not x["suspended"], -(x["complaints"] * 10 + x["bounces"]), x["address"]))
    return out
