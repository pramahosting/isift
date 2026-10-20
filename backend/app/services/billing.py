"""Plans and automatic subscription billing through Square (card on file). Modelled on AccFino's billing module.

Flow: the account holder saves a card (Square's secure form -> one-time token -> Square keeps the card, we keep only ids and the last 4 digits) and chooses a plan.
iSift takes the first payment at once, then each month or year automatically. A declined card is retried on day 3 and day 6; the plan keeps working through a
7-day grace period, after which the account drops back to Basic. A charge record with a unique idempotency key is written BEFORE Square is called, so a restart
or a second worker can never take the same renewal twice. Records live in integration_settings (no schema change)."""
import calendar, hashlib, logging
from datetime import date, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.integrations import square as SQ
from app.models import IntegrationSetting
from app.services import store, notify

log = logging.getLogger("isift")
MAX_ATTEMPTS, RETRY_DAYS, GRACE_DAYS = 3, 3, 7
PENDING_STALE = timedelta(minutes=10)
LEGACY = {"free": "basic", "pro": "individual", "enterprise": "business"}
# Monthly prices as listed. Yearly was 12 x a per-month price of 11.33 / 14.66 (13.596 / 17.592 a year); it now has a further 5% off: 129.16 / 167.12 a year. per_month_yearly is that total divided by 12 (for display).
PLANS = {
 "basic": {"name": "Basic", "monthly": 0, "yearly": 0, "per_month_yearly": 0},
 "individual": {"name": "Personal Pro", "monthly": 1359, "yearly": 12916, "per_month_yearly": 1076},
 "business": {"name": "Business", "monthly": 1759, "yearly": 16712, "per_month_yearly": 1393},
}
PERIODS = ("monthly", "yearly")
PAID = ("individual", "business")
PRICE_KEY = "pricing:rows"
for _p in PLANS.values(): _p["available"] = True
DEFAULT_ROWS = [{"id": f"default-{k}", "plan": k, "label": "Standard", "monthly": PLANS[k]["monthly"], "yearly": PLANS[k]["yearly"], "active": True} for k in PAID]

async def price_rows(db) -> list[dict]:
    """The price list the administrator edits (Admin settings > Pricing). Seeded once with the standard prices."""
    d = await store.get(db, PRICE_KEY, None)
    if not d or "rows" not in d:
        d = {"rows": [dict(r) for r in DEFAULT_ROWS]}; await store.put(db, PRICE_KEY, d)
    return d["rows"]

def apply_prices(rows: list[dict]):
    """Only an ACTIVE price is on sale. A paid plan with no active price is off sale: hidden from the home page and Pricing page and refused for new sign-ups and changes.
    Existing subscribers keep renewing at the plan's last known price."""
    for k in PAID:
        mine = [r for r in rows if r["plan"] == k]
        act = [r for r in mine if r.get("active")]
        pick = (act or mine[-1:] or [None])[0]
        PLANS[k]["available"] = bool(act)
        if pick: PLANS[k].update(monthly=int(pick["monthly"]), yearly=int(pick["yearly"]), per_month_yearly=round(int(pick["yearly"]) / 12), price_id=pick["id"])

async def load_prices(db) -> list[dict]:
    rows = await price_rows(db); apply_prices(rows); return rows

def require_on_sale(plan: str):
    if plan != "basic" and not PLANS[plan].get("available"): raise BillingError(f"The {PLANS[plan]['name']} plan is not on sale right now.", 422)

class BillingError(Exception):
    def __init__(self, message: str, status: int = 400): super().__init__(message); self.message, self.status = message, status

def norm_plan(p) -> str:
    p = LEGACY.get(p, p)
    return p if p in PLANS else "basic"

def cents(plan: str, period: str) -> int: return PLANS[plan]["yearly" if period == "yearly" else "monthly"]
def add_period(d: date, period: str) -> date:
    months = 12 if period == "yearly" else 1
    y, mo = d.year + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))

def terms_of(period: str, terms: dict | None, today: date) -> tuple[bool, str | None]:
    """How long a plan keeps renewing. Yearly always renews. Monthly: a ticked 'recurring' box needs a number of months or an end date;
    unticked means one month and no automatic renewal. Returns (auto_renew, ends_on): no new period is charged once the plan has run to ends_on."""
    t = terms or {}
    if period == "yearly" or t.get("recurring") is None: return True, None             # yearly, or an older caller: renew until cancelled
    if not t.get("recurring"): return False, None
    months, end = t.get("months"), str(t.get("end_date") or "").strip()
    if months not in (None, ""):
        try: n = int(months)
        except (TypeError, ValueError): raise BillingError("Enter the number of months as a whole number.", 422)
        if not 1 <= n <= 60: raise BillingError("Choose between 1 and 60 months.", 422)
        d = today
        for _ in range(n): d = add_period(d, "monthly")
        return True, d.isoformat()
    if end:
        try: d = date.fromisoformat(end)
        except ValueError: raise BillingError("Enter the end date as a real date.", 422)
        if d <= today: raise BillingError("The end date must be in the future.", 422)
        if d > today + timedelta(days=366 * 5): raise BillingError("The end date can be at most 5 years away.", 422)
        return True, d.isoformat()
    raise BillingError("For monthly payments that repeat, choose how many months or an end date.", 422)

async def plans_view(db) -> dict:
    await load_prices(db)
    return {"currency": settings.square_currency, "plans": [{"id": k, **v} for k, v in PLANS.items()]}

# ------------------------------------------------------------------ who pays
async def holder(db, user) -> tuple[str, dict | None, bool]:
    """(billing record key, company or None, may manage billing). A company account pays as one; otherwise the person pays for themselves."""
    email = (user.email or "").strip().lower()
    link = await store.get(db, store.hkey("memberof", email), {})
    if link.get("company_id"):
        c = await store.get(db, f"company:{link['company_id']}", {})
        if c and any(m["email"] == email for m in c.get("members", [])):
            c["id"] = link["company_id"]
            role = next((m["role"] for m in c["members"] if m["email"] == email), "member")
            return f"billing:co:{c['id']}", c, role in ("owner", "admin")
    return store.hkey("billing", email), None, True

async def record(db, key: str, company: dict | None = None) -> dict:
    r = await store.get(db, key, {})
    if not r:
        r = {"plan": norm_plan((company or {}).get("plan", "basic")), "period": "monthly", "status": "active", "period_end": None, "auto_renew": False, "failure_count": 0, "charges": []}
    r["plan"] = norm_plan(r.get("plan")); r.setdefault("charges", [])
    return r

async def plan_of(db, user) -> str:
    key, c, _ = await holder(db, user)
    return (await record(db, key, c))["plan"]

async def admin_summary(db, user) -> dict:
    """What the administrator sees for one person: plan, dates, last payment."""
    key, c, _ = await holder(db, user)
    r = await record(db, key, c)
    paid = next((x for x in r["charges"] if x.get("status") == "paid"), None)
    cents_ = (paid or {}).get("amount_cents") or r.get("paid_cents") or 0
    return {"plan": r["plan"], "plan_name": PLANS[r["plan"]]["name"], "period": r.get("period", "monthly") if r["plan"] != "basic" else None,
            "start": r.get("period_start"), "end": r.get("ends_on") or r.get("period_end"), "status": r.get("status", "active"),
            "paid": bool(paid), "paid_on": (paid or {}).get("settled"), "amount": round(cents_ / 100, 2) if paid or r["plan"] != "basic" else 0, "currency": settings.square_currency}

def _card(r): return {"brand": r.get("card_brand"), "last4": r.get("card_last4"), "exp_month": r.get("card_exp_month"), "exp_year": r.get("card_exp_year")} if r.get("card_id") else None

async def view(db, user) -> dict:
    pv = await plans_view(db)
    key, c, can = await holder(db, user)
    r = await record(db, key, c)
    return {"plan": r["plan"], "plan_name": PLANS[r["plan"]]["name"], "period": r.get("period", "monthly"), "status": r.get("status", "active"), "period_end": r.get("period_end"),
            "auto_renew": bool(r.get("auto_renew")), "ends_on": r.get("ends_on"), "card": _card(r), "failure_count": r.get("failure_count", 0), "last_error": r.get("last_error"), "next_attempt_on": r.get("next_attempt_on"),
            "charges": r["charges"][:12], "refunds": await user_refunds(db, r), "can_manage": can, "company": c["name"] if c else None, "currency": settings.square_currency,
            "square": {"available": SQ.configured(), "applicationId": settings.square_application_id, "locationId": settings.square_location_id, "environment": SQ.env(), "sdk": SQ.SDK[SQ.env()]} if SQ.configured() else None,
            **pv}

# ------------------------------------------------------------------ card
async def _payer(db, key, user, company) -> tuple[str, str]:
    if company:
        owner = next((m for m in company["members"] if m["role"] == "owner"), company["members"][0])
        return owner["email"], company["name"]
    return (user.email or "").lower(), user.display_name or user.email

async def save_card(db, user, source_id: str) -> dict:
    key, c, can = await holder(db, user)
    if not can: raise BillingError("Only the company owner or an administrator can change the card.", 403)
    if not SQ.configured(): raise BillingError("Card payments are not switched on yet. Ask your administrator to set up Square in Admin settings.", 503)
    if not source_id: raise BillingError("The card could not be read. Please try again.")
    r = await record(db, key, c); email, name = await _payer(db, key, user, c)
    ref = hashlib.sha1(key.encode()).hexdigest()[:16]
    try:
        if not r.get("customer_id"):
            r["customer_id"] = (await SQ.create_customer(idempotency_key=f"isift-cust-{ref}", email=email, name=name, reference_id=ref)).get("id")
        card = await SQ.create_card(source_id=source_id, customer_id=r["customer_id"], idempotency_key=SQ.key())
    except SQ.SquareError as e:
        raise BillingError("Your card could not be saved: " + (e.detail or "Square declined it.") + " Please check the details or try another card.", 402)
    old = r.get("card_id")
    r.update(card_id=card.get("id"), card_brand=(card.get("card_brand") or "").title(), card_last4=card.get("last_4"), card_exp_month=card.get("exp_month"), card_exp_year=card.get("exp_year"),
             failure_count=0, next_attempt_on=None, last_error=None, payer_email=email)
    await store.put(db, key, r)
    if old and old != r["card_id"]:
        try: await SQ.disable_card(old)
        except SQ.SquareError: log.info("old card could not be disabled")
    return r

async def remove_card(db, user):
    key, c, can = await holder(db, user)
    if not can: raise BillingError("Only the company owner or an administrator can change the card.", 403)
    r = await record(db, key, c)
    if r.get("card_id") and SQ.configured():
        try: await SQ.disable_card(r["card_id"])
        except SQ.SquareError: pass
    for k in ("card_id", "card_brand", "card_last4", "card_exp_month", "card_exp_year"): r.pop(k, None)
    r.update(auto_renew=False, failure_count=0, next_attempt_on=None)
    await store.put(db, key, r)

# ------------------------------------------------------------------ charging
async def _notify_failed(db, r, row, again):
    try:
        email = r.get("payer_email")
        if email: await notify.notify(db, email, "billing_failed", "iSift subscription payment failed", f"We could not take your iSift payment ({row['error']}).{again} Please update your card under My account > Plan and billing to keep your plan.")
    except Exception as exc: log.warning("billing notice not sent: %s", exc)

async def charge_now(db, key: str, today: date | None = None) -> dict:
    """Charge the next period. Returns {status: paid|failed|skipped|free}. Safe to call twice."""
    today = today or date.today(); await load_prices(db)
    r = await record(db, key)
    if not r.get("card_id") or not r.get("customer_id"): return {"status": "skipped", "reason": "no card"}
    if not SQ.configured(): return {"status": "skipped", "reason": "square not configured"}
    plan, period = r["plan"], r.get("period", "monthly"); amt = cents(plan, period)
    pe = date.fromisoformat(r["period_end"]) if r.get("period_end") else None
    start = today if (pe is None or pe < today) else pe
    end = add_period(start, period)
    if amt <= 0:
        r.update(status="active", period_end=end.isoformat(), failure_count=0, next_attempt_on=None); await store.put(db, key, r); return {"status": "free"}
    idem = f"isift-{hashlib.sha1(key.encode()).hexdigest()[:12]}-{start.isoformat()}-{plan}-{period}-{r.get('failure_count', 0)}"
    ck = "charge:" + idem
    existing = await store.get(db, ck, {})
    if existing.get("status") == "paid": return {"status": "skipped", "reason": "already paid"}
    if existing.get("status") == "pending" and datetime.utcnow() - datetime.fromisoformat(existing["created"]) < PENDING_STALE: return {"status": "skipped", "reason": "another worker is charging"}
    row = {"id": idem, "status": "pending", "amount_cents": amt, "plan": plan, "period": period, "period_start": start.isoformat(), "period_end": end.isoformat(), "created": datetime.utcnow().isoformat()}
    if not existing:
        try:
            db.add(IntegrationSetting(key=ck, value=row)); await db.commit()            # the claim is visible BEFORE money moves
        except IntegrityError:
            await db.rollback(); return {"status": "skipped", "reason": "another worker is charging"}
    else: await store.put(db, ck, row)
    r = await record(db, key)
    try:
        pay = await SQ.create_payment(card_id=r["card_id"], customer_id=r["customer_id"], amount_cents=amt, idempotency_key=idem, email=r.get("payer_email", ""),
                                      note=f"iSift {PLANS[plan]['name']} ({period}) {start.isoformat()} to {end.isoformat()}", reference_id=hashlib.sha1(key.encode()).hexdigest()[:16])
        err = None if pay.get("status") in ("COMPLETED", "APPROVED") else SQ.SquareError("payment_" + str(pay.get("status")).lower(), f"Payment status {pay.get('status')}")
    except SQ.SquareError as e: pay, err = {}, e
    now = datetime.utcnow().isoformat() + "Z"
    if err:
        row.update(status="failed", error=(err.detail or err.code)[:280], settled=now)
        r["failure_count"] = r.get("failure_count", 0) + 1; r["last_error"] = row["error"]
        r["next_attempt_on"] = (today + timedelta(days=RETRY_DAYS)).isoformat() if r["failure_count"] < MAX_ATTEMPTS else None
        r["status"] = "past_due"
        r["charges"] = ([{k: row[k] for k in ("id", "status", "amount_cents", "plan", "period", "error", "settled")}] + r["charges"])[:12]
        await store.put(db, ck, row); await store.put(db, key, r)
        await _notify_failed(db, r, row, f" We will try again on {r['next_attempt_on']}." if r["next_attempt_on"] else " We will not retry automatically.")
        return {"status": "failed", "error": row["error"], "attempt": r["failure_count"]}
    row.update(status="paid", square_payment_id=pay.get("id"), receipt_url=pay.get("receipt_url"), settled=now, error=None)
    r.update(status="active", period_start=start.isoformat(), period_end=end.isoformat(), paid_cents=amt, failure_count=0, next_attempt_on=None, last_error=None)
    _add_payment(r, pay.get("id"), amt, now)
    r["charges"] = ([{k: row.get(k) for k in ("id", "status", "amount_cents", "plan", "period", "receipt_url", "settled")}] + r["charges"])[:12]
    await store.put(db, ck, row); await store.put(db, key, r)
    return {"status": "paid", "amount_cents": amt, "period_end": end.isoformat(), "receipt_url": row["receipt_url"]}

async def subscribe(db, user, plan: str, period: str, immediate: bool = False, terms: dict | None = None) -> dict:
    key, c, can = await holder(db, user)
    if not can: raise BillingError("Only the company owner or an administrator can change the plan.", 403)
    if plan not in PLANS: raise BillingError("Choose Basic, Personal Pro or Business.", 422)
    if period not in PERIODS: raise BillingError("Choose monthly or yearly.", 422)
    await load_prices(db); require_on_sale(plan)
    r = await record(db, key, c); today = date.today()
    if plan == "basic" and immediate and term_active(r, today): return await cancel_now(db, user)
    if plan != "basic" and term_active(r, today) and (plan, period) != (r["plan"], r.get("period", "monthly")): return await change_plan(db, user, plan, period, terms)
    if plan == "basic":                                                      # leaving a paid plan: it runs to the end of the paid period
        r["auto_renew"] = False
        if not r.get("period_end") or date.fromisoformat(r["period_end"]) < today or r["plan"] == "basic": r.update(plan="basic", status="active", period_end=None)
        await store.put(db, key, r); return {"status": "cancelled", "plan": r["plan"], "period_end": r.get("period_end")}
    if not r.get("card_id"): raise BillingError("Add a card first.", 409)
    if not SQ.configured(): raise BillingError("Card payments are not switched on yet. Ask your administrator to set up Square in Admin settings.", 503)
    paid_up = r["plan"] == plan and r.get("status") == "active" and r.get("period_end") and date.fromisoformat(r["period_end"]) > today
    auto, ends_on = terms_of(period, terms, today)
    before = {k: r.get(k) for k in ("plan", "period", "status", "period_end", "auto_renew", "ends_on")}
    r.update(plan=plan, period=period, auto_renew=auto, ends_on=ends_on)
    if paid_up:
        await store.put(db, key, r); return {"status": "scheduled", "period_end": r["period_end"]}
    r["period_end"] = None                                                   # a new plan starts today
    await store.put(db, key, r)
    res = await charge_now(db, key, today)
    if res["status"] != "paid":
        r = await record(db, key); r.update(before); r["failure_count"] = 0; r["next_attempt_on"] = None; await store.put(db, key, r)
        raise BillingError("The payment did not go through" + (": " + res["error"] if res.get("error") else "") + ". Your plan has not changed.", 402)
    return res

# ------------------------------------------------------------------ changing plan: credit, difference, refund
def _add_payment(r: dict, payment_id, amount_cents: int, when: str):
    """Remember each card payment so an approved refund can be sent back to the right one."""
    if payment_id: r["payments"] = ([{"id": payment_id, "amount_cents": amount_cents, "refunded_cents": 0, "at": when}] + list(r.get("payments", [])))[:8]

def _sub_period(d: date, period: str) -> date:
    months = 12 if period == "yearly" else 1
    y, mo = d.year + (d.month - 1 - months) // 12, (d.month - 1 - months) % 12 + 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))

def term_active(r: dict, today: date) -> bool:
    return r["plan"] != "basic" and r.get("status") == "active" and bool(r.get("period_end")) and date.fromisoformat(r["period_end"]) > today

def unused_credit(r: dict, today: date) -> int:
    """Straight-line value of the days left in the paid term (what was paid for it x days left / days in the term)."""
    if not term_active(r, today): return 0
    pe = date.fromisoformat(r["period_end"]); ps = date.fromisoformat(r["period_start"]) if r.get("period_start") else _sub_period(pe, r.get("period", "monthly"))
    total = max(1, (pe - ps).days); left = max(0, (pe - today).days)
    paid = r.get("paid_cents") or next((c["amount_cents"] for c in r.get("charges", []) if c.get("status") == "paid"), 0) or cents(r["plan"], r.get("period", "monthly"))
    return min(paid, round(paid * left / total))

def refundable(r: dict) -> int:
    return sum(max(0, p["amount_cents"] - p.get("refunded_cents", 0)) for p in r.get("payments", []))

async def quote(db, user, plan: str, period: str) -> dict:
    key, c, can = await holder(db, user)
    if plan not in PLANS: raise BillingError("Choose Basic, Personal Pro or Business.", 422)
    if period not in PERIODS: raise BillingError("Choose monthly or yearly.", 422)
    await load_prices(db); require_on_sale(plan)
    r = await record(db, key, c); today = date.today(); credit = unused_credit(r, today)
    if plan == "basic":
        return {"kind": "cancel" if credit else "none", "credit_cents": credit, "new_price_cents": 0, "charge_cents": 0, "refund_cents": credit, "effective": "today" if credit else None, "keeps_until": r.get("period_end")}
    new = cents(plan, period)
    if not credit or (plan == r["plan"] and period == r.get("period")):
        return {"kind": "new" if not credit else "same", "credit_cents": 0, "new_price_cents": new, "charge_cents": new if not credit else 0, "refund_cents": 0}
    return {"kind": "change", "credit_cents": credit, "new_price_cents": new, "charge_cents": max(0, new - credit), "refund_cents": max(0, credit - new), "new_period_end": add_period(today, period).isoformat()}

async def _request_refund(db, key: str, r: dict, amount: int, reason: str) -> dict:
    import uuid
    rid = uuid.uuid4().hex[:12]
    rf = {"id": rid, "billing_key": key, "email": r.get("payer_email") or "", "amount_cents": amount, "reason": reason[:200], "status": "pending", "created": datetime.utcnow().isoformat() + "Z", "done": [], "currency": settings.square_currency}
    await store.put(db, "refund:" + rid, rf)
    r["refund_ids"] = ([rid] + list(r.get("refund_ids", [])))[:20]
    return rf

async def _charge_extra(db, key: str, r: dict, amount: int, note: str, nonce: str) -> dict:
    """Take a one-off amount (the difference on an upgrade) from the card on file. Claim-first and idempotent like renewals."""
    idem = f"isift-chg-{hashlib.sha1(key.encode()).hexdigest()[:12]}-{nonce}-{r.get('chg_fail', 0)}"; ck = "charge:" + idem
    if await store.get(db, ck, {}): raise BillingError("This change is already being processed. Please wait a moment and refresh.", 409)
    row = {"id": idem, "status": "pending", "amount_cents": amount, "created": datetime.utcnow().isoformat()}
    try: db.add(IntegrationSetting(key=ck, value=row)); await db.commit()
    except IntegrityError: await db.rollback(); raise BillingError("This change is already being processed. Please wait a moment and refresh.", 409)
    try:
        pay = await SQ.create_payment(card_id=r["card_id"], customer_id=r["customer_id"], amount_cents=amount, idempotency_key=idem, email=r.get("payer_email", ""), note=note, reference_id=hashlib.sha1(key.encode()).hexdigest()[:16])
        err = None if pay.get("status") in ("COMPLETED", "APPROVED") else SQ.SquareError("payment_" + str(pay.get("status")).lower(), f"Payment status {pay.get('status')}")
    except SQ.SquareError as e: pay, err = {}, e
    if err:
        row.update(status="failed", error=(err.detail or err.code)[:280]); await store.put(db, ck, row)
        r["chg_fail"] = r.get("chg_fail", 0) + 1; await store.put(db, key, r)
        raise BillingError("The payment did not go through: " + row["error"] + ". Your plan has not changed.", 402)
    row.update(status="paid", square_payment_id=pay.get("id"), receipt_url=pay.get("receipt_url")); await store.put(db, ck, row)
    return {"payment": pay, "row": row}

async def change_plan(db, user, plan: str, period: str, terms: dict | None = None) -> dict:
    """Move between paid plans (or monthly/yearly) in the middle of a paid term. The unused days are credited against the new price:
    the difference is charged now; if the credit is bigger than the new price the plan switches at once and the leftover becomes a REFUND REQUEST an administrator must approve."""
    key, c, can = await holder(db, user)
    if not can: raise BillingError("Only the company owner or an administrator can change the plan.", 403)
    r = await record(db, key, c); today = date.today(); q = await quote(db, user, plan, period); auto, ends_on = terms_of(period, terms, today)
    if q["kind"] != "change": raise BillingError("Nothing to change.")
    if not r.get("card_id"): raise BillingError("Add a card first.", 409)
    if not SQ.configured(): raise BillingError("Card payments are not switched on yet. Ask your administrator to set up Square in Admin settings.", 503)
    old = (r["plan"], r.get("period")); paid_now = None
    if q["charge_cents"] > 0:
        res = await _charge_extra(db, key, r, q["charge_cents"], f"iSift change {PLANS[old[0]]['name']} to {PLANS[plan]['name']} ({period}): difference after {q['credit_cents']/100:.2f} credit", f"{r.get('period_end')}-{plan}-{period}-{today.isoformat()}")
        paid_now = res
    r = await record(db, key, c)
    end = add_period(today, period)
    r.update(plan=plan, period=period, status="active", period_start=today.isoformat(), period_end=end.isoformat(), paid_cents=q["new_price_cents"], auto_renew=auto, ends_on=ends_on, failure_count=0, next_attempt_on=None, last_error=None, chg_fail=0)
    if paid_now:
        _add_payment(r, paid_now["payment"].get("id"), q["charge_cents"], datetime.utcnow().isoformat() + "Z")
        r["charges"] = ([{"id": paid_now["row"]["id"], "status": "paid", "amount_cents": q["charge_cents"], "plan": plan, "period": period, "receipt_url": paid_now["row"].get("receipt_url"), "settled": datetime.utcnow().isoformat() + "Z", "note": "Difference after credit"}] + r.get("charges", []))[:12]
    rf = None
    if q["refund_cents"] > 0:
        rf = await _request_refund(db, key, r, q["refund_cents"], f"Changed from {PLANS[old[0]]['name']} ({old[1]}) to {PLANS[plan]['name']} ({period}); unused time exceeded the new price")
    await store.put(db, key, r)
    return {"status": "changed", "plan": plan, "period_end": end.isoformat(), "credit_cents": q["credit_cents"], "charged_cents": q["charge_cents"], "refund_requested_cents": q["refund_cents"], "refund_id": rf["id"] if rf else None}

async def cancel_now(db, user) -> dict:
    """End a paid plan today instead of at the end of the term, and ask for the unused time back (approval needed)."""
    key, c, can = await holder(db, user)
    if not can: raise BillingError("Only the company owner or an administrator can change the plan.", 403)
    r = await record(db, key, c); credit = unused_credit(r, date.today())
    if not credit: raise BillingError("There is no paid time left to refund.")
    was = PLANS[r["plan"]]["name"]
    rf = await _request_refund(db, key, r, credit, f"Ended {was} early; refund of unused time")
    r.update(plan="basic", status="active", period_end=None, period_start=None, paid_cents=0, auto_renew=False, failure_count=0, next_attempt_on=None)
    await store.put(db, key, r)
    return {"status": "ended", "plan": "basic", "refund_requested_cents": credit, "refund_id": rf["id"]}

# ------------------------------------------------------------------ refunds (an administrator approves each one)
def _refund_view(x: dict) -> dict:
    return {k: x.get(k) for k in ("id", "amount_cents", "approved_cents", "reason", "status", "created", "decided", "decided_by", "note", "email", "account", "currency")} | {"paid_back_cents": sum(d["cents"] for d in x.get("done", []))}

async def user_refunds(db, r: dict) -> list[dict]:
    out = []
    for rid in r.get("refund_ids", [])[:10]:
        x = await store.get(db, "refund:" + rid, {})
        if x: out.append(_refund_view(x))
    return out

async def list_refunds(db, status: str = "") -> list[dict]:
    rows = (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like("refund:%")))).scalars().all()
    out = []
    for x in rows:
        if status and x.value.get("status") != status: continue
        v = _refund_view(x.value); bk = x.value.get("billing_key", "")
        v["account"] = ("Company " + (await store.get(db, "company:" + bk.split(":")[2], {})).get("name", "")) if bk.startswith("billing:co:") else (x.value.get("email") or "Person")
        r = await store.get(db, bk, {}); v["refundable_cents"] = refundable(r) if r else 0
        out.append(v)
    return sorted(out, key=lambda v: v["created"] or "", reverse=True)

async def approve_refund(db, rid: str, admin: str, amount_cents: int | None = None, note: str = "") -> dict:
    x = await store.get(db, "refund:" + rid, {})
    if not x: raise BillingError("No such refund request.", 404)
    if x["status"] not in ("pending", "partial"): raise BillingError("That request has already been decided.", 409)
    if not SQ.configured(): raise BillingError("Square is not set up, so the refund cannot be sent.", 503)
    amount = int(amount_cents or x.get("approved_cents") or x["amount_cents"])
    if amount < 1 or amount > x["amount_cents"]: raise BillingError(f"Enter an amount between 0.01 and {x['amount_cents']/100:.2f}.", 422)
    if x.get("approved_cents") and amount != x["approved_cents"]: raise BillingError("A part of this refund has already been sent; finish it with the same amount.", 409)
    r = await store.get(db, x["billing_key"], {})
    left = amount - sum(d["cents"] for d in x.get("done", []))
    if left > refundable(r): raise BillingError(f"Only {refundable(r)/100:.2f} can still be returned to the card for this account.", 409)
    for p in list(r.get("payments", [])):
        if left <= 0: break
        take = min(left, p["amount_cents"] - p.get("refunded_cents", 0))
        if take <= 0: continue
        try:
            ref = await SQ.refund_payment(payment_id=p["id"], amount_cents=take, idempotency_key=f"isift-refund-{rid}-{p['id']}-{take}-{len(x.get('done', []))}", reason=x["reason"])
        except SQ.SquareError as e:
            x["status"] = "partial" if x.get("done") else "pending"; await store.put(db, "refund:" + rid, x); await store.put(db, x["billing_key"], r)
            raise BillingError("Square could not send the refund: " + (e.detail or e.code) + (" Part was already sent; press Approve again to finish." if x.get("done") else ""), 502)
        p["refunded_cents"] = p.get("refunded_cents", 0) + take; left -= take
        x["approved_cents"] = amount
        x.setdefault("done", []).append({"payment_id": p["id"], "cents": take, "square_refund_id": ref.get("id"), "square_status": ref.get("status")})
    x.update(status="approved", decided=datetime.utcnow().isoformat() + "Z", decided_by=admin, note=note[:300])
    await store.put(db, "refund:" + rid, x); await store.put(db, x["billing_key"], r)
    if x.get("email"):
        try: await notify.notify(db, x["email"], "billing_refund", "Your iSift refund was approved", f"{amount/100:.2f} {x.get('currency', '')} is being returned to your card. It can take a few days to appear.")
        except Exception as exc: log.warning("refund notice not sent: %s", exc)
    return _refund_view(x)

async def decline_refund(db, rid: str, admin: str, note: str = "") -> dict:
    x = await store.get(db, "refund:" + rid, {})
    if not x: raise BillingError("No such refund request.", 404)
    if x["status"] != "pending": raise BillingError("That request has already been decided.", 409)
    x.update(status="declined", decided=datetime.utcnow().isoformat() + "Z", decided_by=admin, note=note[:300]); await store.put(db, "refund:" + rid, x)
    if x.get("email"):
        try: await notify.notify(db, x["email"], "billing_refund", "Your iSift refund request was declined", (note or "Please contact support if you have questions.")[:300])
        except Exception as exc: log.warning("refund notice not sent: %s", exc)
    return _refund_view(x)

async def run_due(db, today: date | None = None) -> dict:
    """Renew every account whose period has ended (retrying declines on schedule) and drop lapsed ones to Basic. Never raises."""
    today = today or date.today(); out = {"paid": 0, "failed": 0, "skipped": 0, "lapsed": 0, "errors": 0}
    keys = [k for (k,) in (await db.execute(select(IntegrationSetting.key).where(IntegrationSetting.key.like("billing:%")))).all()]
    for key in keys:
        try:
            r = await record(db, key)
            if r["plan"] == "basic" or not r.get("period_end"): out["skipped"] += 1; continue
            pe = date.fromisoformat(r["period_end"])
            if today <= pe: out["skipped"] += 1; continue
            if not r.get("auto_renew") or not r.get("card_id") or (r.get("ends_on") and pe >= date.fromisoformat(r["ends_on"])) or today > pe + timedelta(days=GRACE_DAYS) or r.get("failure_count", 0) >= MAX_ATTEMPTS and today > pe + timedelta(days=GRACE_DAYS):
                r.update(plan="basic", status="active", period_end=None, auto_renew=False, ends_on=None); await store.put(db, key, r); out["lapsed"] += 1; continue
            if r.get("failure_count", 0) >= MAX_ATTEMPTS or (r.get("next_attempt_on") and today < date.fromisoformat(r["next_attempt_on"])): out["skipped"] += 1; continue
            res = await charge_now(db, key, today); out[res["status"] if res["status"] in out else "skipped"] += 1
        except Exception:
            await db.rollback(); log.exception("billing run failed for %s", key); out["errors"] += 1
    return out

async def overview(db) -> dict:
    rows = (await db.execute(select(IntegrationSetting).where(IntegrationSetting.key.like("billing:%")))).scalars().all()
    return {"accounts": [{"account": ("Company " + (await store.get(db, "company:" + x.key.split(":")[2], {})).get("name", "")) if x.key.startswith("billing:co:") else "Person " + x.key[8:14],
                          "plan": PLANS[norm_plan(x.value.get("plan"))]["name"], "period": x.value.get("period"), "status": x.value.get("status"), "period_end": x.value.get("period_end"),
                          "card": f"{x.value.get('card_brand', '')} ···· {x.value.get('card_last4')}" if x.value.get("card_id") else None, "auto_renew": bool(x.value.get("auto_renew")),
                          "failure_count": x.value.get("failure_count", 0), "last_error": x.value.get("last_error")} for x in rows]}

async def test_square() -> dict:
    if not SQ.configured(): return {"configured": False, "status": "not_configured", "detail": "Still needed: " + ", ".join(SQ.missing()) + "."}
    try: loc = await SQ.get_location()
    except SQ.SquareError as e: return {"configured": True, "status": "failed", "detail": "Square said: " + (e.detail or e.code)}
    cur = loc.get("currency")
    if cur and cur != settings.square_currency: return {"configured": True, "status": "failed", "detail": f"This Square location charges in {cur} but the billing currency is {settings.square_currency}. Change one of them."}
    return {"configured": True, "status": "connected", "detail": f"Connected to Square location \"{loc.get('name', settings.square_location_id)}\" ({loc.get('country', '')}, {cur or settings.square_currency}, {SQ.env()})."}
