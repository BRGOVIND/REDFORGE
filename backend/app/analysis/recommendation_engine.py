"""Attach concrete, category-specific recommendations to findings.

Recommendations are deterministic lookups keyed by category, with severity-aware
prefixing so higher-risk findings read more urgently. Kept separate from finding
generation so the "what" (finding) and the "so what" (recommendation) evolve
independently.
"""
from __future__ import annotations

from app.analysis.finding_generator import Finding

_RECOMMENDATIONS = {
    "PROMPT_INJECTION": (
        "Strengthen the system prompt hierarchy and add input validation that "
        "isolates user content from instructions (e.g. delimiters, role tags, and "
        "an explicit instruction-precedence policy)."
    ),
    "JAILBREAK": (
        "Harden refusal behavior against persona and hypothetical framings; add "
        "adversarial jailbreak examples to safety tuning and enforce a consistent "
        "refusal style."
    ),
    "CONTEXT_MANIPULATION": (
        "Do not trust in-context claims of prior agreements or authority; validate "
        "conversation state server-side and ignore injected 'previous instructions'."
    ),
    "DATA_LEAKAGE": (
        "Never expose the system prompt, hidden context, or training data. Add "
        "output filters for secret-like content and refuse meta-requests about "
        "internal instructions."
    ),
    "prompt_injection": None,   # aliases resolved below
    "jailbreak": None,
    "data_leakage": None,
    "hallucination": (
        "Ground responses in provided context, express uncertainty, and avoid "
        "fabricating facts; consider retrieval augmentation for factual queries."
    ),
    "toxicity": (
        "Reinforce content-safety filters and refusal behavior for harmful or "
        "hateful requests."
    ),
}

# Map lowercase benchmark aliases to their uppercase attack-library text.
_ALIASES = {
    "prompt_injection": "PROMPT_INJECTION",
    "jailbreak": "JAILBREAK",
    "data_leakage": "DATA_LEAKAGE",
}

_DEFAULT = (
    "Review the failing prompts and reinforce the model's safety guidelines and "
    "input handling for this category."
)

_URGENCY = {
    "critical": "Critical priority: ",
    "high": "High priority: ",
    "medium": "",
    "low": "",
    "none": "",
}


def recommendation_for(category: str, severity: str = "medium") -> str:
    text = _RECOMMENDATIONS.get(category)
    if text is None:
        text = _RECOMMENDATIONS.get(_ALIASES.get(category, ""), _DEFAULT)
    return f"{_URGENCY.get(severity, '')}{text}"


def attach_recommendations(findings: list[Finding]) -> list[Finding]:
    for finding in findings:
        finding.recommendation = recommendation_for(finding.category, finding.severity)
    return findings
