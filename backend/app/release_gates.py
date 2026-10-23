"""Evidence-only release decisions. Never deploys or changes runtime configuration."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.db.models import (BenchmarkResult, EvaluationResult, ReleaseGatePolicy,
                           SecurityCandidateRun, SecurityCandidateVersion, TraceEvent,
                           WorkbenchSession)


class GateRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_evidence_age_hours: int = Field(ge=1, le=8760)
    missing_evidence: str = Field(pattern="^(fail|inconclusive)$")
    require_evaluation: bool = False
    min_quality_score: float | None = Field(default=None, ge=0, le=100)
    required_security_categories: list[str] = Field(default_factory=list, max_length=8)
    max_critical_findings: int | None = Field(default=None, ge=0, le=1000)
    max_error_rate: float | None = Field(default=None, ge=0, le=1)
    max_latency_p95_ms: float | None = Field(default=None, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)
    min_trace_samples: int | None = Field(default=None, ge=1, le=100000)
    require_approval: bool = False

    @model_validator(mode="after")
    def validate_dependencies(self):
        if not any((self.require_evaluation, self.min_quality_score is not None,
                    self.required_security_categories, self.max_critical_findings is not None,
                    self.max_error_rate is not None, self.max_latency_p95_ms is not None,
                    self.max_cost_usd is not None, self.require_approval)):
            raise ValueError("At least one explicit check is required")
        if any(x is not None for x in (self.max_error_rate, self.max_latency_p95_ms,
                                       self.max_cost_usd)) and self.min_trace_samples is None:
            raise ValueError("Trace checks require explicit min_trace_samples")
        allowed = {"PROMPT_INJECTION", "JAILBREAK", "CONTEXT_MANIPULATION", "DATA_LEAKAGE"}
        if len(set(self.required_security_categories)) != len(self.required_security_categories) or any(x not in allowed for x in self.required_security_categories):
            raise ValueError("Unsupported or duplicate security category")
        return self


class CandidateIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_type: str = Field(pattern="^(model|prompt|configuration|application)$")
    artifact_id: str = Field(min_length=1, max_length=128)
    artifact_version: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=200)
    provider: str = Field(min_length=1, max_length=80)
    prompt_version_id: str | None = Field(default=None, max_length=128)
    dataset_version: int | None = Field(default=None, ge=1)


class EvidenceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_session_ids: list[str] = Field(default_factory=list, max_length=20)
    benchmark_result_ids: list[str] = Field(default_factory=list, max_length=20)
    security_run_ids: list[str] = Field(default_factory=list, max_length=50)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]


def _candidate_tag(candidate: CandidateIdentity) -> dict:
    return {"artifact_type": candidate.artifact_type,
            "artifact_id": candidate.artifact_id,
            "artifact_version": candidate.artifact_version}


def _matching_tag(config: dict | None, candidate: CandidateIdentity) -> bool:
    value = (config or {}).get("release_candidate")
    return isinstance(value, dict) and all(value.get(k) == v for k, v in _candidate_tag(candidate).items())


async def evaluate_gate(db, *, project_id: str, policy: ReleaseGatePolicy,
                        candidate: CandidateIdentity, evidence: EvidenceSelection,
                        baseline: CandidateIdentity | None = None,
                        now: datetime | None = None) -> dict:
    """Read bounded, project-scoped evidence; missing/stale/mismatched never passes."""
    rules = GateRules.model_validate(policy.rules)
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=rules.max_evidence_age_hours)
    checks: list[dict] = []
    accepted: dict[str, list[str]] = {"evaluation_session_ids": [], "benchmark_result_ids": [],
                                     "security_run_ids": []}

    def check(name: str, status: str, reason: str, observed=None, threshold=None):
        checks.append({"name": name, "status": status, "reason": reason,
                       "observed": observed, "threshold": threshold})

    def missing(name: str, reason: str):
        check(name, rules.missing_evidence, reason)

    evaluation_results = []
    session_ids = list(dict.fromkeys(evidence.evaluation_session_ids))
    session_rows = (await db.execute(select(WorkbenchSession).where(
        WorkbenchSession.id.in_(session_ids),
        WorkbenchSession.project_id == project_id))).scalars().all() if session_ids else []
    valid_sessions = []
    for session in session_rows:
        if (session is None or session.status != "completed" or
                not _aware(session.completed_at) or _aware(session.completed_at) < cutoff or
                not _matching_tag(session.config, candidate) or
                candidate.dataset_version is not None and
                (session.config or {}).get("dataset_version") != candidate.dataset_version):
            continue
        valid_sessions.append(session)
    if valid_sessions:
        result_rows = (await db.execute(select(EvaluationResult).where(
            EvaluationResult.session_id.in_([session.id for session in valid_sessions]),
            EvaluationResult.target_model == candidate.model,
            EvaluationResult.provider == candidate.provider))).scalars().all()
    else:
        result_rows = []
    for session in valid_sessions:
        rows = [row for row in result_rows if row.session_id == session.id]
        if candidate.prompt_version_id is not None:
            rows = [r for r in rows if str(r.prompt_version) == candidate.prompt_version_id]
        if not rows:
            continue
        accepted["evaluation_session_ids"].append(session.id)
        evaluation_results.extend(rows)

    if rules.require_evaluation:
        if evaluation_results and all(r.verdict not in {"none", "error"} for r in evaluation_results):
            check("evaluation_complete", "pass", "Completed candidate-matched results",
                  observed=len(evaluation_results))
        else:
            missing("evaluation_complete", "No complete, current candidate-matched evaluation")
    if rules.min_quality_score is not None:
        scores = [r.similarity_score for r in evaluation_results if r.similarity_score is not None
                  and r.verdict not in {"none", "error"}
                  and r.baseline_type in {"expected", "golden"}]
        methods = {session.similarity for session in valid_sessions
                   if session.id in accepted["evaluation_session_ids"]}
        baselines = {r.baseline_type for r in evaluation_results if r.similarity_score is not None}
        if not scores or len(scores) != len(evaluation_results) or len(methods) != 1 or len(baselines) != 1:
            missing("quality", "Quality scores need complete, same-method, same-baseline evaluations")
        else:
            score = round(mean(scores), 3)
            check("quality", "pass" if score >= rules.min_quality_score else "fail",
                  "Mean of valid Workbench similarity scores", score, rules.min_quality_score)

    benchmarks = []
    benchmark_ids = list(dict.fromkeys(evidence.benchmark_result_ids))
    benchmark_rows = (await db.execute(select(BenchmarkResult).where(
        BenchmarkResult.id.in_(benchmark_ids),
        BenchmarkResult.project_id == project_id))).scalars().all() if benchmark_ids else []
    for row in benchmark_rows:
        if (row and row.status == "completed" and _aware(row.completed_at) and
                _aware(row.completed_at) >= cutoff and row.target_model == candidate.model and
                row.provider == candidate.provider and _matching_tag(row.config, candidate)):
            accepted["benchmark_result_ids"].append(row.id)
            benchmarks.append(row)

    security_runs = []
    security_ids = list(dict.fromkeys(evidence.security_run_ids))
    security_rows = (await db.execute(select(SecurityCandidateRun, SecurityCandidateVersion).join(
        SecurityCandidateVersion,
        SecurityCandidateRun.candidate_version_id == SecurityCandidateVersion.id).where(
        SecurityCandidateRun.id.in_(security_ids),
        SecurityCandidateRun.project_id == project_id,
        SecurityCandidateVersion.project_id == project_id))).all() if security_ids else []
    for row, version in security_rows:
        if (row is None or row.status != "completed" or not _aware(row.completed_at) or
                _aware(row.completed_at) < cutoff or row.model != candidate.model or
                row.provider != candidate.provider or not _matching_tag(row.config, candidate)):
            continue
        if version is None or (candidate.prompt_version_id is not None and
                               version.snapshot.get("prompt_version_id") != candidate.prompt_version_id):
            continue
        accepted["security_run_ids"].append(row.id)
        security_runs.append((row, version))

    if rules.required_security_categories:
        tested = {version.snapshot.get("category") for _, version in security_runs}
        omitted = sorted(set(rules.required_security_categories) - tested)
        if omitted:
            missing("security_suites", f"Missing candidate-matched categories: {', '.join(omitted)}")
        else:
            check("security_suites", "pass", "Required categories executed",
                  observed=sorted(tested), threshold=rules.required_security_categories)
    if rules.max_critical_findings is not None:
        if not security_runs:
            missing("critical_findings", "No candidate-matched security results")
        else:
            critical = sum(row.classification == "confirmed" and row.severity == "critical"
                           for row, _ in security_runs)
            unreviewed = sum(row.outcome == "detected" and row.classification == "observed"
                             for row, _ in security_runs)
            status = ("fail" if critical > rules.max_critical_findings else
                      "warning" if unreviewed else "pass")
            check("critical_findings", status,
                  "Unreviewed detected behavior never counts as confirmed exploitability",
                  observed={"confirmed_critical": critical, "unreviewed_detections": unreviewed},
                  threshold=rules.max_critical_findings)

    trace_ids: list[int] = []
    if any(x is not None for x in (rules.max_error_rate, rules.max_latency_p95_ms,
                                   rules.max_cost_usd)):
        # Trace metrics are valid only for application releases carrying this
        # exact application version. Other artifact types lack a trustworthy
        # revision link in Phase 1 traces and therefore remain inconclusive.
        traces = []
        if candidate.artifact_type == "application":
            traces = (await db.execute(select(TraceEvent).where(
                TraceEvent.project_id == project_id,
                TraceEvent.application_version == candidate.artifact_version,
                TraceEvent.model == candidate.model,
                TraceEvent.provider == candidate.provider,
                TraceEvent.received_at >= cutoff)
                .order_by(TraceEvent.received_at.desc()).limit(5001))).scalars().all()
        capped = len(traces) > 5000
        if not capped:
            trace_ids = [trace.id for trace in traces[:100]]
        sufficient = not capped and len(traces) >= rules.min_trace_samples
        absent_reason = ("Trace window exceeds the bounded 5,000-row cap" if capped else
                         "Insufficient version-matched trace samples")
        if rules.max_error_rate is not None:
            if not sufficient:
                missing("error_rate", absent_reason)
            else:
                rate = sum(t.status == "error" for t in traces) / len(traces)
                check("error_rate", "pass" if rate <= rules.max_error_rate else "fail",
                      "Observed error fraction", round(rate, 6), rules.max_error_rate)
        if rules.max_latency_p95_ms is not None:
            durations = [t.duration_ms for t in traces if t.duration_ms is not None]
            if not sufficient or len(durations) < rules.min_trace_samples:
                missing("latency_p95", absent_reason if not sufficient else "Insufficient measured latency samples")
            else:
                p95 = _p95(durations)
                check("latency_p95", "pass" if p95 <= rules.max_latency_p95_ms else "fail",
                      "Observed p95 latency in milliseconds", p95, rules.max_latency_p95_ms)
        if rules.max_cost_usd is not None:
            priced = [t for t in traces if t.cost_usd is not None and t.cost_source]
            if not sufficient or len(priced) < rules.min_trace_samples:
                missing("cost", absent_reason if not sufficient else "Insufficient provider/estimated cost samples")
            else:
                total = round(sum(t.cost_usd for t in priced), 6)
                estimated = sum(t.cost_source == "estimated" for t in priced)
                status = ("fail" if total > rules.max_cost_usd else
                          "warning" if estimated else "pass")
                check("cost", status, "Measured window cost; estimated samples prevent an unqualified pass",
                      {"total_usd": total, "estimated_samples": estimated,
                       "provider_samples": len(priced) - estimated}, rules.max_cost_usd)

    if rules.require_approval:
        missing("approval", "No release approval attached; use explicit audited override")

    statuses = {entry["status"] for entry in checks}
    outcome = ("fail" if "fail" in statuses else
               "inconclusive" if "inconclusive" in statuses else
               "warning" if "warning" in statuses else "pass")
    return {"outcome": outcome, "checks": checks,
            "accepted_evidence_ids": {**accepted, "trace_event_ids": trace_ids},
            "rejected_evidence_ids": {
                key: sorted(set(getattr(evidence, key)) - set(accepted[key]))
                for key in accepted},
            "candidate": candidate.model_dump(),
            "baseline": baseline.model_dump() if baseline else None,
            "policy_version": policy.version,
            "executed_at": now.isoformat(),
            "benchmark_results_considered": len(benchmarks)}
