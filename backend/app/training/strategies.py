"""Training strategies (RedForge V3, Epic 3).

A **strategy** is *what algorithm* a run applies, separated from *who executes* it
(provider) and *how* it runs (execution) — Constitution §10.2. Each strategy declares
its required dataset shape and which providers can run it. New alignment methods
(DPO/ORPO/PPO/RLHF) are new registered strategy specs — **no redesign** of the engine,
providers, or execution (the extensibility guarantee).

Providers are the existing ``app/training/providers`` implementations, reused as-is;
strategy↔provider compatibility is declared here, in the V3 layer, so the existing
provider classes are never modified.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StrategyDef:
    key: str
    label: str
    adapter_based: bool                  # produces a LoRA adapter (vs full fine-tune)
    dataset_shape: str                   # "instruction" | "text" | "preference" | "prompt+reward"
    providers: tuple[str, ...]           # provider keys that can run this strategy
    implemented: bool = True             # False → architecture present, not yet runnable

    def to_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "adapter_based": self.adapter_based,
                "dataset_shape": self.dataset_shape, "providers": list(self.providers),
                "implemented": self.implemented}


_STRATEGIES: dict[str, StrategyDef] = {}


def register_strategy(defn: StrategyDef) -> None:
    _STRATEGIES[defn.key] = defn


def _seed() -> None:
    for defn in (
        # Implemented in Epic 3.
        StrategyDef("lora", "LoRA", adapter_based=True, dataset_shape="instruction",
                    providers=("unsloth", "transformers", "simulation", "mock")),
        StrategyDef("qlora", "QLoRA", adapter_based=True, dataset_shape="instruction",
                    providers=("unsloth", "simulation", "mock")),
        StrategyDef("sft", "Supervised Fine-Tuning", adapter_based=False, dataset_shape="instruction",
                    providers=("unsloth", "transformers", "simulation", "mock")),
        # Architecture present, not yet runnable (future epics) — honestly flagged.
        StrategyDef("dpo", "Direct Preference Optimization", adapter_based=True,
                    dataset_shape="preference", providers=("simulation", "mock"), implemented=False),
        StrategyDef("orpo", "ORPO", adapter_based=True, dataset_shape="preference",
                    providers=("simulation", "mock"), implemented=False),
        StrategyDef("ppo", "PPO", adapter_based=True, dataset_shape="prompt+reward",
                    providers=("simulation", "mock"), implemented=False),
        StrategyDef("rlhf", "RLHF", adapter_based=True, dataset_shape="prompt+reward",
                    providers=("simulation", "mock"), implemented=False),
    ):
        register_strategy(defn)


_seed()


def get_strategy(key: str) -> StrategyDef:
    known = _STRATEGIES.get(key)
    if known is not None:
        return known
    return StrategyDef(key=key, label=key.upper(), adapter_based=True,
                       dataset_shape="instruction", providers=("simulation", "mock"),
                       implemented=False)


def list_strategies() -> list[dict]:
    return [d.to_dict() for d in _STRATEGIES.values()]


def compatible_providers(strategy_key: str) -> list[str]:
    return list(get_strategy(strategy_key).providers)


def resolve_provider(strategy_key: str, requested: str | None) -> str:
    """Pick a provider for a strategy: honor an explicit, compatible request; else
    the first compatible provider that is available. Falls back to 'simulation'
    (the guaranteed-available dev provider) so the pipeline always runs."""
    compatible = compatible_providers(strategy_key)
    if requested and requested in compatible:
        return requested
    from app.training import manager
    for name in compatible:
        # 'mock' aliases the simulation provider (always available); skip the alias
        # for availability probing and use the real registered provider name.
        probe = "simulation" if name == "mock" else name
        try:
            factory = manager._PROVIDERS.get(probe)
            if factory is None:
                continue
            ok, _ = factory().is_available()
            if ok:
                return probe
        except Exception:  # noqa: BLE001
            continue
    return "simulation"
