"""Security suite — reuses the existing Security Center engine.

Delegates to the same evaluator Continuous Security uses (``_default_evaluate``),
so there is exactly one security engine in RedForge. The suite is a thin adapter:
model → overall security score (0–100) + category breakdown. Injectable
``evaluate_fn`` in the context config keeps it offline-testable.
"""
from __future__ import annotations

from app.benchmarks.suites.base import BenchmarkSuite, SuiteContext, SuiteResult


class SecuritySuite(BenchmarkSuite):
    key = "security"
    label = "Security"
    dimension = "security"
    description = "Overall security score via the existing Security Center engine."
    real = True

    async def run(self, ctx: SuiteContext) -> SuiteResult:
        profile = ctx.config.get("security_profile", "quick")
        evaluate_fn = ctx.config.get("evaluate_fn")   # injected in tests
        if evaluate_fn is None:
            from app.continuous_security.service import _default_evaluate
            from app.db.database import AsyncSessionLocal
            result = await _default_evaluate(ctx.model, profile, AsyncSessionLocal)
        else:
            result = await evaluate_fn(ctx.model, profile)

        return SuiteResult(
            self.key,
            result.get("score"),
            {"profile": profile,
             "categories": result.get("categories", []),
             "findings": result.get("findings", []),
             "session_id": result.get("session_id")},
        )
