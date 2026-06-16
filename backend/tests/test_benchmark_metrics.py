import pytest

from app.scoring.scoring_interface import PlaceholderScoringEngine, ModelScores


def make_results(verdicts_by_category: dict[str, list[str]], latency: int = 100) -> list[dict]:
    rows = []
    for cat, verdicts in verdicts_by_category.items():
        for v in verdicts:
            rows.append({"category": cat, "verdict": v, "latency_ms": latency, "score": 0.5})
    return rows


def test_all_pass():
    engine = PlaceholderScoringEngine()
    results = make_results({
        "PROMPT_INJECTION": ["PASS", "PASS"],
        "JAILBREAK": ["PASS"],
    })
    scores = engine.compute_scores("model-a", results)
    assert scores.overall_score == 100.0
    assert scores.injection_rate == 0.0
    assert scores.jailbreak_rate == 0.0


def test_all_fail():
    engine = PlaceholderScoringEngine()
    results = make_results({
        "PROMPT_INJECTION": ["FAIL", "FAIL"],
        "JAILBREAK": ["FAIL"],
        "DATA_LEAKAGE": ["FAIL"],
        "CONTEXT_MANIPULATION": ["FAIL"],
    })
    scores = engine.compute_scores("model-b", results)
    assert scores.overall_score == 0.0
    assert scores.injection_rate == 1.0


def test_mixed():
    engine = PlaceholderScoringEngine()
    results = make_results({
        "PROMPT_INJECTION": ["FAIL", "PASS"],  # 50% fail rate
        "JAILBREAK": ["PASS", "PASS"],          # 0%
    })
    scores = engine.compute_scores("model-c", results)
    assert scores.injection_rate == 0.5
    assert scores.jailbreak_rate == 0.0


def test_empty_results():
    engine = PlaceholderScoringEngine()
    scores = engine.compute_scores("model-d", [])
    assert isinstance(scores, ModelScores)
    assert scores.overall_score == 0.0
    assert scores.total_tests == 0


def test_avg_latency():
    engine = PlaceholderScoringEngine()
    results = [
        {"category": "JAILBREAK", "verdict": "PASS", "latency_ms": 100, "score": 1.0},
        {"category": "JAILBREAK", "verdict": "PASS", "latency_ms": 200, "score": 1.0},
    ]
    scores = engine.compute_scores("model-e", results)
    assert scores.avg_latency_ms == 150.0
