import asyncio, logging, os, time
from sqlalchemy import event, exc
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from app.core.config import settings, pg_connect_args, normalise_database_url

log = logging.getLogger("isift.db")
_sqlite = settings.database_url.startswith("sqlite")

class Failover:
    """Several PostgreSQL addresses in priority order. New connections use the active one; when it is out of quota or unreachable the next
    one is tried and becomes the active one. It never switches back by itself (the copies may differ): restart with DATABASE_ACTIVE_INDEX to move."""
    def __init__(self, urls: list[str], start: int = 0):
        self.urls = urls; self.active = start if 0 <= start < len(urls) else 0; self.bad_until: dict[int, float] = {}
    @property
    def enabled(self) -> bool: return len(self.urls) > 1
    def status(self) -> dict:
        return {"active": self.active, "count": len(self.urls), "hosts": [make_url(u).host for u in self.urls]}

def _all_urls() -> list[str]:
    extra = [normalise_database_url(u) for u in (settings.database_standby_urls or "").replace(",", "\n").split("\n") if u.strip()]
    return [settings.database_url] + extra

failover = Failover([settings.database_url] if _sqlite else _all_urls(), settings.database_active_index)

def _failover_errors():
    import asyncpg
    # quota / resource errors (class 53, includes "exceeded the quota" and "too many connections"), cannot-connect-now, dropped or unreachable
    return (asyncpg.exceptions.InsufficientResourcesError, asyncpg.exceptions.CannotConnectNowError, asyncpg.exceptions.PostgresConnectionError,
            asyncpg.exceptions.InvalidAuthorizationSpecificationError, ConnectionError, OSError, asyncio.TimeoutError)

if _sqlite:
    # SQLite: many users read while one writes (WAL), and writers wait for each other instead of failing with "database is locked".
    engine = create_async_engine(settings.database_url, connect_args={"timeout": 30})
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL"); cur.execute("PRAGMA foreign_keys=ON"); cur.close()
else:
    import asyncpg

    class _Tagged(asyncpg.Connection):
        """A connection that remembers which database address it belongs to."""
        isift_idx = -1

    def _connect_kwargs(url: str) -> dict:
        _args, kw = engine.dialect.create_connect_args(make_url(url))
        kw = dict(kw); kw.pop("prepared_statement_cache_size", None)
        kw.update(pg_connect_args(url)); kw.setdefault("timeout", float(os.environ.get("DB_CONNECT_TIMEOUT", "6")))
        return kw

    async def _create_connection():
        n = len(failover.urls); start = failover.active; last = None; errs = _failover_errors()
        for step in range(n):
            i = (start + step) % n
            if step and failover.bad_until.get(i, 0) > time.time(): continue
            try:
                conn = await asyncpg.connect(connection_class=_Tagged, **_connect_kwargs(failover.urls[i]))
            except errs as e:
                last = e; failover.bad_until[i] = time.time() + 600
                log.warning("Database %d (%s) not usable: %s", i, make_url(failover.urls[i]).host, str(e)[:160]); continue
            conn.isift_idx = i
            if i != failover.active:
                log.error("DATABASE FAILOVER: now using database %d (%s). Update DATABASE_URL / DATABASE_ACTIVE_INDEX so a restart keeps it.", i, make_url(failover.urls[i]).host)
                prev = failover.active; failover.active = i
                try:
                    from app.services import dbsync
                    asyncio.get_running_loop().create_task(dbsync.on_failover(prev, i))     # one-off: copy the old database into the new one if it can still be read
                except Exception: log.exception("could not start the failover copy")
            return conn
        raise last

    engine = create_async_engine(failover.urls[0], async_creator=_create_connection, pool_pre_ping=False, pool_recycle=int(os.environ.get("DB_POOL_RECYCLE", "240")), pool_timeout=10, pool_size=settings.db_pool_size, max_overflow=settings.db_pool_size * 2)

    @event.listens_for(engine.sync_engine, "checkout")
    def _drop_other_database(dbapi_conn, _record, _proxy):
        """After a failover, pooled connections to the old database are thrown away instead of being reused (no writes to two databases)."""
        raw = getattr(dbapi_conn, "_connection", None)
        if getattr(raw, "isift_idx", failover.active) != failover.active: raise exc.DisconnectionError("database switched")
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def get_db():
    async with SessionLocal() as session:
        yield session
