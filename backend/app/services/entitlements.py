"""What each person may do, by plan, with the administrator's per-person changes on top.

Basic: 100 MB of storage, 20 hours of hosted meetings a month, 3 AI minutes summaries a month, 1 booking page, no calls, no Commbox (mail, calendar, contacts), no open room, meetings of up to 70 minutes, no recording, 5 new documents or whiteboards a day, PDFs of up to 5 pages.
Personal Pro / Business: everything on. Administrators: everything on, no limits.
The administrator can raise or lower any of these for a single person (Admin > Users > Limits). A count of 0 means "no limit"."""
from datetime import date
from app.services import billing, store

BASIC = {"calls": False, "ai_per_month": 3, "booking_pages": 1, "commbox": False, "open_room": False, "recording": False, "meeting_minutes": 70, "docs_per_day": 5, "pdf_pages": 5, "storage_mb": 100, "meeting_hours_per_month": 20, "max_participants": 100}
OPEN = {"calls": True, "ai_per_month": 0, "booking_pages": 0, "commbox": True, "open_room": True, "recording": True, "meeting_minutes": 0, "docs_per_day": 0, "pdf_pages": 0, "storage_mb": 0, "meeting_hours_per_month": 0, "max_participants": 0}
PAID_DEFAULT = {"pdf_pages": 0, "storage_mb": 5120, "meeting_hours_per_month": 300, "max_participants": 100}      # fair-use ceilings for Personal Pro and Business (5 GB, 300 hours)
WARN_MINUTES = 10
FIELDS = {"calls": bool, "ai_per_month": int, "booking_pages": int, "commbox": bool, "open_room": bool, "recording": bool, "meeting_minutes": int, "docs_per_day": int, "pdf_pages": int, "storage_mb": int, "meeting_hours_per_month": int, "max_participants": int}

def _key(email: str) -> str: return store.hkey("profile", email)

async def overrides(db, email: str) -> dict:
    return dict((await store.get(db, _key(email), {})).get("limits") or {})

async def set_overrides(db, email: str, changes: dict) -> dict:
    """changes: field -> value, or None to go back to the plan's default."""
    p = await store.get(db, _key(email), {}); cur = dict(p.get("limits") or {})
    for k, v in changes.items():
        if k not in FIELDS: continue
        if v is None: cur.pop(k, None)
        else: cur[k] = bool(v) if FIELDS[k] is bool else max(0, min(int(v), 10000000))
    if cur: p["limits"] = cur
    else: p.pop("limits", None)
    await store.put(db, _key(email), p)
    return cur

PLAN_IDS = ("basic", "individual", "business")
PLAN_KEY = "plan-config"

def plan_defaults(plan: str) -> dict:
    """The built-in limits of a plan, before the administrator's changes for the plan or for one person."""
    base = dict(BASIC if plan == "basic" else {**OPEN, **PAID_DEFAULT})
    base["open_room"] = plan != "basic"; base["commbox"] = plan != "basic"; base["calls"] = plan != "basic"
    return base

async def plan_config(db) -> dict:
    return await store.get(db, PLAN_KEY, {})

async def set_plan_config(db, plan: str, limits_changes: dict, modules_off: list | None = None) -> dict:
    """limits_changes: field -> value, or None to go back to the built-in value. modules_off: ids of modules this plan does not include."""
    cfg = await plan_config(db); cur = dict(cfg.get(plan, {})); lim = dict(cur.get("limits") or {})
    for k, v in (limits_changes or {}).items():
        if k not in FIELDS: continue
        if v is None: lim.pop(k, None)
        else: lim[k] = bool(v) if FIELDS[k] is bool else max(0, min(int(v), 10000000))
    cur["limits"] = lim
    if modules_off is not None: cur["modules_off"] = sorted({str(m) for m in modules_off})
    cfg[plan] = cur
    await store.put(db, PLAN_KEY, cfg)
    return cur

async def modules_off(db, user) -> list[str]:
    """Modules this person's plan does not include (the ones switched off for everyone are handled separately)."""
    if user is None or user.role == "admin": return []
    plan = await billing.plan_of(db, user)
    return list((await plan_config(db)).get(plan, {}).get("modules_off") or [])

async def limits(db, user) -> dict:
    """The person's effective limits. 0 for a count means unlimited."""
    if user is None: return dict(BASIC)
    if user.role == "admin": return {**OPEN, "plan": "admin", "custom": {}}
    plan = await billing.plan_of(db, user)
    base = plan_defaults(plan)
    base.update({k: v for k, v in (await plan_config(db)).get(plan, {}).get("limits", {}).items() if k in FIELDS})         # what the administrator set for the whole plan
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

# ---- AI minutes a month and booking pages ----
async def ai_used(db, user) -> int:
    d = await store.get(db, store.hkey("ai-usage", user.email), {})
    return int(d.get("n", 0)) if d.get("month") == date.today().strftime("%Y-%m") else 0

async def use_ai(db, user) -> None:
    from fastapi import HTTPException
    lim = (await limits(db, user))["ai_per_month"]; n = await ai_used(db, user)
    if lim and n >= lim:
        raise HTTPException(403, f"You have used your {lim} AI minutes summaries for this month. The Basic plan includes {lim} a month. Upgrade your plan, or ask an administrator for more.")
    await store.put(db, store.hkey("ai-usage", user.email), {"month": date.today().strftime("%Y-%m"), "n": n + 1})
    await bump(db, user.email, "ai_summaries", 1)

async def check_booking_pages(db, user, have: int) -> None:
    from fastapi import HTTPException
    lim = (await limits(db, user))["booking_pages"]
    if lim and have >= lim:
        raise HTTPException(403, f"The Basic plan includes {lim} booking page{'s' if lim != 1 else ''}. Upgrade your plan, or ask an administrator to allow more.")

async def need_calls(user, db) -> None:
    from fastapi import HTTPException
    if not (await limits(db, user))["calls"]: raise HTTPException(403, "Calling other people is not included in the Basic plan. Upgrade your plan, or ask an administrator to allow it for you. You can still receive calls.")

async def need_commbox(user, db) -> None:
    from fastapi import HTTPException
    if not (await limits(db, user))["commbox"]: raise HTTPException(403, "Commbox (mail, calendar and contacts) is not included in the Basic plan. Upgrade your plan, or ask an administrator to allow it for you.")

# ---- storage: documents, whiteboards and cloud recordings ----
async def storage_used(db, user) -> int:
    """Bytes this person keeps in iSift: the text of their Docs and whiteboards plus cloud recordings of meetings they host."""
    from sqlalchemy import select, func
    from app.models import Note, Room, RoomRecording
    notes = (await db.execute(select(func.coalesce(func.sum(func.length(Note.content)), 0)).where(Note.owner_id == user.id))).scalar() or 0
    recs = (await db.execute(select(func.coalesce(func.sum(RoomRecording.size_bytes), 0)).join(Room, Room.id == RoomRecording.room_id).where(Room.host_id == user.id))).scalar() or 0
    return int(notes) + int(recs)

async def check_storage(db, user, adding: int) -> None:
    """Refuse (HTTP 403) when `adding` more bytes would pass the person's storage allowance. Always lets shrinking edits through."""
    from fastapi import HTTPException
    if adding <= 0 or user is None: return
    mb = (await limits(db, user))["storage_mb"]
    if mb and await storage_used(db, user) + adding > mb * 1024 * 1024:
        raise HTTPException(403, f"Your storage is full ({mb} MB). Delete old documents or recordings to make room, upgrade your plan, or ask an administrator for more.")

# ---- hosted meeting hours a month ----
def _month() -> str: return date.today().strftime("%Y-%m")

async def hours_used(db, user) -> float:
    d = await store.get(db, store.hkey("meet-usage", user.email), {})
    return round(float(d.get("minutes", 0)) / 60, 2) if d.get("month") == _month() else 0.0

async def add_meeting_minutes(db, email: str, minutes: float) -> None:
    d = await store.get(db, store.hkey("meet-usage", email), {}); m = float(d.get("minutes", 0)) if d.get("month") == _month() else 0.0
    await store.put(db, store.hkey("meet-usage", email), {"month": _month(), "minutes": round(m + max(0.0, minutes), 2)})
    await bump(db, email, "minutes", max(0.0, float(minutes))); await bump(db, email, "meetings", 1)

async def minutes_left(db, user) -> int | None:
    """Minutes of hosting left this month, or None when there is no monthly limit."""
    lim = (await limits(db, user))["meeting_hours_per_month"]
    if not lim: return None
    return max(0, int(lim * 60 - await hours_used(db, user) * 60))

async def summary(db, user) -> dict:
    L = await limits(db, user)
    return {**L, "docs_used_today": await docs_used(db, user), "ai_used_month": await ai_used(db, user), "storage_used_mb": round(await storage_used(db, user) / 1048576, 1), "hours_used_month": await hours_used(db, user), "warn_minutes": WARN_MINUTES, "modules_off": await modules_off(db, user)}


# ---- monthly usage report (the dashboard tiles) ----
STAT_KEYS = ("meetings", "minutes", "recordings", "pdf_edited", "pdf_signed", "docs_created", "boards_created", "docs_edited", "calls", "ai_summaries")
_STAT_KEEP = 13           # months of history kept per person

def _stat_key(email: str) -> str: return store.hkey("usage-stats", email)

async def bump(db, email: str, counter: str, n: float = 1, ref: str | None = None) -> None:
    """Count one thing for this person this month. With `ref`, the same thing is counted once a month (e.g. the same document edited again)."""
    if not email or counter not in STAT_KEYS: return
    try:
        d = await store.get(db, _stat_key(email), {}); months = dict(d.get("months") or {})
        cur = dict(months.get(_month()) or {})
        if ref is not None:
            seen = list(cur.get("_seen_" + counter) or [])
            if ref in seen: return
            cur["_seen_" + counter] = (seen + [ref])[-500:]
        cur[counter] = round(float(cur.get(counter, 0)) + n, 2) if isinstance(n, float) else int(cur.get(counter, 0)) + int(n)
        months[_month()] = cur
        for old in sorted(months)[:-_STAT_KEEP]: months.pop(old, None)
        await store.put(db, _stat_key(email), {"months": months})
    except Exception:
        import logging; logging.getLogger("isift").exception("Could not count usage")

def _clean(m: dict) -> dict:
    out = {k: m.get(k, 0) for k in STAT_KEYS}
    out["hours"] = round(float(out.pop("minutes") or 0) / 60, 1)
    return out

async def usage_stats(db, user) -> dict:
    d = await store.get(db, _stat_key(user.email), {}); months = d.get("months") or {}
    now = date.today(); keys = []
    y, m = now.year, now.month
    for _ in range(6):
        keys.append(f"{y:04d}-{m:02d}"); m -= 1
        if m == 0: y, m = y - 1, 12
    keys.reverse()
    L = await limits(db, user)
    return {"month": _month(), "current": _clean(months.get(_month()) or {}), "previous": _clean(months.get(keys[-2]) or {}),
            "history": [{"month": k, **_clean(months.get(k) or {})} for k in keys],
            "caps": {"hours": L["meeting_hours_per_month"], "ai_summaries": L["ai_per_month"], "recording": L["recording"], "calls": L["calls"], "storage_mb": L["storage_mb"]},
            "storage_used_mb": round(await storage_used(db, user) / 1048576, 1)}
