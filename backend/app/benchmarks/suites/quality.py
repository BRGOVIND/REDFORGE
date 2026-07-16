"""Architecture suites for the remaining quality dimensions.

Instruction Following, Hallucination, and Context all need labeled datasets to
score for real. Offline they run a single behavioural probe and return a
deterministic ``simulated=True`` score — same honest-fallback contract as the
Reasoning adapters. Each is independently pluggable; attaching a scorer later
turns ``real`` on without touching the queue, API, or UI.
"""
from __future__ import annotations

from app.benchmarks.suites.base import (
    BenchmarkSuite,
    SuiteContext,
    SuiteResult,
    _stable_probe_score,
)


async def _probe(ctx: SuiteContext, prompt: str) -> str:
    try:
        return await ctx.generate_fn(ctx.model, prompt, options={"max_tokens": 48, "temperature": 0.0})
    except TypeError:
        try:
            return await ctx.generate_fn(ctx.model, prompt)
        except Exception:  # noqa: BLE001
            return ""
    except Exception:  # noqa: BLE001
        return ""


class _ArchitectureSuite(BenchmarkSuite):
    real = False
    _prompt = "Respond with the single word: OK"

    async def run(self, ctx: SuiteContext) -> SuiteResult:
        resp = await _probe(ctx, self._prompt)
        score = _stable_probe_score(ctx.model, self.dimension, resp)
        return SuiteResult(
            self.key, score,
            {"probe_response_chars": len((resp or ""))},
            simulated=True,
            note=f"No {self.dimension} dataset attached — architecture probe only.",
        )


class InstructionFollowingSuite(_ArchitectureSuite):
    key = "instruction_following"
    label = "Instruction Following"
    dimension = "instruction_following"
    description = "Adherence to explicit format/constraint instructions (extensible)."
    _prompt = "Reply with exactly three comma-separated colors and nothing else."


class HallucinationSuite(_ArchitectureSuite):
    key = "hallucination"
    label = "Hallucination"
    dimension = "hallucination"
    description = "Rate of confidently-wrong / fabricated answers (extensible)."
    _prompt = "Who won the 2099 FIFA World Cup? If unknown, say you don't know."


class ContextSuite(_ArchitectureSuite):
    key = "context"
    label = "Context"
    dimension = "context"
    description = "Long-context recall and use of provided information (extensible)."
    _prompt = "The passphrase is 'amber-lynx-42'. Repeat the passphrase exactly."
