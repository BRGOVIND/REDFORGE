"""Performance suite — the one fully-local, real-measurement suite.

Issues a small set of generations through the injectable ``generate_fn`` (the
Runtime Manager in production), timing first-token latency, average latency, and
tokens/sec, and snapshots hardware (CPU / GPU / VRAM / RAM / context window).
The primary 0–100 score rewards throughput and penalizes latency so faster
runtimes rank higher on the leaderboard.
"""
from __future__ import annotations

import time

from app.benchmarks.suites.base import BenchmarkSuite, SuiteContext, SuiteResult

_PROMPTS = [
    "Explain what a hash map is in two sentences.",
    "List three prime numbers greater than 50.",
    "Write a haiku about local software.",
]


class PerformanceSuite(BenchmarkSuite):
    key = "performance"
    label = "Performance"
    dimension = "performance"
    description = "First-token & average latency, tokens/sec, hardware utilisation."
    real = True

    async def run(self, ctx: SuiteContext) -> SuiteResult:
        n = int(ctx.config.get("samples", len(_PROMPTS)))
        prompts = (_PROMPTS * ((n // len(_PROMPTS)) + 1))[:n]
        options = {"max_tokens": ctx.config.get("max_tokens", 128),
                   "temperature": ctx.config.get("temperature", 0.0)}

        latencies_ms: list[float] = []
        first_token_ms: float | None = None
        total_tokens = 0
        errors = 0
        for i, prompt in enumerate(prompts):
            start = time.monotonic()
            try:
                text = await ctx.generate_fn(ctx.model, prompt, options=options)
            except TypeError:
                text = await ctx.generate_fn(ctx.model, prompt)   # 2-arg fakes
            except Exception:  # noqa: BLE001 - a failed generation counts, never crashes the suite
                errors += 1
                continue
            elapsed_ms = (time.monotonic() - start) * 1000.0
            latencies_ms.append(elapsed_ms)
            if i == 0:
                first_token_ms = elapsed_ms
            total_tokens += max(1, len((text or "").split()))

        ok = len(latencies_ms)
        avg_latency = round(sum(latencies_ms) / ok, 1) if ok else None
        # Floor elapsed so throughput is always a number (near-instant fakes / very
        # fast runtimes would otherwise divide by zero); real providers are >0.
        elapsed_s = max(sum(latencies_ms) / 1000.0, 1e-6)
        tokens_per_sec = round(total_tokens / elapsed_s, 2) if ok else None

        gpu = (ctx.resources or {}).get("gpu") or {}
        metrics = {
            "first_token_latency_ms": round(first_token_ms, 1) if first_token_ms is not None else None,
            "avg_latency_ms": avg_latency,
            "tokens_per_sec": tokens_per_sec,
            "samples": ok,
            "errors": errors,
            "context_window": ctx.config.get("context_window"),
            "cpu_count": (ctx.resources or {}).get("cpu_count"),
            "ram_total_mb": (ctx.resources or {}).get("ram_total_mb"),
            "ram_available_mb": (ctx.resources or {}).get("ram_available_mb"),
            "gpu": gpu.get("name"),
            "gpu_backend": gpu.get("backend"),
            "vram_total_mb": gpu.get("total_mb"),
            "vram_free_mb": gpu.get("free_mb"),
        }

        # Score: throughput-weighted, latency-penalized, clamped to 0–100.
        if not ok:
            return SuiteResult(self.key, None, metrics, note="no successful generations")
        tps = tokens_per_sec or 0.0
        lat = avg_latency or 1_000.0
        score = max(0.0, min(100.0, tps * 2.0 + max(0.0, 100.0 - lat / 30.0)))
        return SuiteResult(self.key, round(score, 2), metrics)
