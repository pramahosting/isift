"""Small JSON records kept in the integration_settings table, keyed by person (a hash of the email address) so no schema change is needed."""
import hashlib
from sqlalchemy import event
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import IntegrationSetting

@event.listens_for(Session, "after_commit")
def _forget_misses(session): session.info.pop("_miss", None)       # anything saved may now exist, so "not found" answers are forgotten

async def _fetch(db: AsyncSession, key: str):
    """The record, asking the database only once per request for a key that does not exist (a remote database makes every question slow)."""
    miss = db.info.setdefault("_miss", set())
    if key in miss: return None
    row = await db.get(IntegrationSetting, key)
    if row is None: miss.add(key)
    return row

def hkey(prefix: str, email: str) -> str: return f"{prefix}:{hashlib.sha1((email or '').strip().lower().encode()).hexdigest()}"

async def get(db: AsyncSession, key: str, default=None):
    row = await _fetch(db, key)
    return dict(row.value) if row and row.value else (default if default is not None else {})

async def put(db: AsyncSession, key: str, value: dict, commit: bool = True):
    row = await db.get(IntegrationSetting, key)
    db.info.get("_miss", set()).discard(key)
    if row: row.value = value
    else: db.add(IntegrationSetting(key=key, value=value))
    if commit: await db.commit()

async def drop(db: AsyncSession, key: str):
    db.info.get("_miss", set()).discard(key)
    row = await db.get(IntegrationSetting, key)
    if row: await db.delete(row); await db.commit()
