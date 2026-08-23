"""Assistant orchestration: decide which local source answers a question.

The endpoint used to be a 140-line ladder of ``if`` branches that each repeated
the same shape — try a source, and if it produced prose, wrap it with a
hard-coded citation and a hard-coded set of follow-up suggestions. That made the
answer order, the citations and the follow-ups three things you had to read the
whole ladder to discover.

Here the ladder is data. :data:`_CHAIN` lists the sources in priority order; each
entry owns its own citation and follow-ups, and each answerer decides for itself
whether it can speak (returning ``None`` when it cannot). Resolution is then a
single loop, and adding a source means adding one entry rather than another
branch.

Priority order is load-bearing and matches the original ladder exactly: a
question scoped to a recommendation is answered from that recommendation before
anything else, and the knowledge base is the last resort.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import answerers
from app.assistant.knowledge import _SUGGESTIONS, retrieve


@dataclass(frozen=True)
class AssistantQuery:
    """A question plus the optional local scopes it may be answered from."""

    question: str
    context: Optional[str] = None
    dataset_id: Optional[str] = None
    run_id: Optional[str] = None
    recommendation_id: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None

    @property
    def lowered(self) -> str:
        return self.question.lower()


@dataclass(frozen=True)
class Citation:
    id: str
    title: str


@dataclass(frozen=True)
class Answer:
    """A resolved answer with the source it came from and what to ask next."""

    text: str
    sources: list[Citation] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# An answerer returns prose when it can speak, or None to defer to the next
# source. `_recommendation_quality` is the one source whose follow-ups depend on
# which of its two answers it gave, so it returns a complete Answer instead;
# `answer()` normalises both forms in a single place.
AnswererResult = Optional[Union[str, Answer]]
Answerer = Callable[[AsyncSession, "AssistantQuery"], Awaitable[AnswererResult]]


@dataclass(frozen=True)
class Source:
    """One entry in the answer chain: who to ask, how to cite them, what next."""

    id: str
    title: str
    ask: Answerer
    suggestions: tuple[str, ...] = ()


# -- the sources, in the order they get a chance to answer --------------------

async def _recommendation_scoped(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    if not q.recommendation_id:
        return None
    return await answerers.recommendation_answer(db, q.recommendation_id, q.question)


async def _recommendation_quality(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    """Accuracy history across all recommendations, not one in particular."""
    ql = q.lowered
    if not ("recommendation accuracy" in ql or "biggest improvement" in ql
            or "which recommendation" in ql):
        return None
    from app.recommendations import recommendation_service
    summ = await recommendation_service.accuracy_summary(db)
    if not summ["count"]:
        return None
    cite = [Citation(id="rec-accuracy", title="Recommendation history (local)")]
    best = summ.get("best_recommendation")
    if ("biggest improvement" in ql or "which recommendation" in ql) and best:
        o = best.get("outcome") or {}
        return Answer(
            text=f"The biggest improvement came from the recommendation for "
                 f"**{best['target_model']}**: actual +{o.get('actual_security_gain')} "
                 f"security points (predicted +{o.get('predicted_security_gain')}).",
            sources=cite,
            suggestions=["Why did recommendation accuracy decrease?"],
        )
    return Answer(
        text=f"Across {summ['count']} completed recommendation(s), mean accuracy is "
             f"{summ['mean_accuracy']}. Accuracy drops when actual improvement diverges from "
             f"the prediction — usually because data quality or training dynamics differed "
             f"from what the heuristic assumed.",
        sources=cite,
        suggestions=["Which recommendation produced the biggest improvement?"],
    )


async def _benchmark_priority(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    """Explains which benchmark dimension to care about. Needs no local data."""
    ql = q.lowered
    if not ("benchmark" in ql and ("matter" in ql or "most important" in ql
                                   or "should i care" in ql)):
        return None
    return ("It depends on your goal. **Security** matters most if the model is "
            "exposed to untrusted input. **Performance** (latency, tokens/sec) matters "
            "for interactive or high-volume use. **Reasoning** and **Instruction "
            "Following** matter for task accuracy. RedForge weights all measured suites "
            "equally into the overall score, but rank by the suite that reflects your "
            "deployment risk.")


async def _benchmark_results(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    return await answerers.benchmark_answer(q.question, q.project_id)


async def _evaluation_session(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    if not (q.project_id or q.session_id):
        return None
    return await answerers.evaluation_answer(q.question, q.project_id, q.session_id)


async def _security_evolution(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    if not q.run_id:
        return None
    return await answerers.security_evolution_answer(q.run_id, q.question)


async def _training_run(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    if not q.run_id:
        return None
    return await answerers.training_answer(db, q.run_id, q.question)


async def _dataset_scoped(db: AsyncSession, q: AssistantQuery) -> AnswererResult:
    if not q.dataset_id:
        return None
    return await answerers.dataset_answer(db, q.dataset_id, q.question)


_CHAIN: tuple[Source, ...] = (
    Source(
        id="recommendation", title="Recommendation (local)", ask=_recommendation_scoped,
        suggestions=("Why is this dataset recommended?",
                     "How much improvement should I expect?",
                     "Why this rank and method?"),
    ),
    Source(id="rec-accuracy", title="Recommendation history (local)",
           ask=_recommendation_quality),
    Source(
        id="benchmark-center", title="Benchmark Center (local)", ask=_benchmark_priority,
        suggestions=("Which model is fastest?", "Which checkpoint performs best?"),
    ),
    Source(
        id="benchmark-center", title="Benchmark Center (local)", ask=_benchmark_results,
        suggestions=("Which model is fastest?", "Why did latency increase?",
                     "Should I deploy the best checkpoint?"),
    ),
    Source(
        id="evaluation-workbench", title="Evaluation Workbench (local)",
        ask=_evaluation_session,
        suggestions=("Which prompts failed?",
                     "Which model stayed closest to the baseline?",
                     "Show only safety regressions.", "Should I retrain?"),
    ),
    Source(
        id="continuous-security", title="Security timeline (local)", ask=_security_evolution,
        suggestions=("Why did my security score decrease?", "Which attacks improved?",
                     "Should I continue training?"),
    ),
    Source(
        id="training", title="Training run (local)", ask=_training_run,
        suggestions=("Why is loss increasing?", "Should I reduce the learning rate?",
                     "Explain rank and alpha."),
    ),
    Source(
        id="dataset", title="Dataset analysis (local)", ask=_dataset_scoped,
        suggestions=("How many duplicates exist?", "Why is quality low?",
                     "Is this dataset suitable for instruction tuning?"),
    ),
)


def _knowledge_base_answer(question: str) -> Answer:
    """Last resort: the curated knowledge base, or an honest "I don't know"."""
    hits = retrieve(question)
    if not hits:
        return Answer(
            text="I don't have a local answer for that yet. Try `redforge doctor`, the "
                 "Runtime page, or the docs. (A retrieval-augmented assistant is planned.)",
            sources=[],
            suggestions=list(_SUGGESTIONS),
        )
    return Answer(
        text="\n\n".join(f"**{h['title']}**\n{h['body']}" for h in hits),
        sources=[Citation(id=h["id"], title=h["title"]) for h in hits],
        suggestions=list(_SUGGESTIONS),
    )


async def answer(db: AsyncSession, query: AssistantQuery) -> Answer:
    """First source that can speak wins; the knowledge base backs everyone up."""
    for source in _CHAIN:
        result = await source.ask(db, query)
        if result is None:
            continue
        if isinstance(result, Answer):
            return result
        return Answer(
            text=str(result),
            sources=[Citation(id=source.id, title=source.title)],
            suggestions=list(source.suggestions),
        )
    return _knowledge_base_answer(query.question)
