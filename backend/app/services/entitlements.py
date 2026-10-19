"""What each person may do, by plan, with the administrator's per-person changes on top.

Basic: no Commbox (mail, calendar, contacts), no open room, meetings of up to 70 minutes, no recording, 5 new documents or whiteboards a day, PDFs of up to 5 pages.
Individual / Business: everything on. Administrators: everything on, no limits.
The administrator can raise or lower any of these for a single person (Admin > Users > Limits). A count of 0 means "no limit"."""
from datetime import date
from app.services import billing, store

BASIC = {"commbox": False, "open_room": False, "recording": False, "meeting_minutes": 70, "docs_per_day": 5, "pdf_pages": 5}
OPEN = {"commbox": True, "open_room": True, "recording": True, "meeting_minutes": 0, "docs_per_day": 0, "pdf_pages": 0}
WARN_MINUTES = 10
FIELDS = {"commbox": bool, "open_room": bool, "recording": bool, "meeting_minutes": int, "docs_per_day": int, "pdf_pages": int}

def _key(email: str) -> str: return store.hkey("profile", email)

async def overrides(db, email: str) -> dict:
    return dict((await store.get(db, _key(email), {})).get("limits") or {})

async def set_overrides(db, email: str, changes: dict) -> dict:
    """changes: field -> value, or None to go back to the plan's default."""
    p = await store.get(db, _key(email), {}); cur = dict(p.get("limits") or {})
    for k, v in changes.items():
        if k not in FIELDS: continue
        if v is None: cur.pop(k, None)
        else: cur[k] = bool(v) if FIELDS[k] is bool else max(0, min(int(v), 100000))
    if cur: p["limits"] = cur
    else: p.pop("limits", None)
    await store.put(db, _key(email), p)
    return cur

async def limits(db, user) -> dict:
    """The person's effective limits. 0 for a count means unlimited."""
    if user is None: return dict(BASIC)
    if user.role == "admin": return {**OPEN, "plan": "admin", "custom": {}}
    plan = await billing.plan_of(db, user)
    base = dict(BASIC if plan == "basic" else {**OPEN, "pdf_pages": 0})
    base["open_room"] = plan != "basic"; base["commbox"] = plan != "basic"
    custom = await overrides(db, user.email)
    base.update({k: v for k, v in custom.items() if k in FIELDS})
    return {**base, "plan": plan, "custom": custom}

async def can_open_room(db, user) -> bool: return bool((await limits(db, user))["open_room"])

# ---- documents a day (Docs modules and whiteboards) ----
async def docs_used(db, user) -> int:
    d = await store.get(db, store.hkey("docs-usage", user.email), {})
    return int(d.get("n", 0)) if d.get("day") == date.today().isoformat() else 0

async def use_document(db, user) -> None:
    """Count one more document today, or refuse (HTTP 403) when the person's daily number is used up."""
    from fastapi import HTTPException
    lim = (await limits(db, user))["docs_per_day"]; n = await docs_used(db, user)
    if lim and n >= lim:
        raise HTTPException(403, f"You have used your {lim} documents for today. The Basic plan includes {lim} new Docs files, whiteboards or PDF/Word edits a day. Upgrade your plan, or ask an administrator for more.")
    await store.put(db, store.hkey("docs-usage", user.email), {"day": date.today().isoformat(), "n": n + 1})

async def need_commbox(user, db) -> None:
    from fastapi import HTTPException
    if not (await limits(db, user))["commbox"]: raise HTTPException(403, "Commbox (mail, calendar and contacts) is not included in the Basic plan. Upgrade your plan, or ask an administrator to allow it for you.")

async def summary(db, user) -> dict:
    L = await limits(db, user)
    return {**L, "docs_used_today": await docs_used(db, user), "warn_minutes": WARN_MINUTES}
