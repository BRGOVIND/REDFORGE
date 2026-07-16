"""Release-hardening (v2.0): upload size cap, orphaned-job recovery, and the
single-process guard. All offline."""
from __future__ import annotations

import io

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.database import Base


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    fac = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = fac()
    yield session
    await session.close()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    from app.main import app
    from app.db.database import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# -- upload cap -------------------------------------------------------------

@pytest.mark.asyncio
async def test_oversized_upload_rejected_413(client, monkeypatch):
    # Patch the exact settings object the handler captured at import (robust to
    # other tests reloading app.config).
    import app.api.datasets as ds_mod
    monkeypatch.setattr(ds_mod.settings, "MAX_UPLOAD_BYTES", 1024)  # 1 KB cap for the test
    big = b"text\n" + b"x" * 5000
    files = {"file": ("big.txt", io.BytesIO(big), "text/plain")}
    r = await client.post("/api/datasets/import", files=files, data={"name": "Big"})
    assert r.status_code == 413
    assert "too large" in r.json()["error"]["message"].lower()


@pytest.mark.asyncio
async def test_empty_upload_rejected(client):
    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    r = await client.post("/api/datasets/import", files=files, data={"name": "Empty"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_normal_upload_still_works(client):
    files = {"file": ("ok.csv", io.BytesIO(b"text\nhi\nbye\n"), "text/csv")}
    r = await client.post("/api/datasets/import", files=files, data={"name": "OK"})
    assert r.status_code == 201 and r.json()["record_count"] == 2


# -- orphaned-job recovery --------------------------------------------------

@pytest.mark.asyncio
async def test_recover_orphaned_jobs_marks_interrupted(db_session, monkeypatch):
    import app.main as main
    from app.db.models import EvaluationSession, TrainingRun
    from uuid import uuid4

    db_session.add(TrainingRun(id=str(uuid4()), name="t", base_model="m", status="running"))
    db_session.add(TrainingRun(id=str(uuid4()), name="t2", base_model="m", status="completed"))
    db_session.add(EvaluationSession(id=str(uuid4()), session_type="batch", status="running",
                                     total_tasks=1, completed_tasks=0))
    await db_session.commit()

    # Point the recovery's session factory at the in-memory test session.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_factory():
        yield db_session

    monkeypatch.setattr(main, "AsyncSessionLocal", fake_factory)
    await main._recover_orphaned_jobs()

    from sqlalchemy import select
    runs = (await db_session.execute(select(TrainingRun))).scalars().all()
    statuses = sorted(r.status for r in runs)
    assert statuses == ["completed", "interrupted"]  # running → interrupted; completed untouched
    ev = (await db_session.execute(select(EvaluationSession))).scalars().all()
    assert ev[0].status == "interrupted"


# -- single-process guard ---------------------------------------------------

def test_single_process_guard(monkeypatch):
    from app.main import _enforce_single_process
    monkeypatch.delenv("REDFORGE_ALLOW_MULTIWORKER", raising=False)
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeError):
        _enforce_single_process()
    monkeypatch.setenv("REDFORGE_ALLOW_MULTIWORKER", "1")
    _enforce_single_process()  # override → no raise
    monkeypatch.delenv("REDFORGE_ALLOW_MULTIWORKER")
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    _enforce_single_process()  # single worker → no raise
