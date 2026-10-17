"""Plans, the card on file and subscription payments (Square). The Square keys are set by an administrator in Admin settings > Payments."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.security import principal, require_admin
from app.models import User, AuditLog
from app.services import billing as B

router = APIRouter(prefix="/api/v1", tags=["billing"])

async def _do(coro):
    try: return await coro
    except B.BillingError as e: raise HTTPException(e.status, e.message)

@router.get("/billing/plans")
async def plans(): return B.plans_view()

@router.get("/billing/me")
async def me(user: User = Depends(principal), db: AsyncSession = Depends(get_db)): return await B.view(db, user)

@router.post("/billing/card")
async def card(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _do(B.save_card(db, user, str(payload.get("source_id") or "")))
    db.add(AuditLog(actor=user.email, action="billing.card_saved", resource_type="billing", safe_metadata={})); await db.commit()
    return await B.view(db, user)

@router.delete("/billing/card")
async def card_remove(user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    await _do(B.remove_card(db, user)); return await B.view(db, user)

@router.post("/billing/subscribe")
async def subscribe(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    res = await _do(B.subscribe(db, user, str(payload.get("plan") or ""), str(payload.get("period") or "monthly"), bool(payload.get("immediate"))))
    db.add(AuditLog(actor=user.email, action="billing.subscribe", resource_type="billing", safe_metadata={"plan": payload.get("plan"), "period": payload.get("period"), "result": res.get("status")})); await db.commit()
    return {**res, "billing": await B.view(db, user)}

@router.post("/billing/quote")
async def quote(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    """What a plan change would cost: unused time credited, difference due now, or a refund request."""
    return await _do(B.quote(db, user, str(payload.get("plan") or ""), str(payload.get("period") or "monthly")))

@router.post("/billing/auto-renew")
async def auto_renew(payload: dict, user: User = Depends(principal), db: AsyncSession = Depends(get_db)):
    key, c, can = await B.holder(db, user)
    if not can: raise HTTPException(403, "Only the company owner or an administrator can change that.")
    r = await B.record(db, key, c)
    if payload.get("enabled") and not r.get("card_id"): raise HTTPException(409, "Add a card first.")
    r["auto_renew"] = bool(payload.get("enabled")); await B.store.put(db, key, r)
    return await B.view(db, user)

@router.get("/admin/billing/overview")
async def overview(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)): return await B.overview(db)

@router.post("/admin/billing/run")
async def run(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)): return await B.run_due(db)


@router.get("/admin/billing/refunds")
async def refunds(status: str = "", user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)): return {"refunds": await B.list_refunds(db, status)}

@router.post("/admin/billing/refunds/{rid}/approve")
async def refund_approve(rid: str, payload: dict | None = None, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    payload = payload or {}
    res = await _do(B.approve_refund(db, rid, user.email, int(payload["amount_cents"]) if payload.get("amount_cents") else None, str(payload.get("note") or "")))
    db.add(AuditLog(actor=user.email, action="billing.refund_approved", resource_type="billing", safe_metadata={"id": rid, "cents": res.get("paid_back_cents")})); await db.commit()
    return res

@router.post("/admin/billing/refunds/{rid}/decline")
async def refund_decline(rid: str, payload: dict | None = None, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    res = await _do(B.decline_refund(db, rid, user.email, str((payload or {}).get("note") or "")))
    db.add(AuditLog(actor=user.email, action="billing.refund_declined", resource_type="billing", safe_metadata={"id": rid})); await db.commit()
    return res
