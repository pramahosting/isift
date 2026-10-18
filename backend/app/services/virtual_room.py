"""Is the virtual room (boardroom table view) switched on for a meeting?

It must be on in all three places: for the whole service (Admin settings), for the host's account (My account, or an administrator
in Admin > Users) and for the meeting itself (the checkbox in the meeting options). Off anywhere means everyone sees the plain gallery.
"""
from app.core.config import settings
from app.services import store

async def account_on(db, email: str) -> bool:
    return (await store.get(db, store.hkey("profile", email), {})).get("virtual_room", True) is not False

async def effective(db, host, options: dict | None) -> bool:
    if not settings.room_virtual_enabled: return False
    if (options or {}).get("virtual_room", False) is not True: return False
    return await account_on(db, host.email) if host else True

async def set_account(db, email: str, on: bool, commit: bool = False) -> None:
    p = await store.get(db, store.hkey("profile", email), {}); p["virtual_room"] = bool(on)
    await store.put(db, store.hkey("profile", email), p, commit=commit)
