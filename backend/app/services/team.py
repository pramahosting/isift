"""Team plan helpers: who is on my team, and the shared booking pages that rotate between them.

A team is a company account on the Business plan. Nothing new is stored on the booking page itself: the list of people who
share it lives in a small record keyed by the page id, so no schema change is needed.
"""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import User
from app.services import billing, store

def _em(e: str) -> str: return (e or "").strip().lower()

async def members(db, user) -> list[str] | None:
    """Emails of everyone on the person's company account, or None when they are not on a Business company account."""
    key, company, _ = await billing.holder(db, user)
    if not company: return None
    if user.role != "admin" and (await billing.record(db, key, company))["plan"] != "business": return None
    return [_em(m["email"]) for m in company.get("members", [])]

async def need_team(db, user) -> list[str]:
    m = await members(db, user)
    if m is None: raise HTTPException(402, "Team sharing is part of the Business plan with a company account. Create or join a company under Account to use it.")
    return m

async def users_by_email(db, emails: list[str]) -> dict[str, User]:
    if not emails: return {}
    rows = (await db.execute(select(User).where(User.email.in_(emails)))).scalars().all()
    return {u.email.lower(): u for u in rows}

def page_key(type_id: str) -> str: return f"teampage:{type_id}"

async def page_members(db, type_id: str) -> list[str]:
    return list((await store.get(db, page_key(type_id), {})).get("members", []))

async def hosts_of(db, bt, owner: User) -> list[User]:
    """The people who take bookings from this page: the owner first, then each chosen teammate who is still on the owner's team."""
    chosen = await page_members(db, bt.id)
    if not chosen: return [owner]
    team = await members(db, owner)
    if team is None: return [owner]
    found = await users_by_email(db, [e for e in chosen if e in team and e != _em(owner.email)])
    return [owner] + [found[e] for e in chosen if e in found and e != _em(owner.email) and found[e].is_active]
