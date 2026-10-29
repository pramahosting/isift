"""In-app alerts (for example 'Ann invited you to a meeting'), kept per person and shown by the bell in the top bar."""
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.services import store

MAX_KEPT = 50

async def notify(db: AsyncSession, email: str, kind: str, title: str, text: str = "", url: str = "", sender: str = "") -> dict:
    key = store.hkey("notif", email); rec = await store.get(db, key, {"items": []})
    item = {"id": uuid.uuid4().hex[:12], "kind": kind, "title": title[:200], "text": text[:500], "url": url[:500], "from": sender[:200], "at": datetime.now(timezone.utc).isoformat(), "read": False}
    rec["items"] = ([item] + list(rec.get("items", [])))[:MAX_KEPT]
    await store.put(db, key, rec)
    try:
        from app.services import push
        await push.safe_send(db, email, title, text, url, "n-" + item["id"], kind)       # also to the person's phone / computer if they turned notifications on
    except Exception: pass
    return item
