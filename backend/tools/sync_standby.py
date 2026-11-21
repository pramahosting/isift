"""Copy the active database into every standby so a failover has current data.

  python tools/sync_standby.py            # copy DATABASE_URL (or the active one) -> each standby
  python tools/sync_standby.py --to 2     # only address number 2 (0 = DATABASE_URL, 1 = first standby, ...)

Run it on a schedule (Northflank cron job, once a day is usually enough), with the same DATABASE_URL, DATABASE_STANDBY_URLS and
DATABASE_ACTIVE_INDEX variables as the app. Full copy, table by table, in dependency order; the standby is replaced.
It reads the source, so it uses a little of the source's quota. Never run it with the source and target the same database.
"""
import argparse, asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import select, insert, delete, text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings, pg_connect_args
from app.core.db import failover
from app.models import Base

BATCH = 500

def eng(url): return create_async_engine(url, connect_args=pg_connect_args(url), pool_size=2, max_overflow=0)

async def copy(src_url: str, dst_url: str):
    src, dst = eng(src_url), eng(dst_url)
    try:
        async with dst.begin() as c: await c.run_sync(Base.metadata.create_all)
        tables = list(Base.metadata.sorted_tables)
        async with dst.begin() as d:
            for t in reversed(tables): await d.execute(delete(t))
            for t in tables:
                n = 0
                async with src.connect() as s:
                    res = await s.stream(select(t))
                    async for part in res.partitions(BATCH):
                        rows = [dict(r._mapping) for r in part]
                        if rows: await d.execute(insert(t), rows); n += len(rows)
                print(f"  {t.name}: {n} rows")
    finally:
        await src.dispose(); await dst.dispose()

async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--to", type=int, default=0, help="address number to refresh (default: every one except the active)")
    a = ap.parse_args(); urls = failover.urls; active = failover.active
    if len(urls) < 2: sys.exit("No standby addresses: set DATABASE_STANDBY_URLS.")
    targets = [a.to] if a.to else [i for i in range(len(urls)) if i != active]
    if any(i == active or not 0 <= i < len(urls) for i in targets): sys.exit('Pick a standby that is not the active database.')
    for i in targets:
        print(f"Copying database {active} -> {i}"); await copy(urls[active], urls[i]); print("  done")

if __name__ == "__main__": asyncio.run(main())
