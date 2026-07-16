"""Reasoning suite — adapter architecture (MMLU / GSM8K / BBH / HumanEval / custom).

Each academic benchmark is a pluggable *adapter*. Adapters that have no dataset
attached (the default offline state) report ``available=False``; the suite then
falls back to a deterministic behavioural probe and marks the result
``simulated=True``. Attaching a real dataset later is a one-adapter change with no
caller impact — the extension point the spec asks for ("Architecture only").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.benchmarks.suites.base import (
    BenchmarkSuite,
    SuiteContext,
    SuiteResult,
    _stable_probe_score,
)


@dataclass
class ReasoningAdapter:
    key: str
    label: str
    available: bool = False          # True once a dataset/loader is attached
    # loader() -> list[{"prompt", "answer"}] — plugged in when a dataset exists.
    loader: Optional[Callable[[], list[dict]]] = None


# Pluggable adapter registry. All unavailable offline (no datasets shipped) — the
# architecture is in place; flip ``available`` + set ``loader`` to enable a real run.
REASONING_ADAPTERS: dict[str, ReasoningAdapter] = {
    "mmlu": ReasoningAdapter("mmlu", "MMLU"),
    "gsm8k": ReasoningAdapter("gsm8k", "GSM8K"),
    "bbh": ReasoningAdapter("bbh", "BIG-Bench Hard"),
    "humaneval": ReasoningAdapter("humaneval", "HumanEval"),
    "custom": ReasoningAdapter("custom", "Custom dataset"),
}

_PROBE = "A farmer has 17 sheep. All but 9 run away. How many are left? Answer with a number."


class ReasoningSuite(BenchmarkSuite):
    key = "reasoning"
    label = "Reasoning"
    dimension = "reasoning"
    description = "MMLU / GSM8K / BBH / HumanEval adapters (extensible)."
    real = False   # architecture until a dataset adapter is attached

    async def run(self, ctx: SuiteContext) -> SuiteResult:
        adapter_key = ctx.config.get("adapter", "mmlu")
        adapter = REASONING_ADAPTERS.get(adapter_key)
        available = [a.key for a in REASONING_ADAPTERS.values() if a.available]

        # Real path (future): adapter.loader() + score against ground truth.
        if adapter and adapter.available and adapter.loader:  # pragma: no cover
            items = adapter.loader()
            correct = 0
            for it in items:
                resp = await _safe_generate(ctx, it["prompt"])
                if str(it.get("answer", "")).strip().lower() in (resp or "").lower():
                    correct += 1
            score = round(100.0 * correct / max(1, len(items)), 2)
            return SuiteResult(self.key, score, {"adapter": adapter_key, "items": len(items)})

        # Architecture fallback: light probe, deterministic, clearly simulated.
        resp = await _safe_generate(ctx, _PROBE)
        score = _stable_probe_score(ctx.model, self.dimension, resp)
        return SuiteResult(
            self.key, score,
            {"adapter": adapter_key, "adapters_available": available,
             "probe_correct": "9" in (resp or "")},
            simulated=True,
            note="No reasoning dataset attached — architecture probe only.",
        )


async def _safe_generate(ctx: SuiteContext, prompt: str) -> str:
    try:
        return await ctx.generate_fn(ctx.model, prompt, options={"max_tokens": 32, "temperature": 0.0})
    except TypeError:
        try:
            return await ctx.generate_fn(ctx.model, prompt)
        except Exception:  # noqa: BLE001
            return ""
    except Exception:  # noqa: BLE001
        return ""
