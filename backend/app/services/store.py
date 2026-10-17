"""Small JSON records kept in the integration_settings table, keyed by person (a hash of the email address) so no schema change is needed."""
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import IntegrationSetting

def hkey(prefix: str, email: str) -> str: return f"{prefix}:{hashlib.sha1((email or '').strip().lower().encode()).hexdigest()}"

async def get(db: AsyncSession, key: str, default=None):
    row = await db.get(IntegrationSetting, key)
    return dict(row.value) if row and row.value else (default if default is not None else {})

async def put(db: AsyncSession, key: str, value: dict, commit: bool = True):
    row = await db.get(IntegrationSetting, key)
    if row: row.value = value
    else: db.add(IntegrationSetting(key=key, value=value))
    if commit: await db.commit()

async def drop(db: AsyncSession, key: str):
    row = await db.get(IntegrationSetting, key)
    if row: await db.delete(row); await db.commit()
