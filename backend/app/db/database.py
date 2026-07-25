from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Sourced from central config; default is the historical literal (unchanged).
DATABASE_URL = settings.DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _reconcile_columns(sync_conn) -> None:
    """Additive schema reconciliation for tables that already exist.

    ``create_all`` creates *missing tables* but never ALTERs an existing table to add
    a newly-declared column, so a DB created by an older build silently lags the ORM
    (e.g. ``checkpoint_security.runtime_id`` added in Phase 2.5 → ``no such column``).
    This walks every mapped table that already exists and ``ALTER TABLE ADD COLUMN``s
    any column the ORM declares but the DB lacks.

    Strictly ADDITIVE: only ever adds columns — never drops, renames, retypes, or
    rewrites data, so existing user data is never touched. New columns are added
    nullable (SQLite cannot add NOT-NULL without a constant default to a populated
    table; a constant ``server_default`` is honoured when present)."""
    from app.logging_config import get_logger

    insp = inspect(sync_conn)
    existing_tables = set(insp.get_table_names())
    dialect = sync_conn.dialect
    added: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brand-new table → create_all already made it with all columns
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            coltype = col.type.compile(dialect=dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
            sd = getattr(col, "server_default", None)
            if sd is not None and getattr(sd, "arg", None) is not None:
                ddl += f" DEFAULT {sd.arg}"
            try:
                sync_conn.exec_driver_sql(ddl)
                added.append(f"{table.name}.{col.name}")
            except Exception as exc:  # noqa: BLE001 - one bad column must not abort startup
                get_logger("startup").warning(
                    "schema reconcile: could not add %s.%s: %s", table.name, col.name, exc)

    if added:
        get_logger("startup").warning(
            "schema reconcile: added %d missing column(s) additively: %s",
            len(added), ", ".join(added))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Reconcile column drift on already-existing tables (additive only).
        await conn.run_sync(_reconcile_columns)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


__all__ = ["engine", "AsyncSessionLocal", "Base", "init_db", "get_db"]
