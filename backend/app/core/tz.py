"""Time zones that never crash the app. Windows has no built-in time zone database, so a missing zone falls back
to this computer's own time zone (or UTC) instead of raising an error."""
import logging
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

log = logging.getLogger("isift")
_warned: set[str] = set()

def zone(name: str | None) -> tzinfo:
    try:
        return ZoneInfo(str(name or "UTC"))
    except Exception:
        if name not in _warned:
            _warned.add(str(name)); log.warning("Time zone %r is not available here (install the 'tzdata' package); using this computer's time zone.", name)
        return datetime.now().astimezone().tzinfo or timezone.utc


import contextvars, re
_REQ: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_tz", default=None)

def set_request_zone(name: str | None) -> None:
    """Remember the time zone the person's device reported for this request (ignored if unknown or malformed)."""
    name = (name or "").strip()
    if name and re.fullmatch(r"[A-Za-z0-9_+\-]+(/[A-Za-z0-9_+\-]+){0,2}", name) and len(name) <= 64:
        try: ZoneInfo(name); _REQ.set(name); return
        except Exception: pass
    _REQ.set(None)

def request_zone() -> tzinfo | None:
    name = _REQ.get()
    return ZoneInfo(name) if name else None
