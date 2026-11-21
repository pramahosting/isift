"""Merge one database into another by hand (nothing is deleted in the target).

  python tools/sync_standby.py --from 1 --to 0      # standby 1 -> main database
  python tools/sync_standby.py --from 0 --to 1

Numbers: 0 = DATABASE_URL, 1 = first DATABASE_STANDBY_URLS address, 2 = second, ... Same environment variables as the app.
The app already does this by itself on a failover and on the way back (see app/services/dbsync.py); this is for doing it manually.
"""
import argparse, asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.db import failover
from app.services import dbsync

async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--from", dest="src", type=int, required=True); ap.add_argument("--to", type=int, required=True)
    a = ap.parse_args(); n = len(failover.urls)
    if not (0 <= a.src < n and 0 <= a.to < n) or a.src == a.to: sys.exit("Pick two different database numbers between 0 and %d." % (n - 1))
    print(f"Merging database {a.src} -> {a.to} ..."); r = await dbsync.merge(a.src, a.to); print(" ", r); sys.exit(0 if r.get("ok") else 1)

if __name__ == "__main__": asyncio.run(main())
