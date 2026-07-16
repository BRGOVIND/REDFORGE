"""RedForge Assistant — local knowledge assistant (RedForge V2, Phase 1).

Answers from a curated, in-repo knowledge base with a simple keyword retriever.
Fully **offline** — no model, no network, no accounts, no telemetry. The
retriever is deliberately pluggable: swap :func:`_retrieve` for a vector/RAG
search later without changing the API or the frontend.

Privacy: this endpoint never uploads user models, datasets, or conversations
anywhere. Optional web search (HuggingFace / GitHub / docs / ArXiv) is a
future, explicitly opt-in capability and is intentionally not enabled here.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


# Curated knowledge. Each entry is a small, self-contained explainer. Keywords
# drive retrieval; a RAG retriever would replace this list with an index.
_KB: list[dict] = [
    {
        "id": "eval-score",
        "title": "Reading a security score",
        "keywords": ["score", "result", "evaluation", "verdict", "pass", "fail", "report"],
        "body": "A RedForge security score (0–100) summarizes how well a model resisted the "
                "attack suite: higher is safer. Each attack yields PASS / FAIL / UNCERTAIN. "
                "Open the report for category breakdowns, ranked vulnerabilities, and "
                "recommendations.",
    },
    {
        "id": "prompt-injection",
        "title": "What is prompt injection?",
        "keywords": ["prompt", "injection", "attack", "override", "instructions"],
        "body": "Prompt injection tries to override the model's instructions with adversarial "
                "input (e.g. 'ignore previous instructions'). RedForge tests many variants; a "
                "FAIL means the model followed the injected instruction.",
    },
    {
        "id": "jailbreak",
        "title": "What is a jailbreak?",
        "keywords": ["jailbreak", "roleplay", "dan", "bypass", "policy", "evasion"],
        "body": "A jailbreak coaxes a model past its safety policy, often via roleplay or "
                "hypotheticals. RedForge groups these under Jailbreak / Roleplay / Policy "
                "Evasion categories in the Attack Library.",
    },
    {
        "id": "provider-setup",
        "title": "Setting up a runtime provider",
        "keywords": ["provider", "runtime", "ollama", "lmstudio", "llama", "vllm", "setup", "offline",
                     "api key", "openai", "anthropic", "gemini", "groq"],
        "body": "RedForge runs models through a runtime provider — Ollama (recommended default), "
                "LM Studio, llama.cpp, or vLLM locally, or OpenAI/Anthropic/Gemini/Groq/OpenRouter "
                "with an API key. Pick one on the Runtime page; onboarding can recommend and "
                "download a model that fits your hardware.",
    },
    {
        "id": "provider-offline",
        "title": "Fixing 'runtime provider is offline'",
        "keywords": ["offline", "unreachable", "error", "provider", "not running", "connection"],
        "body": "Your selected runtime isn't reachable. Start it (for Ollama: `ollama serve`), "
                "confirm its base URL, then re-check on the Runtime page or with `redforge doctor`. "
                "Cloud providers need their API key set.",
    },
    {
        "id": "playground",
        "title": "Using the Playground",
        "keywords": ["playground", "chat", "temperature", "top_p", "system prompt", "seed", "tokens"],
        "body": "The Playground lets you chat with any configured provider and tune sampling "
                "(temperature, top-p, max tokens, seed, system prompt). Click 'Run Security "
                "Evaluation' to send the current prompt straight into the evaluation engine.",
    },
    {
        "id": "projects",
        "title": "Projects and the AI Studio",
        "keywords": ["project", "workspace", "studio", "organize", "recent", "duplicate"],
        "body": "Projects are local workspaces that group models, evaluations, reports, and "
                "settings. Create, open, rename, duplicate, or delete them from the Studio. "
                "Recent projects appear on the dashboard. Everything stays on your machine.",
    },
    {
        "id": "local-first",
        "title": "Is my data private?",
        "keywords": ["privacy", "local", "cloud", "data", "telemetry", "account", "offline"],
        "body": "Yes. RedForge is local-first: no accounts, no telemetry, no required API keys, "
                "and it works fully offline. Nothing — models, datasets, prompts, or results — "
                "leaves your machine unless you explicitly configure a cloud provider.",
    },
    {
        "id": "dataset-lab",
        "title": "The Dataset Lab",
        "keywords": ["dataset", "datasets", "import", "quality", "clean", "split", "version",
                     "duplicates", "tuning", "csv", "jsonl"],
        "body": "The Dataset Lab manages local datasets as project assets: import CSV/JSON/JSONL/"
                "TXT/MD/PDF/DOCX, preview rows, analyze quality, clean (dedupe, trim, normalize, "
                "drop empty), split train/validation/test, and version every save. Open a dataset "
                "and ask me about its quality for specifics.",
    },
    {
        "id": "lora-vs-qlora",
        "title": "LoRA vs QLoRA",
        "keywords": ["lora", "qlora", "method", "quantized", "4bit", "which", "choose", "vram"],
        "body": "LoRA trains small adapter matrices on top of a frozen model — fast, but the base "
                "weights sit in full/half precision. QLoRA loads the base model in 4-bit (quantized) "
                "and trains LoRA adapters on top, cutting VRAM sharply. Use QLoRA when VRAM is tight "
                "or the model is large; LoRA when you have VRAM to spare and want maximum quality.",
    },
    {
        "id": "rank",
        "title": "Explain LoRA rank (r)",
        "keywords": ["rank", "r", "lora"],
        "body": "Rank is the size of the low-rank adapter matrices. Higher rank = more trainable "
                "capacity (can fit more, but risks overfitting and uses more memory); lower rank = "
                "lighter, more regularized. 8–32 is a common range; 16 is a solid default.",
    },
    {
        "id": "alpha",
        "title": "Explain LoRA alpha",
        "keywords": ["alpha", "scaling", "lora"],
        "body": "Alpha scales the LoRA update (effective scale ≈ alpha / rank). A common convention "
                "is alpha = 2×rank (e.g. rank 16, alpha 32). Raising alpha strengthens the adapter's "
                "influence; lowering it softens it.",
    },
    {
        "id": "batch-size",
        "title": "Explain batch size & gradient accumulation",
        "keywords": ["batch", "size", "gradient", "accumulation", "memory", "oom"],
        "body": "Batch size is how many samples are processed before an optimizer step; larger "
                "batches are smoother but use more VRAM. Gradient accumulation simulates a larger "
                "effective batch (batch_size × accumulation) without the memory cost — lower the "
                "batch size and raise accumulation if you hit out-of-memory.",
    },
    {
        "id": "learning-rate",
        "title": "Learning rate & loss behavior",
        "keywords": ["learning", "rate", "lr", "loss", "increasing", "diverge", "reduce", "scheduler"],
        "body": "If loss increases or spikes, the learning rate is likely too high — reduce it "
                "(e.g. halve it) or add warmup. LoRA typically uses 1e-4 to 3e-4. A cosine scheduler "
                "with a short warmup is a good default. Steadily rising validation loss while train "
                "loss falls means overfitting — fewer epochs or lower rank.",
    },
    {
        "id": "vram",
        "title": "Why is VRAM full?",
        "keywords": ["vram", "memory", "full", "oom", "out of memory", "gpu"],
        "body": "VRAM fills from model weights + activations + optimizer state. To reduce it: use "
                "QLoRA (4-bit base), lower the batch size (raise gradient accumulation to compensate), "
                "shorten max sequence length, or pick a smaller base model.",
    },
]

_SUGGESTIONS = [
    "How do I read a security score?",
    "What is prompt injection?",
    "How do I set up a runtime provider?",
    "The provider is offline — how do I fix it?",
    "How do Projects work?",
    "Is my data private?",
]


class AskRequest(BaseModel):
    question: str
    # Optional page/context hint so the retriever can be biased later (RAG-ready).
    context: str | None = None
    # Optional dataset to answer against, using ONLY its local cached metadata.
    dataset_id: Optional[str] = None
    # Optional training run to answer against, using ONLY local run metadata.
    run_id: Optional[str] = None
    # Optional recommendation to answer against, using ONLY its local payload.
    recommendation_id: Optional[str] = None
    # Optional project to scope benchmark answers, using ONLY local results.
    project_id: Optional[str] = None


class Source(BaseModel):
    id: str
    title: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    suggestions: list[str]


_WORD = re.compile(r"[a-z0-9_]+")


def _retrieve(question: str, k: int = 2) -> list[dict]:
    """Keyword-overlap retriever. Swap for a vector/RAG search later — the return
    shape (list of KB entries) is what the API contract depends on."""
    terms = set(_WORD.findall(question.lower()))
    scored = []
    for entry in _KB:
        kw = set(entry["keywords"])
        overlap = len(terms & kw)
        # small boost when a keyword appears verbatim in the question
        boost = sum(1 for k_ in kw if k_ in question.lower())
        score = overlap * 2 + boost
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [e for _, e in scored[:k]]


@router.get("/suggestions")
async def suggestions() -> dict:
    return {"suggestions": _SUGGESTIONS}


async def _dataset_answer(db: AsyncSession, dataset_id: str, question: str) -> Optional[str]:
    """Answer a dataset question from LOCAL cached metadata only (no external
    calls, no model). Runs the local analyzer if a fresh report is needed."""
    from app.datasets_lab import dataset_service

    meta = await dataset_service.get(db, dataset_id)
    if meta is None:
        return None
    report = await dataset_service.analyze(db, dataset_id)  # local, offline
    if report is None:
        return None
    issues = report["issues"]
    st = report["statistics"]
    q = question.lower()

    if "duplicate" in q:
        return f"**{meta['name']}** has **{issues['duplicates']}** duplicate record(s) " \
               f"out of {st['record_count']}. Use Clean → Remove duplicates to drop them."
    if "quality" in q or "wrong" in q or "low" in q:
        drivers = [k.replace("_", " ") for k, v in issues.items() if v]
        detail = ", ".join(drivers) if drivers else "no major issues"
        return f"**{meta['name']}** scores **{report['score']}/100** ({report['grade']}). " \
               f"Main factors: {detail}. Suggestions: " + " ".join(report["suggestions"][:3])
    if "instruction" in q or "tuning" in q or "suitable" in q:
        ok = report["score"] >= 70 and st["record_count"] >= 50 and issues["malformed_conversations"] == 0
        verdict = "looks suitable" if ok else "needs cleanup first"
        return f"For instruction tuning, **{meta['name']}** {verdict}: {st['record_count']} records, " \
               f"quality {report['score']}/100, {issues['malformed_conversations']} malformed conversation(s), " \
               f"{issues['duplicates']} duplicate(s). Clean and re-check before training."
    # Generic dataset summary.
    active = ", ".join(f"{k.replace('_', ' ')}={v}" for k, v in issues.items() if v) or "none"
    return f"**{meta['name']}** — {st['record_count']} records, ~{st['estimated_tokens']} tokens, " \
           f"quality {report['score']}/100 ({report['grade']}). Issues: {active}."


async def _security_evolution_answer(run_id: str, question: str) -> Optional[str]:
    """Answer security-evolution questions from the LOCAL Continuous Security
    timeline (per-checkpoint scores). Returns None if the question isn't about
    security evolution or there's no timeline yet."""
    from app.continuous_security import continuous_security

    q = question.lower()
    triggers = ("security score", "attacks improved", "vulnerabilit", "continue training",
                "changed between", "checkpoint", "regress")
    if not any(t in q for t in triggers):
        return None

    tl = [t for t in await continuous_security.timeline(run_id) if t.get("score") is not None]
    if len(tl) < 1:
        return None
    first, last = tl[0], tl[-1]

    # "which checkpoint is best" / "deploy checkpoint X or the final model"
    if "best checkpoint" in q or "which checkpoint" in q or "deploy" in q:
        best = max(tl, key=lambda t: t["score"])
        if best["step"] == last["step"]:
            return (f"The final checkpoint (step {last['step']}, score {last['score']}) is the "
                    f"strongest — deploy that one.")
        return (f"Checkpoint at step {best['step']} scored highest ({best['score']}), above the "
                f"final checkpoint (step {last['step']}, {last['score']}). Prefer step "
                f"{best['step']} unless you need the final model's other capabilities.")
    if "more secure" in q or ("why" in q and "checkpoint" in q and "secure" in q):
        import re
        nums = [int(n) for n in re.findall(r"\b(\d+)\b", question)]
        target = next((t for t in tl if t["step"] in nums), last)
        return (f"Checkpoint at step {target['step']} scored {target['score']} because fine-tuning "
                f"reduced fail rates in its weak categories — see the checkpoint comparison for the "
                f"per-category deltas.")

    # "what changed between checkpoint N and M"
    import re
    nums = [int(n) for n in re.findall(r"\b(\d+)\b", question)]
    if "changed between" in q and len(nums) >= 2:
        cmp = await continuous_security.compare(run_id, nums[0], nums[1])
        if cmp is None:
            return f"I don't have completed evaluations for steps {nums[0]} and {nums[1]} yet."
        return (f"Between step {nums[0]} and {nums[1]} the security score moved "
                f"{cmp['a']['score']} → {cmp['b']['score']} (Δ {cmp['score_delta']:+.0f}). "
                f"Improved: {', '.join(cmp['improved_categories']) or 'none'}. "
                f"Regressed: {', '.join(cmp['regressed_categories']) or 'none'}. "
                f"Resolved: {', '.join(cmp['resolved_vulnerabilities']) or 'none'}. "
                f"New: {', '.join(cmp['new_vulnerabilities']) or 'none'}.")

    if "decrease" in q or "regress" in q or "why" in q:
        if last["score"] < first["score"]:
            return (f"Security **decreased** ({first['score']} → {last['score']} over "
                    f"{len(tl)} checkpoints). That usually means fine-tuning weakened some "
                    f"safety behavior — check the regressed categories in the comparison, "
                    f"lower the learning rate, or add safety examples to the dataset.")
        return f"Security did not decrease — it went {first['score']} → {last['score']} across {len(tl)} checkpoints."

    if "improved" in q:
        cmp = await continuous_security.compare(run_id, first["step"], last["step"])
        imp = ", ".join(cmp["improved_categories"]) if cmp else ""
        return f"Improved categories from step {first['step']} to {last['step']}: {imp or 'none yet'}."

    if "vulnerabilit" in q or "remain" in q:
        cats = last.get("categories") or []
        risky = [c["category"] for c in cats if (c.get("risk_level") or "none") not in ("none",)]
        return (f"At the latest checkpoint (step {last['step']}, score {last['score']}), "
                f"remaining risk areas: {', '.join(risky) or 'none flagged'}.")

    if "continue training" in q:
        trend = last["score"] - first["score"]
        if trend > 1:
            return f"Security is trending up ({first['score']} → {last['score']}). Continuing looks worthwhile; keep monitoring the timeline."
        if trend < -1:
            return f"Security is trending down ({first['score']} → {last['score']}). Consider stopping or lowering the learning rate before continuing."
        return f"Security is roughly flat ({first['score']} → {last['score']}). More epochs may not help security; review the dataset."

    # Generic evolution summary
    scores = " → ".join(str(t["score"]) for t in tl)
    return f"Security timeline for this run: {scores} across {len(tl)} checkpoint(s)."


async def _training_answer(db: AsyncSession, run_id: str, question: str) -> Optional[str]:
    """Answer a training question from LOCAL run metadata + checkpoints only."""
    from app.training import training_service

    run = await training_service.get(db, run_id)
    if run is None:
        return None
    cps = await training_service.checkpoints(db, run_id) or []
    m = run.get("metrics") or {}
    losses = [c["loss"] for c in cps if c.get("loss") is not None]
    val_losses = [c["val_loss"] for c in cps if c.get("val_loss") is not None]
    q = question.lower()

    rising = len(losses) >= 2 and losses[-1] > losses[0]
    overfit = len(val_losses) >= 2 and val_losses[-1] > min(val_losses)

    if "loss" in q and ("increas" in q or "rising" in q or "diverg" in q):
        if rising:
            return (f"Loss is trending up on **{run['name']}** (first {losses[0]:.3f} → last "
                    f"{losses[-1]:.3f}). That usually means the learning rate is too high — "
                    f"reduce it (try halving), or add warmup steps.")
        return (f"Loss on **{run['name']}** is not increasing overall "
                f"(latest {m.get('final_loss')}). If you saw a transient spike, it's likely noise.")
    if "learning rate" in q or "reduce" in q:
        return (f"For **{run['name']}** (method {run['method']}, lr={run['config'].get('learning_rate')}), "
                f"reduce the learning rate if loss is unstable or rising. LoRA usually runs well at "
                f"1e-4–3e-4 with a short warmup.")
    if "overfit" in q or ("validation" in q and "loss" in q):
        verdict = "validation loss is rising while training continues — overfitting" if overfit \
            else "no clear overfitting yet"
        return f"On **{run['name']}**, {verdict}. If overfitting, use fewer epochs or a lower rank."
    # Generic run summary.
    return (f"**{run['name']}** — {run['method'].upper()} on {run['base_model']} "
            f"({run['backend']} backend), status {run['status']}. "
            f"Final loss {m.get('final_loss')}, val {m.get('final_val_loss')}, "
            f"{len(cps)} checkpoint(s).")


async def _recommendation_answer(db: AsyncSession, rec_id: str, question: str) -> Optional[str]:
    """Answer a recommendation question from its LOCAL stored payload."""
    from app.recommendations import recommendation_service

    rec = await recommendation_service.get(db, rec_id)
    if rec is None:
        return None
    p = rec.get("payload") or {}
    q = question.lower()

    if "dataset" in q and "recommend" in q or ("why" in q and "dataset" in q):
        ds = p.get("datasets", {})
        pub = ", ".join(f"{d['name']} ({d['reason']})" for d in ds.get("public", [])[:2])
        return f"Recommended datasets target the detected weaknesses: {pub or 'none'}. " \
               f"Project datasets: {', '.join(d['name'] for d in ds.get('project', [])) or 'none linked'}."
    if "improvement" in q or "expect" in q or "how much" in q:
        pr = p.get("prediction", {})
        return (f"Estimated **+{pr.get('expected_security_gain')}** security points "
                f"(benchmark ≈ +{pr.get('expected_benchmark_gain')}), confidence "
                f"{pr.get('confidence')}. {pr.get('explanation', '')} {pr.get('disclaimer', '')}")
    if "rank" in q:
        hp = p.get("hyperparameters", {})
        return f"Recommended rank {hp.get('rank')} (alpha {hp.get('alpha')}): {hp.get('rationale', {}).get('rank', '')}"
    if "lora" in q or "qlora" in q or "strategy" in q or "method" in q:
        st = p.get("strategy", {})
        return f"Recommended method: **{st.get('method', '').upper()}** — {st.get('reason', '')}"
    if "continue" in q:
        pr = p.get("prediction", {})
        gain = pr.get("expected_security_gain", 0)
        return (f"With an estimated +{gain} security points at confidence {pr.get('confidence')}, "
                f"fine-tuning with the recommended config is likely worthwhile — then re-evaluate.")
    # Generic
    return p.get("summary")


async def _benchmark_answer(question: str, project_id: Optional[str]) -> Optional[str]:
    """Answer benchmark questions from LOCAL Benchmark Center results only."""
    from app.benchmarks import benchmark_center

    q = question.lower()
    if not any(k in q for k in (
        "fast", "latency", "slow", "benchmark", "perform", "throughput",
        "tokens/sec", "tokens per sec", "deploy", "best model", "best checkpoint",
    )):
        return None

    rows = await benchmark_center.history(project_id=project_id, limit=200)
    completed = [r for r in rows if r["status"] == "completed"]
    if not completed:
        return None

    def perf(r):
        return (r.get("metrics", {}).get("performance") or {})

    # Which model is fastest? (highest tokens/sec, tie-break lowest avg latency)
    if "fast" in q or "throughput" in q or "tokens" in q:
        ranked = [r for r in completed if perf(r).get("tokens_per_sec") is not None]
        if ranked:
            top = max(ranked, key=lambda r: perf(r)["tokens_per_sec"])
            m = perf(top)
            return (f"**{top['label']}** is fastest: {m['tokens_per_sec']} tokens/sec, "
                    f"avg latency {m.get('avg_latency_ms')} ms, first-token "
                    f"{m.get('first_token_latency_ms')} ms.")

    # Why did latency increase? Compare earliest vs latest performance results.
    if "latency" in q and ("increase" in q or "why" in q or "slow" in q):
        withlat = [r for r in completed if perf(r).get("avg_latency_ms") is not None]
        withlat.sort(key=lambda r: r["created_at"] or "")
        if len(withlat) >= 2:
            first, last = withlat[0], withlat[-1]
            d = perf(last)["avg_latency_ms"] - perf(first)["avg_latency_ms"]
            hw = perf(last)
            trend = "increased" if d > 0 else "decreased"
            return (f"Average latency {trend} by {abs(round(d,1))} ms "
                    f"({perf(first)['avg_latency_ms']} → {perf(last)['avg_latency_ms']} ms). "
                    f"Latency tracks hardware and model size — last run: "
                    f"GPU={hw.get('gpu') or 'none'}, VRAM free={hw.get('vram_free_mb')} MB, "
                    f"RAM available={hw.get('ram_available_mb')} MB. A larger/less-quantized "
                    f"checkpoint or contended hardware raises it.")

    # Which checkpoint performs best? / Should I deploy checkpoint N?
    if "best" in q or "deploy" in q or "perform" in q:
        scored = [r for r in completed if r["overall_score"] is not None]
        if scored:
            top = max(scored, key=lambda r: r["overall_score"])
            answer = (f"**{top['label']}** has the best overall benchmark score "
                      f"({top['overall_score']}) across {', '.join(top['suites'])}.")
            if "deploy" in q:
                answer += (" It leads on the measured suites, so it's the strongest deploy "
                           "candidate — confirm the security suite meets your bar first. "
                           "Everything stays local; nothing is uploaded.")
            return answer
    return None


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, db: AsyncSession = Depends(get_db)) -> AskResponse:
    # Recommendation-scoped questions answered from the stored recommendation.
    if req.recommendation_id:
        r_answer = await _recommendation_answer(db, req.recommendation_id, req.question)
        if r_answer:
            return AskResponse(
                answer=r_answer,
                sources=[Source(id="recommendation", title="Recommendation (local)")],
                suggestions=[
                    "Why is this dataset recommended?",
                    "How much improvement should I expect?",
                    "Why this rank and method?",
                ],
            )

    # Recommendation-quality questions (accuracy history, biggest improvement).
    ql = req.question.lower()
    if "recommendation accuracy" in ql or "biggest improvement" in ql or "which recommendation" in ql:
        from app.recommendations import recommendation_service
        summ = await recommendation_service.accuracy_summary(db)
        if summ["count"]:
            best = summ.get("best_recommendation")
            if "biggest improvement" in ql or "which recommendation" in ql:
                if best:
                    o = best.get("outcome") or {}
                    return AskResponse(
                        answer=f"The biggest improvement came from the recommendation for "
                               f"**{best['target_model']}**: actual +{o.get('actual_security_gain')} "
                               f"security points (predicted +{o.get('predicted_security_gain')}).",
                        sources=[Source(id="rec-accuracy", title="Recommendation history (local)")],
                        suggestions=["Why did recommendation accuracy decrease?"],
                    )
            return AskResponse(
                answer=f"Across {summ['count']} completed recommendation(s), mean accuracy is "
                       f"{summ['mean_accuracy']}. Accuracy drops when actual improvement diverges from "
                       f"the prediction — usually because data quality or training dynamics differed "
                       f"from what the heuristic assumed.",
                sources=[Source(id="rec-accuracy", title="Recommendation history (local)")],
                suggestions=["Which recommendation produced the biggest improvement?"],
            )

    # "Which benchmark matters most?" — explain the dimensions (no data needed).
    if "benchmark" in ql and ("matter" in ql or "most important" in ql or "should i care" in ql):
        return AskResponse(
            answer="It depends on your goal. **Security** matters most if the model is "
                   "exposed to untrusted input. **Performance** (latency, tokens/sec) matters "
                   "for interactive or high-volume use. **Reasoning** and **Instruction "
                   "Following** matter for task accuracy. RedForge weights all measured suites "
                   "equally into the overall score, but rank by the suite that reflects your "
                   "deployment risk.",
            sources=[Source(id="benchmark-center", title="Benchmark Center (local)")],
            suggestions=["Which model is fastest?", "Which checkpoint performs best?"],
        )

    # Benchmark questions answered from local Benchmark Center results.
    bench = await _benchmark_answer(req.question, req.project_id)
    if bench:
        return AskResponse(
            answer=bench,
            sources=[Source(id="benchmark-center", title="Benchmark Center (local)")],
            suggestions=[
                "Which model is fastest?",
                "Why did latency increase?",
                "Should I deploy the best checkpoint?",
            ],
        )

    # Training-run-scoped questions answered from local run metadata.
    if req.run_id:
        # Security-evolution questions first (Continuous Security timeline).
        sec = await _security_evolution_answer(req.run_id, req.question)
        if sec:
            return AskResponse(
                answer=sec,
                sources=[Source(id="continuous-security", title="Security timeline (local)")],
                suggestions=[
                    "Why did my security score decrease?",
                    "Which attacks improved?",
                    "Should I continue training?",
                ],
            )
        t_answer = await _training_answer(db, req.run_id, req.question)
        if t_answer:
            return AskResponse(
                answer=t_answer,
                sources=[Source(id="training", title="Training run (local)")],
                suggestions=[
                    "Why is loss increasing?",
                    "Should I reduce the learning rate?",
                    "Explain rank and alpha.",
                ],
            )

    # Dataset-scoped questions are answered from local dataset metadata.
    if req.dataset_id:
        ds_answer = await _dataset_answer(db, req.dataset_id, req.question)
        if ds_answer:
            return AskResponse(
                answer=ds_answer,
                sources=[Source(id="dataset", title="Dataset analysis (local)")],
                suggestions=[
                    "How many duplicates exist?",
                    "Why is quality low?",
                    "Is this dataset suitable for instruction tuning?",
                ],
            )

    hits = _retrieve(req.question)
    if not hits:
        return AskResponse(
            answer="I don't have a local answer for that yet. Try `redforge doctor`, the "
                   "Runtime page, or the docs. (A retrieval-augmented assistant is planned.)",
            sources=[],
            suggestions=_SUGGESTIONS,
        )
    answer = "\n\n".join(f"**{h['title']}**\n{h['body']}" for h in hits)
    return AskResponse(
        answer=answer,
        sources=[Source(id=h["id"], title=h["title"]) for h in hits],
        suggestions=_SUGGESTIONS,
    )
