import asyncio
import os
import pathlib
import tempfile

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Isolate the whole test session onto a FRESH, EMPTY database file.
#
# This must happen before any `app.*` import, so the app engine is built against
# the test database rather than a developer's stateful ``redforge.db``. It mirrors
# a clean CI checkout: every run starts from an empty database.
#
# Set before importing app.config (which reads REDFORGE_DATABASE_URL at import).
# ---------------------------------------------------------------------------
_TEST_DB = pathlib.Path(tempfile.gettempdir()) / "redforge_pytest.db"
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ["REDFORGE_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker  # noqa: E402

from app.db.database import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _initialize_app_schema():
    """Create the application schema before any test touches the app engine.

    In production the schema is created by ``init_db()`` in the FastAPI lifespan.
    Tests drive the app through ``ASGITransport``, which does NOT run lifespan, so
    without this the app database would be missing every table on a clean
    checkout (the CI failure: ``no such table: evaluation_sessions``).

    Importing ``app.db.models`` registers every ORM table on ``Base.metadata``;
    ``create_all`` then builds them — exactly what ``init_db`` does. The engine is
    disposed afterwards so function-scoped test event loops start with a clean
    connection pool rather than one bound to this fixture's loop.
    """
    import app.db.models  # noqa: F401 - registers all tables on Base.metadata
    from app.db.database import engine

    async def _prepare() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_prepare())
    yield


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def db_session():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
