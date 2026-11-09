"""Where visitors came from: one line per visit that arrived on a tagged link (utm_content=day3 and so on),
and the first tag each signed-in person arrived with. No cookies, no IP address, nothing about the person is kept
beyond a random browser id, so a visit can be counted once a day."""
import re
from datetime import datetime, timezone
from app.services import store

_LOG, _ATTR, _KEEP = "visits:log", "visits:attr", 5000
_OK = re.compile(r"[^A-Za-z0-9._ -]")


def clean(v, n=60) -> str:
    return _OK.sub("", str(v or "")).strip()[:n]


async def log(db) -> list[dict]:
    return list(((await store.get(db, _LOG, {})) or {}).get("items") or [])


async def record_visit(db, *, source, medium, campaign, content, vid) -> bool:
    source, medium, campaign, content, vid = clean(source), clean(medium), clean(campaign), clean(content), clean(vid, 40)
    if not (source or content or campaign): return False
    now = datetime.now(timezone.utc); day = now.date().isoformat()
    items = await log(db)
    if vid and any(i.get("vid") == vid and i.get("content") == content and i.get("source") == source and i.get("at", "")[:10] == day for i in items[-500:]):
        return False                                           # the same browser counts once a day for the same link
    items.append({"at": now.isoformat(), "source": source, "medium": medium, "campaign": campaign, "content": content, "vid": vid})
    await store.put(db, _LOG, {"items": items[-_KEEP:]})
    return True


async def attribution(db) -> dict:
    return dict(((await store.get(db, _ATTR, {})) or {}).get("people") or {})


async def attribute(db, email: str, *, source, medium, campaign, content) -> bool:
    """Remember the link a person first arrived with. The first one is kept; later ones are ignored."""
    email = (email or "").strip().lower()
    source, medium, campaign, content = clean(source), clean(medium), clean(campaign), clean(content)
    if not email or not (source or content or campaign): return False
    people = await attribution(db)
    if email in people: return False
    people[email] = {"source": source, "medium": medium, "campaign": campaign, "content": content, "at": datetime.now(timezone.utc).isoformat()}
    await store.put(db, _ATTR, {"people": people})
    return True
