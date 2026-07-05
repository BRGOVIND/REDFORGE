"""Turn an :class:`AnalysisResult` into actionable findings.

Every finding carries a severity, supporting evidence, and (after the
recommendation engine runs) a recommendation — the three things the spec
requires. Generation is deterministic and ordered worst-first.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.analysis.security_analyzer import AnalysisResult, CategoryScore

# Human-friendly titles per category (covers attack-library and benchmark names).
_CATEGORY_TITLES = {
    "PROMPT_INJECTION": "Prompt Injection",
    "JAILBREAK": "Jailbreak",
    "CONTEXT_MANIPULATION": "Context Manipulation",
    "DATA_LEAKAGE": "Data Leakage",
    "prompt_injection": "Prompt Injection",
    "jailbreak": "Jailbreak",
    "data_leakage": "Data Leakage",
    "hallucination": "Hallucination",
    "toxicity": "Toxicity",
}

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}


class Evidence(BaseModel):
    attack_name: str
    verdict: str
    excerpt: str


class Finding(BaseModel):
    id: str
    category: str
    title: str
    severity: str
    risk_level: str
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    recommendation: str = ""


def _title(category: str) -> str:
    return _CATEGORY_TITLES.get(category, category.replace("_", " ").title())


def _severity_from_category(cs: CategoryScore) -> str:
    # Finding severity tracks the category risk level directly.
    return cs.risk_level if cs.risk_level != "none" else "low"


def generate_findings(analysis: AnalysisResult) -> list[Finding]:
    findings: list[Finding] = []

    for cs in analysis.category_scores:
        if cs.failed == 0:
            continue

        evidence = [
            Evidence(attack_name=v.attack_name, verdict=v.verdict, excerpt=v.excerpt)
            for v in analysis.top_vulnerabilities
            if v.category == cs.category
        ][:3]

        severity = _severity_from_category(cs)
        reason = (
            f"{cs.failed} of {cs.total} {_title(cs.category)} attacks succeeded "
            f"(weighted fail rate {cs.fail_rate:.0%}). "
            f"Multiple {_title(cs.category).lower()} bypasses were observed."
        )
        findings.append(Finding(
            id=f"finding-{cs.category.lower()}",
            category=cs.category,
            title=f"{_title(cs.category)} vulnerabilities",
            severity=severity,
            risk_level=cs.risk_level,
            reason=reason,
            evidence=evidence,
        ))

    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 5), f.category))
    return findings
