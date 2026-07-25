"""Pluggable similarity architecture for the Evaluation Workbench.

A :class:`SimilarityProvider` scores how close a model response is to a baseline
(golden / expected output) on a 0–100 scale. Providers are registered here;
adding a new one (e.g. a real embedding model, or an LLM judge) is a one-file
change and requires no caller updates.

Honesty: the current providers are deterministic and fully local — Exact Match
and Text Similarity are real; the Embedding provider uses a local character-ngram
vector (a stand-in for a real embedding model) and is flagged ``simulated=True``.
The LLM-judge provider is declared as architecture and marked unavailable until a
judge model is wired in.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional, Protocol

_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class SimilarityResult:
    score: float                                  # 0–100 (higher = closer to baseline)
    method: str
    detail: dict = field(default_factory=dict)
    simulated: bool = False

    def to_dict(self) -> dict:
        return {"score": self.score, "method": self.method,
                "detail": self.detail, "simulated": self.simulated}


class SimilarityProvider(Protocol):
    key: str
    label: str
    description: str
    available: bool

    def score(self, candidate: str, reference: str) -> SimilarityResult: ...


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _tokens(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


class ExactMatchProvider:
    key = "exact"
    label = "Exact Match"
    description = "100 if the normalized response equals the baseline, else 0."
    available = True

    def score(self, candidate: str, reference: str) -> SimilarityResult:
        hit = _norm(candidate) == _norm(reference) and _norm(reference) != ""
        return SimilarityResult(100.0 if hit else 0.0, self.key, {"match": hit})


class TextSimilarityProvider:
    key = "text"
    label = "Text Similarity"
    description = "Deterministic local blend of sequence ratio and token overlap (Jaccard)."
    available = True

    def score(self, candidate: str, reference: str) -> SimilarityResult:
        from difflib import SequenceMatcher

        c, r = _norm(candidate), _norm(reference)
        if not r:
            return SimilarityResult(0.0, self.key, {"note": "no baseline"})
        ratio = SequenceMatcher(None, c, r).ratio()
        ct, rt = set(_tokens(c)), set(_tokens(r))
        jaccard = (len(ct & rt) / len(ct | rt)) if (ct or rt) else 0.0
        blended = round((0.6 * ratio + 0.4 * jaccard) * 100, 2)
        return SimilarityResult(
            blended, self.key,
            {"sequence_ratio": round(ratio, 4), "token_jaccard": round(jaccard, 4)},
        )


class EmbeddingSimilarityProvider:
    key = "embedding"
    label = "Embedding Similarity (local)"
    description = ("Cosine similarity of local character-trigram frequency vectors. A "
                   "stand-in for a real embedding model — flagged simulated until one is attached.")
    available = True

    def _vector(self, text: str) -> dict[str, int]:
        s = f"  {_norm(text).lower()} "
        vec: dict[str, int] = {}
        for i in range(len(s) - 2):
            g = s[i:i + 3]
            vec[g] = vec.get(g, 0) + 1
        return vec

    def score(self, candidate: str, reference: str) -> SimilarityResult:
        a, b = self._vector(candidate), self._vector(reference)
        if not b:
            return SimilarityResult(0.0, self.key, {"note": "no baseline"}, simulated=True)
        dot = sum(a.get(g, 0) * b.get(g, 0) for g in set(a) | set(b))
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        cos = (dot / (na * nb)) if (na and nb) else 0.0
        return SimilarityResult(round(cos * 100, 2), self.key,
                                {"cosine": round(cos, 4)}, simulated=True)


class LLMJudgeProvider:
    """Architecture placeholder — an LLM judge would score semantic equivalence.
    Declared but unavailable until a judge model is wired in; scoring falls back
    to text similarity so callers never break."""

    key = "llm_judge"
    label = "LLM Judge (future)"
    description = "Semantic scoring by a judge model. Not enabled — falls back to text similarity."
    available = False

    def score(self, candidate: str, reference: str) -> SimilarityResult:  # pragma: no cover
        res = TextSimilarityProvider().score(candidate, reference)
        res.method = self.key
        res.simulated = True
        res.detail["note"] = "llm judge not available — text-similarity fallback"
        return res


_PROVIDERS: dict[str, SimilarityProvider] = {
    p.key: p for p in (
        ExactMatchProvider(), TextSimilarityProvider(),
        EmbeddingSimilarityProvider(), LLMJudgeProvider(),
    )
}

DEFAULT_SIMILARITY = "text"


def get_similarity(key: Optional[str]) -> SimilarityProvider:
    return _PROVIDERS.get(key or "", _PROVIDERS[DEFAULT_SIMILARITY])


def list_similarity() -> list[dict]:
    return [{"key": p.key, "label": p.label, "description": p.description,
             "available": p.available} for p in _PROVIDERS.values()]
