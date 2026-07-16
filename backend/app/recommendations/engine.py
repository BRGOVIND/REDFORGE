"""Recommendation engine — pure, deterministic logic.

Given a normalized ``ModelContext`` (assembled by the service from existing
metadata), produce a structured recommendation. No I/O, no DB, no model calls —
so it's fully testable and never duplicates the training/security/dataset engines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.runtime.model_sizes import parse_param_billions

DISCLAIMER = (
    "These are heuristic estimates from local metadata, not guarantees. Actual "
    "improvement depends on data quality and training dynamics — re-evaluate with "
    "Continuous Security to confirm."
)

# Curated public datasets (suggested only — never downloaded automatically).
_PUBLIC_DATASETS = {
    "safety": [
        {"name": "Anthropic HH-RLHF", "url": "https://huggingface.co/datasets/Anthropic/hh-rlhf",
         "reason": "Human preference data for harmlessness — directly targets jailbreak/injection weaknesses."},
        {"name": "OpenAssistant (OASST)", "url": "https://huggingface.co/datasets/OpenAssistant/oasst1",
         "reason": "Assistant conversations with safety-aware responses."},
    ],
    "instruction": [
        {"name": "OpenHermes", "url": "https://huggingface.co/datasets/teknium/OpenHermes-2.5",
         "reason": "High-quality instruction data to reinforce instruction-following under adversarial prompts."},
        {"name": "UltraChat", "url": "https://huggingface.co/datasets/stingning/ultrachat",
         "reason": "Large multi-turn instruction set — strengthens context handling."},
        {"name": "LIMA", "url": "https://huggingface.co/datasets/GAIR/lima",
         "reason": "Small, curated, high-quality set — good for targeted alignment without overfitting."},
    ],
    "general": [
        {"name": "Alpaca", "url": "https://huggingface.co/datasets/tatsu-lab/alpaca",
         "reason": "Compact general instruction data — a fast baseline for fine-tuning."},
        {"name": "Dolly", "url": "https://huggingface.co/datasets/databricks/databricks-dolly-15k",
         "reason": "Human-written instructions across categories."},
    ],
}

# Which dataset theme addresses which weakness category.
_CATEGORY_THEME = {
    "PROMPT_INJECTION": "safety",
    "JAILBREAK": "safety",
    "POLICY_EVASION": "safety",
    "ROLEPLAY": "safety",
    "CONTEXT_MANIPULATION": "instruction",
    "RAG": "instruction",
    "DATA_LEAKAGE": "safety",
}


@dataclass
class ModelContext:
    target_model: str
    security_score: Optional[float] = None
    categories: list[dict] = field(default_factory=list)   # [{category, score, risk_level, ...}]
    findings: list[dict] = field(default_factory=list)
    total_tests: int = 0
    last_training: Optional[dict] = None                    # prior run config (method, rank, lr, ...)
    dataset: Optional[dict] = None                          # {quality_score, record_count, issues}
    score_trend: Optional[float] = None                    # last - first over the timeline
    project_datasets: list[dict] = field(default_factory=list)  # [{id, name, quality, records}]


def _weaknesses(ctx: ModelContext) -> list[dict]:
    out = []
    for c in ctx.categories:
        risk = (c.get("risk_level") or "none").lower()
        if risk in ("none",):
            continue
        out.append({
            "category": c.get("category"),
            "severity": risk,
            "score": c.get("score"),
            "description": f"{c.get('category')} shows {risk} risk (category score {c.get('score')}).",
        })
    out.sort(key=lambda w: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(w["severity"], 4))
    return out


def _strategy(ctx: ModelContext) -> dict:
    billions = parse_param_billions(ctx.target_model) or 0
    if billions >= 13:
        return {
            "method": "qlora",
            "reason": f"{ctx.target_model} is large (~{billions:g}B). QLoRA loads the base in 4-bit, "
                      "cutting VRAM so it fits on a single GPU with minimal quality loss.",
        }
    return {
        "method": "lora",
        "reason": f"{ctx.target_model} is small enough (~{billions:g}B) to train with full-precision "
                  "LoRA adapters — maximum quality, and VRAM isn't the constraint.",
    }


def _hyperparameters(ctx: ModelContext, weaknesses: list[dict]) -> dict:
    severe = sum(1 for w in weaknesses if w["severity"] in ("critical", "high"))
    n_weak = len(weaknesses)

    # Rank scales with how much the model needs to learn.
    rank = 32 if severe >= 2 else 16 if n_weak else 8
    alpha = rank * 2
    epochs = 4 if severe >= 2 else 3 if n_weak else 2

    prior = ctx.last_training or {}
    prior_lr = prior.get("learning_rate")
    # If a prior run existed and security didn't improve, lower the LR + add warmup.
    if prior_lr and (ctx.score_trend is not None and ctx.score_trend <= 0):
        learning_rate = round(prior_lr * 0.5, 6)
        lr_reason = "Prior training didn't improve security — halving the learning rate to stabilize."
        warmup = max(20, prior.get("warmup_steps", 10) * 2)
    else:
        learning_rate = 2e-4
        lr_reason = "2e-4 is a solid LoRA default; lower it if loss becomes unstable."
        warmup = 10

    return {
        "rank": rank,
        "alpha": alpha,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "batch_size": 2,
        "gradient_accumulation": 4,
        "scheduler": "cosine",
        "optimizer": "adamw_8bit",
        "warmup_steps": warmup,
        "rationale": {
            "rank": f"Rank {rank}: {'more capacity for several weak areas' if rank >= 32 else 'balanced capacity vs. overfitting'}.",
            "alpha": f"Alpha {alpha} (≈2×rank) — the common scaling convention.",
            "epochs": f"{epochs} epoch(s): {'more passes to address multiple high-severity weaknesses' if epochs >= 4 else 'enough to adapt without overfitting'}.",
            "learning_rate": lr_reason,
            "batch_size": "Batch 2 × grad-accum 4 → effective batch 8; raise accumulation if VRAM allows.",
            "scheduler": "Cosine decay with warmup is stable for short LoRA runs.",
            "optimizer": "adamw_8bit keeps optimizer memory low.",
            "warmup_steps": f"{warmup} warmup steps to avoid early instability.",
        },
    }


def _datasets(ctx: ModelContext, weaknesses: list[dict]) -> dict:
    themes = {_CATEGORY_THEME.get(w["category"], "instruction") for w in weaknesses} or {"instruction"}
    public: list[dict] = []
    seen = set()
    for theme in list(themes) + ["general"]:
        for d in _PUBLIC_DATASETS.get(theme, []):
            if d["name"] not in seen:
                seen.add(d["name"])
                public.append({**d, "theme": theme})

    # Existing project datasets that look usable (decent quality + enough records).
    project = []
    for d in ctx.project_datasets:
        fit = "good candidate" if (d.get("quality", 0) >= 70 and d.get("records", 0) >= 50) else "usable, but small/low-quality"
        project.append({"id": d.get("id"), "name": d.get("name"), "fit": fit,
                        "quality": d.get("quality"), "records": d.get("records")})

    return {"project": project, "public": public[:5]}


def _attacks(ctx: ModelContext, weaknesses: list[dict]) -> dict:
    # Low confidence when few tests were run, or many UNCERTAIN verdicts.
    low_confidence = ctx.total_tests < 30
    recommend = low_confidence or len(weaknesses) == 0
    cats = [w["category"] for w in weaknesses] or ["PROMPT_INJECTION", "JAILBREAK"]
    reason = ("Few attacks were run — widen coverage before trusting the score."
              if low_confidence else
              "No weaknesses found — run a broader profile to confirm robustness.")
    return {"recommend_more": recommend, "categories": sorted(set(cats)),
            "reason": reason if recommend else "Current coverage looks sufficient for the detected weaknesses."}


def _prediction(ctx: ModelContext, weaknesses: list[dict]) -> dict:
    score = ctx.security_score if ctx.security_score is not None else 60.0
    # Lower current score + more addressable weaknesses ⇒ larger potential headroom.
    headroom = max(0.0, 90.0 - score)
    severity_factor = min(1.0, sum({"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.2}.get(w["severity"], 0.2)
                                   for w in weaknesses) / 2.0)
    expected_security = round(min(headroom, headroom * 0.4 + severity_factor * 8), 1)
    expected_benchmark = round(expected_security * 0.3, 1)  # benchmark moves less than the targeted score

    # Confidence rises with data completeness.
    conf = 0.35
    if ctx.total_tests >= 30:
        conf += 0.2
    if ctx.dataset is not None:
        conf += 0.15
    if ctx.last_training is not None:
        conf += 0.15
    conf = round(min(0.85, conf), 2)

    return {
        "expected_security_gain": expected_security,
        "expected_benchmark_gain": expected_benchmark,
        "confidence": conf,
        "explanation": (
            f"Current score {score:.0f} leaves ~{headroom:.0f} points of headroom; addressing "
            f"{len(weaknesses)} weakness(es) with the recommended data/config typically recovers a "
            f"fraction of that. Confidence {conf} reflects how complete the local signals are "
            f"(tests={ctx.total_tests}, dataset={'yes' if ctx.dataset else 'no'}, "
            f"history={'yes' if ctx.last_training else 'no'})."
        ),
        "disclaimer": DISCLAIMER,
    }


def recommend(ctx: ModelContext) -> dict:
    """Produce the full recommendation for a model context."""
    weaknesses = _weaknesses(ctx)
    strategy = _strategy(ctx)
    hyperparameters = _hyperparameters(ctx, weaknesses)
    prediction = _prediction(ctx, weaknesses)
    n = len(weaknesses)
    summary = (
        f"No weaknesses detected — {ctx.target_model} looks robust; consider a broader attack profile to confirm."
        if n == 0 else
        f"{ctx.target_model} has {n} weakness(es) (top: {weaknesses[0]['category']}). "
        f"Recommend {strategy['method'].upper()} fine-tuning (rank {hyperparameters['rank']}, "
        f"{hyperparameters['epochs']} epochs) with targeted data; estimated +{prediction['expected_security_gain']} "
        f"security points (confidence {prediction['confidence']})."
    )
    return {
        "target_model": ctx.target_model,
        "summary": summary,
        "weaknesses": weaknesses,
        "strategy": strategy,
        "hyperparameters": hyperparameters,
        "datasets": _datasets(ctx, weaknesses),
        "attacks": _attacks(ctx, weaknesses),
        "prediction": prediction,
    }
