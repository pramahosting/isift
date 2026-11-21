"""Moving data between the main database (DATABASE_URL, number 0) and the standbys (DATABASE_STANDBY_URLS, numbers 1, 2, ...).
Nothing is copied on a timer. A copy happens only in two situations:

  1. FAILOVER  (db.py): the app moves from database A to database B. It tries to copy A -> B once. When A is out of quota it cannot be read,
     so B simply carries on with what it has (it is created empty on first use).
  2. FAIL-BACK (monitor below): while a standby is in use, the main database is tried every DB_FAILBACK_MINUTES (default 30). As soon as it
     accepts connections again, everything in the standby is merged into it, then the app switches back to it (and a short second pass
     catches anything written during the first).

A copy is a MERGE: rows are inserted or updated by primary key, nothing is deleted, so data that exists only in the older database is kept.
A row that would break another unique rule (for example the same e-mail on a different id) is skipped and counted.
Skip big tables with DB_SYNC_SKIP_TABLES=name1,name2. Turn fail-back off with DB_FAILBACK_MINUTES=0."""
import asyncio, logging, os, time
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.engine import make_url
from app.core.config import pg_connect_args
from app.core.db import failover
from app.models import Base

log = logging.getLogger("isift.dbsync")
BATCH = 500
last: dict = {"at": None, "results": []}
_lock = asyncio.Lock()

def _engine(url): return create_async_engine(url, connect_args=pg_connect_args(url), pool_size=1, max_overflow=0, pool_pre_ping=True)

def _tables():
    skip = {x.strip() for x in os.environ.get("DB_SYNC_SKIP_TABLES", "").split(",") if x.strip()}
    return [t for t in Base.metadata.sorted_tables if t.name not in skip]

def _upsert(dialect: str, table, rows):
    if dialect == "sqlite": from sqlalchemy.dialects.sqlite import insert
    else: from sqlalchemy.dialects.postgresql import insert
    stmt = insert(table); pk = [c.name for c in table.primary_key.columns]
    other = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in pk}
    return (stmt.on_conflict_do_update(index_elements=pk, set_=other) if other else stmt.on_conflict_do_nothing(index_elements=pk)), rows

async def merge(src_i: int, dst_i: int) -> dict:
    """Copy every row of database src_i into database dst_i (insert or update by primary key; nothing is deleted)."""
    urls = failover.urls
    if src_i == dst_i: raise ValueError("source and target are the same database")
    src, dst = _engine(urls[src_i]), _engine(urls[dst_i]); t0 = time.time()
    out = {"from": src_i, "to": dst_i, "host": make_url(urls[dst_i]).host, "ok": False, "rows": 0, "skipped_rows": 0}
    try:
        async with dst.begin() as c: await c.run_sync(Base.metadata.create_all)
        dialect = dst.dialect.name
        async with dst.connect() as d:
            for t in _tables():
                if not t.primary_key.columns: continue
                async with src.connect() as s:
                    res = await s.stream(select(t))
                    async for part in res.partitions(BATCH):
                        rows = [dict(r._mapping) for r in part]
                        if not rows: continue
                        stmt, _ = _upsert(dialect, t, rows)
                        try:
                            async with d.begin_nested(): await d.execute(stmt, rows)
                            out["rows"] += len(rows)
                        except IntegrityError:                          # another unique rule: go row by row, skip only the clashing ones
                            for r in rows:
                                try:
                                    async with d.begin_nested(): await d.execute(stmt, [r])
                                    out["rows"] += 1
                                except IntegrityError: out["skipped_rows"] += 1
                await d.commit()
        out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"; log.warning("copy %s -> %s failed: %s", src_i, dst_i, out["error"])
    finally:
        await src.dispose(); await dst.dispose()
    out["seconds"] = round(time.time() - t0, 1); last.update(at=time.time(), results=[*last["results"][-9:], out]); log.info("copy finished: %s", out); return out

async def on_failover(old: int, new: int):
    """Called once when the app moves from database `old` to `new`: copy old -> new if old can still be read."""
    async with _lock:
        r = await merge(old, new)
        if not r["ok"]: log.warning("Could not copy database %d into %d (the old one is probably out of quota). %d carries on with the data it has.", old, new, new)

async def _reachable(i: int) -> bool:
    e = _engine(failover.urls[i])
    try:
        async with e.connect() as c: await c.exec_driver_sql("select 1")
        return True
    except Exception: return False
    finally: await e.dispose()

async def failback_once() -> dict | None:
    """If a standby is in use and the main database works again: merge the standby into it, switch back, merge once more."""
    cur = failover.active
    if cur == 0 or _lock.locked() or not await _reachable(0): return None
    async with _lock:
        log.warning("Main database is reachable again: copying database %d into it", cur)
        a = await merge(cur, 0)
        if not a["ok"]: return a
        failover.active = 0; failover.bad_until.pop(0, None)            # new connections now go to the main database
        b = await merge(cur, 0)                                         # rows written while the first copy ran
        log.error("DATABASE FAIL-BACK: back on the main database (0). Set DATABASE_ACTIVE_INDEX=0.")
        return {"first": a, "second": b}

async def loop():
    minutes = float(os.environ.get("DB_FAILBACK_MINUTES", "30"))
    if minutes <= 0 or not failover.enabled: return
    while True:
        await asyncio.sleep(minutes * 60)
        try:
            if failover.active != 0: await failback_once()
        except asyncio.CancelledError: raise
        except Exception: log.exception("fail-back check failed")
