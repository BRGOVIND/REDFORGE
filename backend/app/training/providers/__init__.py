"""Training providers. Each implements :class:`TrainingProvider`.

``BUILTIN_PROVIDERS`` is the single registration point. To add a backend, create
the class and add one line here (or call ``manager.register_provider`` at
runtime). No engine code changes — the Training Manager selects by name.
"""
from __future__ import annotations

from app.training.providers.base import TrainingConfig, TrainingProvider, ProgressEvent
from app.training.providers.simulation import SimulationProvider
from app.training.providers.unsloth import UnslothProvider

BUILTIN_PROVIDERS: dict[str, type[TrainingProvider]] = {
    SimulationProvider.name: SimulationProvider,
    UnslothProvider.name: UnslothProvider,
}

__all__ = [
    "BUILTIN_PROVIDERS",
    "TrainingProvider",
    "TrainingConfig",
    "ProgressEvent",
    "SimulationProvider",
    "UnslothProvider",
]
