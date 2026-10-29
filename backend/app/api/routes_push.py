"""Turning notifications on for a device (browser or installed phone app)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal
from app.models import User
from app.services import push

router = APIRouter(prefix="/api/v1/push", tags=["push"])

@router.get("/key")
async def key(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    _, pub = await push.vapid(db)
    rec = await push.subs(db, user.email)
    return {"key": pub, "devices": len(rec.get("subs", []))}

@router.post("/subscribe")
async def subscribe(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    sub = payload.get("subscription") or {}
    if not isinstance(sub.get("endpoint"), str) or not sub["endpoint"].startswith("https://") or not isinstance((sub.get("keys") or {}).get("p256dh"), str) or not isinstance(sub["keys"].get("auth"), str):
        raise HTTPException(400, "That device could not be registered for notifications.")
    await push.add_sub(db, user.email, {"endpoint": sub["endpoint"][:1000], "keys": {"p256dh": sub["keys"]["p256dh"][:200], "auth": sub["keys"]["auth"][:100]}}, str(payload.get("ua") or ""))
    return {"ok": True}

@router.post("/unsubscribe")
async def unsubscribe(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await push.remove_sub(db, user.email, str(payload.get("endpoint") or "")); return {"ok": True}

@router.post("/test")
async def test(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    n = await push.send(db, user.email, "iSift notifications are on", "You will get meeting, invitation and email alerts like this one.", "", "test", "test")
    if not n: raise HTTPException(409, "No device could be reached. Turn notifications on again on this device.")
    return {"sent": n}
