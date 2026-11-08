"""A plain log of real iSift meetings: when each one ran and for how long.

It lives in the same store as the other per-person counters, newest last, and keeps the most recent entries only.
The room code is never kept here (it is the secret that lets people in), so the admin report cannot leak it.
"""
from datetime import datetime, timezone
from app.services import store

_KEY = "meeting-log:all"
_KEEP = 2000


async def read(db) -> list[dict]:
    d = await store.get(db, _KEY, {})
    return list((d or {}).get("items") or [])


async def record(db, *, title: str, host_email: str, started_ts: float, ended_ts: float) -> None:
    minutes = round(max(0.0, ended_ts - started_ts) / 60, 1)
    if minutes < 0.1:                                   # a room opened by accident and closed straight away is not a meeting
        return
    items = await read(db)
    items.append({
        "title": (title or "")[:200],
        "host": (host_email or "").strip().lower(),
        "started_at": datetime.fromtimestamp(started_ts, timezone.utc).isoformat(),
        "ended_at": datetime.fromtimestamp(ended_ts, timezone.utc).isoformat(),
        "minutes": minutes,
    })
    await store.put(db, _KEY, {"items": items[-_KEEP:]})
