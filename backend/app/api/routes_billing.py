"""Plans, the card on file and subscription payments (Square). The Square keys are set by an administrator in Admin settings > Payments."""
from fastapi import APIRouter, Depends, HTTPException, Response
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
async def plans(response: Response, db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store, max-age=0"       # prices change in Admin settings: no browser or CDN (Cloudflare) may keep an old copy
    return await B.plans_view(db)

# ---------------- price list (Admin settings > Pricing) ----------------
def _clean_price(d: dict, base: dict | None = None) -> dict:
    out = dict(base or {})
    for k in ("plan", "label", "monthly", "yearly", "active"):
        if k in d: out[k] = d[k]
    if out.get("plan") not in B.PAID: raise HTTPException(422, "Choose Personal Pro or Business. Basic is always free.")
    out["label"] = str(out.get("label") or "Standard").strip()[:60] or "Standard"
    for k in ("monthly", "yearly"):
        try: out[k] = int(round(float(out.get(k))))
        except (TypeError, ValueError): raise HTTPException(422, "Enter the monthly and yearly prices as numbers.")
        if not 1 <= out[k] <= 10_000_000: raise HTTPException(422, "A price must be more than 0 and less than 100,000.")
    out["active"] = bool(out.get("active"))
    return out

async def _save_prices(db, rows: list[dict], changed_id: str | None, actor: str, action: str):
    if changed_id:                                         # one price per plan is on sale: switching one on switches the other prices of that plan off
        ch = next((r for r in rows if r["id"] == changed_id), None)
        if ch and ch["active"]:
            for r in rows:
                if r["plan"] == ch["plan"] and r["id"] != changed_id: r["active"] = False
    from app.services import store
    await store.put(db, B.PRICE_KEY, {"rows": rows}, commit=False); B.apply_prices(rows)
    db.add(AuditLog(actor=actor, action=action, resource_type="pricing", safe_metadata={})); await db.commit()
    return {"rows": rows, "plans": (await B.plans_view(db))["plans"]}

@router.get("/admin/pricing")
async def pricing_list(user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return {"rows": await B.load_prices(db), "currency": B.settings.square_currency}

@router.post("/admin/pricing")
async def pricing_add(payload: dict, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    import uuid
    rows = await B.price_rows(db); row = _clean_price(payload); row["id"] = uuid.uuid4().hex[:10]; rows.append(row)
    return await _save_prices(db, rows, row["id"], user.email, "pricing.added")

@router.patch("/admin/pricing/{rid}")
async def pricing_edit(rid: str, payload: dict, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await B.price_rows(db); i = next((n for n, r in enumerate(rows) if r["id"] == rid), None)
    if i is None: raise HTTPException(404, "That price no longer exists.")
    rows[i] = _clean_price(payload, rows[i])
    return await _save_prices(db, rows, rid, user.email, "pricing.changed")

@router.delete("/admin/pricing/{rid}")
async def pricing_delete(rid: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    rows = await B.price_rows(db)
    if not any(r["id"] == rid for r in rows): raise HTTPException(404, "That price no longer exists.")
    return await _save_prices(db, [r for r in rows if r["id"] != rid], None, user.email, "pricing.deleted")

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
    res = await _do(B.subscribe(db, user, str(payload.get("plan") or ""), str(payload.get("period") or "monthly"), bool(payload.get("immediate")), {k: payload.get(k) for k in ("recurring", "months", "end_date") if k in payload}))
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
    r["auto_renew"] = bool(payload.get("enabled"))
    if r["auto_renew"]: r["ends_on"] = None                                   # switching renewal back on means: keep going until cancelled
    await B.store.put(db, key, r)
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
