import asyncio
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.core.config import settings, pg_connect_args
from app.models import Base

config=context.config
config.set_main_option("sqlalchemy.url",settings.database_url.replace("%","%%"))
if config.config_file_name: fileConfig(config.config_file_name)
target_metadata=Base.metadata

def run_migrations_offline():
    context.configure(url=settings.database_url,target_metadata=target_metadata,literal_binds=True,dialect_opts={"paramstyle":"named"},compare_type=True)
    with context.begin_transaction(): context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection,target_metadata=target_metadata,compare_type=True)
    with context.begin_transaction(): context.run_migrations()

async def run_migrations_online():
    if settings.database_url.startswith("sqlite"):
        connectable=async_engine_from_config(config.get_section(config.config_ini_section,{}),prefix="sqlalchemy.",poolclass=pool.NullPool,connect_args=pg_connect_args(settings.database_url))
    else:
        # same failover as the app: if the main database is out of quota, migrate the next one in DATABASE_STANDBY_URLS
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.core.db import failover, _create_connection
        connectable=create_async_engine(failover.urls[0],async_creator=_create_connection,poolclass=pool.NullPool)
    async with connectable.connect() as connection: await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode(): run_migrations_offline()
else: asyncio.run(run_migrations_online())
