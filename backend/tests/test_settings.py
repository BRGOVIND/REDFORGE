"""Settings system tests — schema/grouping, persistence, validation, secrets, reset."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

import app.db.models  # register tables
from app.db.database import Base
from app.settings.service import SettingsService, SettingsValidationError
from app.settings import schema


@pytest_asyncio.fixture
async def svc():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool,
                                 connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield SettingsService(session_factory=factory)
    await engine.dispose()


@pytest.mark.asyncio
async def test_grouped_covers_every_category(svc):
    g = await svc.grouped()
    keys = {c["key"] for c in g["categories"]}
    for cat, *_ in schema.CATEGORIES:
        assert cat in keys, f"missing category {cat}"
    # each setting exposes its effective value + schema
    one = g["categories"][0]["settings"][0]
    assert {"key", "type", "value", "default", "is_overridden"} <= set(one)


@pytest.mark.asyncio
async def test_effective_defaults_then_override(svc):
    eff = await svc.effective()
    assert eff["downloads.concurrent"] == 2               # default
    await svc.set_many({"downloads.concurrent": 4})
    eff2 = await svc.effective()
    assert eff2["downloads.concurrent"] == 4              # persisted override


@pytest.mark.asyncio
async def test_int_is_clamped_to_range(svc):
    await svc.set_many({"downloads.concurrent": 999})
    assert await svc.get("downloads.concurrent") == 6     # max is 6


@pytest.mark.asyncio
async def test_enum_validation_reports_field(svc):
    with pytest.raises(SettingsValidationError) as ei:
        await svc.set_many({"appearance.theme": "neon"})
    assert "appearance.theme" in ei.value.errors


@pytest.mark.asyncio
async def test_unknown_key_is_a_field_error(svc):
    with pytest.raises(SettingsValidationError) as ei:
        await svc.set_many({"nope.nope": 1})
    assert "nope.nope" in ei.value.errors


@pytest.mark.asyncio
async def test_secret_is_masked_but_stored(svc):
    await svc.set_many({"networking.hf_token": "hf_secret_abc"})
    assert await svc.get("networking.hf_token") == "********"          # masked read
    assert await svc.get("networking.hf_token", reveal_secrets=True) == "hf_secret_abc"
    # sending the mask back unchanged does NOT overwrite the stored secret
    await svc.set_many({"networking.hf_token": "********"})
    assert await svc.get("networking.hf_token", reveal_secrets=True) == "hf_secret_abc"


@pytest.mark.asyncio
async def test_reset_one_and_all(svc):
    await svc.set_many({"downloads.concurrent": 5, "appearance.density": "compact"})
    await svc.reset("downloads.concurrent")
    assert await svc.get("downloads.concurrent") == 2                  # back to default
    assert await svc.get("appearance.density") == "compact"           # untouched
    await svc.reset()
    assert await svc.get("appearance.density") == "comfortable"       # all reset
