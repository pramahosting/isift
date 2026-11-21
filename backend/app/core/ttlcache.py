"""Tiny in-memory cache for answers that change rarely (price list, plan matrix). One database read per TTL instead of one per visitor."""
import time, functools

def ttl_cache(seconds: float):
    def deco(fn):
        box = {"at": 0.0, "val": None}
        @functools.wraps(fn)
        async def wrapper(*a, **kw):
            if box["val"] is not None and time.time() - box["at"] < seconds: return box["val"]
            box["val"] = await fn(*a, **kw); box["at"] = time.time(); return box["val"]
        wrapper.clear = lambda: box.update(at=0.0, val=None)
        return wrapper
    return deco
