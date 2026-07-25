"""Foundation Model Platform (RedForge V3, Epic 1).

The training-domain model-identity bounded context (Constitution §3.6, §5.4,
§10.1). A Foundation Model is what a training provider LOADS — a Hugging Face
checkpoint — as distinct from a Runtime Model, which is what the Runtime Manager
SERVES. The two are distinct identities related only by derivation; this context
never merges them.

Additive and non-breaking: nothing existing depends on this package, and it
modifies no existing subsystem. It reads the Runtime Manager (allowed — Runtime
is a leaf) but the Runtime Manager remains entirely unaware of it.

Layering (V3): domain (pure) → repository (persistence) → service (logic) →
resolution (isolated). Services depend on repository *interfaces*, never on
SQLAlchemy.
"""
from app.foundation_models.discovery import (
    DiscoveryService,
    discovery_service,
    register_discovery_handlers,
)
from app.foundation_models.domain import (
    DiscoveredRuntimeModel,
    FoundationModel,
    FoundationModelStatus,
    ModelSource,
    Quantization,
    ResolutionCandidate,
    ResolutionResult,
    RuntimeModelFacts,
    RuntimeResolutionStatus,
    WeightFormat,
)
from app.foundation_models.repository import (
    FoundationModelRepository,
    RuntimeModelRepository,
    SqlFoundationModelRepository,
    SqlRuntimeModelRepository,
)
from app.foundation_models.resolution import (
    GenericResolver,
    ModelResolutionService,
    ModelResolver,
    OllamaResolver,
)
from app.foundation_models.service import FoundationModelService, foundation_model_service

__all__ = [
    # domain
    "FoundationModel", "FoundationModelStatus", "ModelSource", "Quantization",
    "WeightFormat", "ResolutionCandidate", "ResolutionResult", "RuntimeModelFacts",
    "DiscoveredRuntimeModel", "RuntimeResolutionStatus",
    # repository
    "FoundationModelRepository", "SqlFoundationModelRepository",
    "RuntimeModelRepository", "SqlRuntimeModelRepository",
    # resolution
    "ModelResolutionService", "ModelResolver", "OllamaResolver", "GenericResolver",
    # discovery (Epic 4.5)
    "DiscoveryService", "discovery_service", "register_discovery_handlers",
    # service + singleton
    "FoundationModelService", "foundation_model_service",
]
