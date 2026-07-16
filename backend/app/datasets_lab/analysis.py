"""Dataset statistics + quality analysis (pure, offline).

All heuristics are dependency-free and local. ``analyze`` returns a structured
report the UI and the Assistant both consume; ``quality_score`` folds the issues
into a single 0–100 number. No network, no model calls.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

# Rough token estimate: ~4 chars/token (English-ish). Good enough for a ballpark.
_CHARS_PER_TOKEN = 4

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_LATIN = re.compile(r"[A-Za-z]")
_CJK = re.compile(r"[一-鿿぀-ヿ]")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_ARABIC = re.compile(r"[؀-ۿ]")

# Prompt-leakage / unsafe signal lists (heuristic, English-leaning).
_LEAKAGE_MARKERS = [
    "ignore previous instructions", "ignore all previous", "system prompt",
    "you are chatgpt", "as an ai language model", "begin system", "<|im_start|>",
]
_UNSAFE_MARKERS = [
    "how to make a bomb", "build a weapon", "child sexual", "credit card number",
    "social security number", "kill yourself",
]


def _row_text(row: Any) -> str:
    if isinstance(row, str):
        return row
    if isinstance(row, dict):
        return " ".join(str(v) for v in row.values() if v is not None)
    return str(row)


def _detect_language(text: str) -> str:
    """Coarse script-based language guess. Not ISO-accurate — a hint only."""
    if _CJK.search(text):
        return "cjk"
    if _CYRILLIC.search(text):
        return "cyrillic"
    if _ARABIC.search(text):
        return "arabic"
    if _LATIN.search(text):
        return "latin"
    return "other"


def statistics(records: list[Any], kind: str, byte_size: int) -> dict:
    texts = [_row_text(r) for r in records]
    lengths = [len(t) for t in texts]
    total_chars = sum(lengths)
    langs = Counter(_detect_language(t) for t in texts if t.strip())
    return {
        "record_count": len(records),
        "kind": kind,
        "file_size_bytes": byte_size,
        "total_chars": total_chars,
        "estimated_tokens": total_chars // _CHARS_PER_TOKEN,
        "avg_length": round(total_chars / len(records), 1) if records else 0,
        "min_length": min(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "languages": dict(langs.most_common()),
    }


def _is_conversation(row: Any) -> bool:
    return isinstance(row, dict) and ("messages" in row or ("role" in row and "content" in row))


def _malformed_conversation(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if "messages" in row:
        msgs = row.get("messages")
        if not isinstance(msgs, list) or not msgs:
            return True
        return any(not isinstance(m, dict) or "role" not in m or "content" not in m for m in msgs)
    return False


def analyze(records: list[Any], kind: str, columns: list[str], byte_size: int) -> dict:
    """Full quality report + score. Consumed by the UI and the Assistant."""
    stats = statistics(records, kind, byte_size)
    texts = [_row_text(r) for r in records]

    # Duplicates (exact, normalized).
    seen: Counter = Counter(t.strip().lower() for t in texts)
    duplicates = sum(c - 1 for c in seen.values() if c > 1)

    # Missing / empty.
    empty = sum(1 for t in texts if not t.strip())
    missing_values = 0
    if kind == "records" and columns:
        for r in records:
            if isinstance(r, dict):
                missing_values += sum(1 for c in columns if not str(r.get(c, "")).strip())

    # Formatting issues: leading/trailing whitespace, non-breaking spaces, tabs.
    formatting_issues = sum(
        1 for t in texts if t != t.strip() or " " in t or "\t" in t
    )

    # Safety heuristics.
    lowered = [t.lower() for t in texts]
    prompt_leakage = sum(1 for t in lowered if any(m in t for m in _LEAKAGE_MARKERS))
    unsafe = sum(1 for t in lowered if any(m in t for m in _UNSAFE_MARKERS))

    # Malformed conversations (only meaningful for chat-shaped records).
    malformed = sum(1 for r in records if _malformed_conversation(r))

    n = max(len(records), 1)
    issues = {
        "duplicates": duplicates,
        "empty_records": empty,
        "missing_values": missing_values,
        "formatting_issues": formatting_issues,
        "prompt_leakage": prompt_leakage,
        "unsafe_samples": unsafe,
        "malformed_conversations": malformed,
    }

    score = _quality_score(issues, n, stats)
    return {
        "score": score,
        "grade": _grade(score),
        "issues": issues,
        "statistics": stats,
        "suggestions": _suggestions(issues, stats),
    }


def _quality_score(issues: dict, n: int, stats: dict) -> int:
    """0–100, starting at 100 and deducting for issue prevalence (bounded)."""
    def rate(x: int) -> float:
        return min(1.0, x / n)

    penalty = 0.0
    penalty += rate(issues["duplicates"]) * 25
    penalty += rate(issues["empty_records"]) * 20
    penalty += rate(issues["formatting_issues"]) * 10
    penalty += min(1.0, issues["missing_values"] / (n * max(1, len(stats.get("languages", {})) or 1))) * 10
    penalty += rate(issues["malformed_conversations"]) * 20
    penalty += rate(issues["prompt_leakage"]) * 10
    penalty += rate(issues["unsafe_samples"]) * 15
    if n < 10:
        penalty += 10  # very small datasets are low-confidence
    return max(0, min(100, round(100 - penalty)))


def _grade(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


def _suggestions(issues: dict, stats: dict) -> list[str]:
    out: list[str] = []
    if issues["duplicates"]:
        out.append(f"Remove {issues['duplicates']} duplicate record(s).")
    if issues["empty_records"]:
        out.append(f"Drop {issues['empty_records']} empty record(s).")
    if issues["formatting_issues"]:
        out.append("Trim whitespace / normalize formatting.")
    if issues["malformed_conversations"]:
        out.append(f"Fix {issues['malformed_conversations']} malformed conversation(s).")
    if issues["unsafe_samples"]:
        out.append(f"Review {issues['unsafe_samples']} potentially unsafe sample(s).")
    if issues["prompt_leakage"]:
        out.append(f"Inspect {issues['prompt_leakage']} record(s) that look like prompt leakage.")
    if stats["record_count"] < 50:
        out.append("Dataset is small; consider adding more examples for instruction tuning.")
    if not out:
        out.append("No major issues detected.")
    return out
