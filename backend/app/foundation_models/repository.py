"""Foundation Platform — repository layer (RedForge V3, Epic 1).

Dependency inversion, per the V3 Constitution (§3.6, §4): services depend on the
:class:`FoundationModelRepository` *interface*, never on SQLAlchemy. This module
owns persistence and is the only place that knows a ``FoundationModelRecord`` row
exists. It maps between the ORM row and the pure :class:`FoundationModel` domain
object in both directions, so the domain/service layers stay database-ignorant.

Swapping the persistence implementation (a different store, an in-memory fake for
tests) is a matter of providing a different ``FoundationModelRepository`` — no
service changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlalchemy import select

from app.foundation_models.domain import DiscoveredRuntimeModel, FoundationModel


class FoundationModelRepository(ABC):
    """The persistence contract the Foundation Platform services depend on.

    All methods operate on pure :class:`FoundationModel` domain objects. No
    SQLAlchemy type ever crosses this boundary."""

    @abstractmethod
    async def add(self, model: FoundationModel) -> FoundationModel: ...

    @abstractmethod
    async def get(self, model_id: str) -> Optional[FoundationModel]: ...

    @abstractmethod
    async def get_by_identity(self, identity_key: str) -> Optional[FoundationModel]: ...

    @abstractmethod
    async def list(self, *, status: Optional[str] = None, source: Optional[str] = None,
                   limit: int = 200) -> list[FoundationModel]: ...

    @abstractmethod
    async def update(self, model: FoundationModel) -> Optional[FoundationModel]: ...

    @abstractmethod
    async def delete(self, model_id: str) -> bool: ...


class SqlFoundationModelRepository(FoundationModelRepository):
    """SQLAlchemy-backed implementation. ``session_factory`` is injectable so
    tests drive it against an in-memory DB without patching globals."""

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal

    # -- ORM <-> domain mapping (the persistence boundary) --------------------

    @staticmethod
    def _to_domain(row) -> FoundationModel:
        return FoundationModel(
            id=row.id,
            hf_repo=row.hf_repo,
            revision=row.revision,
            architecture=row.architecture,
            parameter_count=row.parameter_count,
            format=FoundationModel.coerce_format(row.format),
            quantization=FoundationModel.coerce_quantization(row.quantization),
            status=FoundationModel.coerce_status(row.status),
            source=FoundationModel.coerce_source(row.source),
            license=row.license,
            cache_path=row.cache_path,
            checksum=row.checksum,
            metadata=dict(row.model_metadata or {}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _apply_to_row(row, model: FoundationModel) -> None:
        row.hf_repo = model.hf_repo
        row.revision = model.revision
        row.architecture = model.architecture
        row.parameter_count = model.parameter_count
        row.format = model.format.value
        row.quantization = model.quantization.value
        row.status = model.status.value
        row.source = model.source.value
        row.license = model.license
        row.cache_path = model.cache_path
        row.checksum = model.checksum
        row.identity_key = model.identity_key
        row.model_metadata = model.metadata or {}

    # -- operations -----------------------------------------------------------

    async def add(self, model: FoundationModel) -> FoundationModel:
        from app.db.models import FoundationModelRecord
        row = FoundationModelRecord(id=model.id)
        self._apply_to_row(row, model)
        async with self._factory()() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def get(self, model_id: str) -> Optional[FoundationModel]:
        from app.db.models import FoundationModelRecord
        async with self._factory()() as db:
            row = await db.get(FoundationModelRecord, model_id)
            return self._to_domain(row) if row else None

    async def get_by_identity(self, identity_key: str) -> Optional[FoundationModel]:
        from app.db.models import FoundationModelRecord
        async with self._factory()() as db:
            row = (await db.execute(
                select(FoundationModelRecord).where(
                    FoundationModelRecord.identity_key == identity_key).limit(1)
            )).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def list(self, *, status: Optional[str] = None, source: Optional[str] = None,
                   limit: int = 200) -> list[FoundationModel]:
        from app.db.models import FoundationModelRecord
        stmt = select(FoundationModelRecord).order_by(FoundationModelRecord.created_at.desc())
        if status is not None:
            stmt = stmt.where(FoundationModelRecord.status == status)
        if source is not None:
            stmt = stmt.where(FoundationModelRecord.source == source)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def update(self, model: FoundationModel) -> Optional[FoundationModel]:
        from app.db.models import FoundationModelRecord
        async with self._factory()() as db:
            row = await db.get(FoundationModelRecord, model.id)
            if row is None:
                return None
            self._apply_to_row(row, model)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def delete(self, model_id: str) -> bool:
        from app.db.models import FoundationModelRecord
        async with self._factory()() as db:
            row = await db.get(FoundationModelRecord, model_id)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True


# ---------------------------------------------------------------------------
# Discovered runtime models (Epic 4.5) — availability + resolution tracking.
# ---------------------------------------------------------------------------

class RuntimeModelRepository(ABC):
    """Persistence contract for discovered runtime models. Operates on pure
    :class:`DiscoveredRuntimeModel` domain objects — no SQLAlchemy crosses this
    boundary. ``upsert`` is keyed on (provider, runtime_ref) so repeated discovery
    never creates duplicate rows."""

    @abstractmethod
    async def upsert(self, model: DiscoveredRuntimeModel) -> tuple[DiscoveredRuntimeModel, bool]:
        """Insert or update by (provider, runtime_ref). Returns (record, created)."""
        ...

    @abstractmethod
    async def get(self, model_id: str) -> Optional[DiscoveredRuntimeModel]: ...

    @abstractmethod
    async def get_by_ref(self, provider: str, runtime_ref: str) -> Optional[DiscoveredRuntimeModel]: ...

    @abstractmethod
    async def list(self, *, provider: Optional[str] = None, resolution: Optional[str] = None,
                   available: Optional[bool] = None, limit: int = 500) -> list[DiscoveredRuntimeModel]: ...

    @abstractmethod
    async def update(self, model: DiscoveredRuntimeModel) -> Optional[DiscoveredRuntimeModel]: ...

    @abstractmethod
    async def delete(self, model_id: str) -> bool: ...


class SqlRuntimeModelRepository(RuntimeModelRepository):
    """SQLAlchemy-backed implementation. ``session_factory`` injectable for tests."""

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _factory(self):
        if self._session_factory is not None:
            return self._session_factory
        from app.db.database import AsyncSessionLocal
        return AsyncSessionLocal

    @staticmethod
    def _to_domain(row) -> DiscoveredRuntimeModel:
        return DiscoveredRuntimeModel(
            id=row.id, runtime_ref=row.runtime_ref, provider=row.provider or "ollama",
            resolution=DiscoveredRuntimeModel.coerce_resolution(row.resolution),
            available=bool(row.available), foundation_model_id=row.foundation_model_id,
            confidence=row.confidence, candidates=list(row.candidates or []),
            facts=dict(row.facts or {}), last_synced_at=row.last_synced_at,
            created_at=row.created_at, updated_at=row.updated_at)

    @staticmethod
    def _apply(row, m: DiscoveredRuntimeModel) -> None:
        row.runtime_ref = m.runtime_ref
        row.provider = m.provider
        row.resolution = m.resolution.value
        row.available = m.available
        row.foundation_model_id = m.foundation_model_id
        row.confidence = m.confidence
        row.candidates = m.candidates or []
        row.facts = m.facts or {}
        row.last_synced_at = m.last_synced_at

    async def upsert(self, model: DiscoveredRuntimeModel) -> tuple[DiscoveredRuntimeModel, bool]:
        from app.db.models import RuntimeModelRecord
        async with self._factory()() as db:
            existing = (await db.execute(
                select(RuntimeModelRecord).where(
                    RuntimeModelRecord.provider == model.provider,
                    RuntimeModelRecord.runtime_ref == model.runtime_ref).limit(1)
            )).scalar_one_or_none()
            if existing is None:
                row = RuntimeModelRecord(id=model.id, created_at=model.created_at)
                self._apply(row, model)
                db.add(row)
                await db.commit()
                await db.refresh(row)
                return self._to_domain(row), True
            self._apply(existing, model)
            await db.commit()
            await db.refresh(existing)
            return self._to_domain(existing), False

    async def get(self, model_id: str) -> Optional[DiscoveredRuntimeModel]:
        from app.db.models import RuntimeModelRecord
        async with self._factory()() as db:
            row = await db.get(RuntimeModelRecord, model_id)
            return self._to_domain(row) if row else None

    async def get_by_ref(self, provider: str, runtime_ref: str) -> Optional[DiscoveredRuntimeModel]:
        from app.db.models import RuntimeModelRecord
        async with self._factory()() as db:
            row = (await db.execute(
                select(RuntimeModelRecord).where(
                    RuntimeModelRecord.provider == provider,
                    RuntimeModelRecord.runtime_ref == runtime_ref).limit(1)
            )).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def list(self, *, provider=None, resolution=None, available=None,
                   limit: int = 500) -> list[DiscoveredRuntimeModel]:
        from app.db.models import RuntimeModelRecord
        stmt = select(RuntimeModelRecord).order_by(RuntimeModelRecord.runtime_ref)
        if provider is not None:
            stmt = stmt.where(RuntimeModelRecord.provider == provider)
        if resolution is not None:
            stmt = stmt.where(RuntimeModelRecord.resolution == resolution)
        if available is not None:
            stmt = stmt.where(RuntimeModelRecord.available == available)
        async with self._factory()() as db:
            rows = (await db.execute(stmt.limit(limit))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def update(self, model: DiscoveredRuntimeModel) -> Optional[DiscoveredRuntimeModel]:
        from app.db.models import RuntimeModelRecord
        async with self._factory()() as db:
            row = await db.get(RuntimeModelRecord, model.id)
            if row is None:
                return None
            self._apply(row, model)
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def delete(self, model_id: str) -> bool:
        from app.db.models import RuntimeModelRecord
        async with self._factory()() as db:
            row = await db.get(RuntimeModelRecord, model_id)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True
