from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.database import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC now (replaces the deprecated naive datetime.utcnow).

    Matches the aware timestamps the app already writes explicitly elsewhere; the
    stored/read SQLite value is unchanged.
    """
    return datetime.now(timezone.utc)


class ModelRecord(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), unique=True, nullable=False)
    provider = Column(String(100))
    version = Column(String(50))
    last_seen = Column(DateTime, default=_utcnow)


class Attack(Base):
    __tablename__ = "attacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)  # PROMPT_INJECTION/JAILBREAK/CONTEXT_MANIPULATION/DATA_LEAKAGE
    prompt = Column(Text, nullable=False)
    description = Column(Text)
    severity = Column(String(20), nullable=False)  # low/medium/high/critical

    test_runs = relationship("TestRun", back_populates="attack")


class TestRun(Base):
    __tablename__ = "test_runs"
    __test__ = False  # ORM model, not a pytest test class (silences collection warning)

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(200), nullable=False)
    attack_id = Column(Integer, ForeignKey("attacks.id"))
    prompt_sent = Column(Text)
    model_response = Column(Text)
    score = Column(Float)
    verdict = Column(String(20))  # PASS/FAIL/UNCERTAIN
    reason = Column(String(500))
    latency_ms = Column(Integer)
    timestamp = Column(DateTime, default=_utcnow)

    attack = relationship("Attack", back_populates="test_runs")


class Project(Base):
    """AI Studio workspace (V2). Groups models, evaluations, reports, and settings
    under one named project. Local-only; no cloud sync. Additive — nothing in v1.2
    depends on it, and existing tables are untouched."""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)  # uuid4 hex-with-dashes
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    # Provider-agnostic references, stored as JSON so the workspace stays flexible
    # without new join tables in Phase 1.
    models = Column(JSON, default=list)         # list[str] model names
    datasets = Column(JSON, default=list)       # list — placeholder for Phase 2 (Dataset Lab)
    settings = Column(JSON, default=dict)       # dict — per-project preferences
    last_scan = Column(JSON, nullable=True)     # dict — cached summary of the latest evaluation
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    opened_at = Column(DateTime, default=_utcnow)  # bumped on open → drives "Recent Projects"


class Dataset(Base):
    """Dataset Lab asset (V2 Phase 2). A named, versioned collection of records
    attached to a Project. Local-only — content lives in SQLite as JSON, never in
    the cloud. Additive: nothing in v1.2 / Phase 1 depends on it."""

    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True)  # uuid4
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    source_format = Column(String(20), default="json")  # csv/json/jsonl/txt/md/pdf/docx
    kind = Column(String(20), default="records")         # "records" | "text"
    columns = Column(JSON, default=list)                 # list[str] for tabular kinds
    record_count = Column(Integer, default=0)
    byte_size = Column(Integer, default=0)
    current_version = Column(Integer, default=1)
    dataset_metadata = Column(JSON, default=dict)        # cached stats/quality summary
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    versions = relationship(
        "DatasetVersion", back_populates="dataset",
        cascade="all, delete-orphan", order_by="DatasetVersion.version",
    )


class DatasetVersion(Base):
    """Immutable snapshot of a dataset's records. Every save creates a new version;
    restore copies an old snapshot forward. Nothing overwrites data permanently."""

    __tablename__ = "dataset_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    records = Column(JSON, nullable=False)      # list[dict] | list[str]
    record_count = Column(Integer, default=0)
    note = Column(String(300), default="")       # what changed (e.g. "removed 12 duplicates")
    created_at = Column(DateTime, default=_utcnow)

    dataset = relationship("Dataset", back_populates="versions")


class TrainingRun(Base):
    """Training Lab run (V2 Phase 2.2) — a first-class, versioned fine-tuning job.

    Isolated from the Runtime Manager / Security Center; local-only. Additive:
    nothing in v1.2 / AI Studio / Dataset Lab depends on it."""

    __tablename__ = "training_runs"

    id = Column(String(36), primary_key=True)  # uuid4
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    base_model = Column(String(200), nullable=False)
    dataset_id = Column(String(36), ForeignKey("datasets.id"), nullable=True)
    method = Column(String(20), default="lora")        # lora | qlora
    backend = Column(String(30), default="simulation")  # training provider used
    config = Column(JSON, default=dict)                 # full training config
    status = Column(String(20), default="pending")      # pending/running/paused/completed/failed/cancelled
    metrics = Column(JSON, default=dict)                # final metrics summary
    output_dir = Column(String(500), default="")
    notes = Column(Text, default="")
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    checkpoints = relationship(
        "Checkpoint", back_populates="run",
        cascade="all, delete-orphan", order_by="Checkpoint.step",
    )


class Checkpoint(Base):
    """A saved point in a training run. Local files/metadata only."""

    __tablename__ = "checkpoints"

    id = Column(String(36), primary_key=True)  # uuid4
    run_id = Column(String(36), ForeignKey("training_runs.id"), nullable=False, index=True)
    step = Column(Integer, nullable=False)
    epoch = Column(Float, default=0.0)
    loss = Column(Float, nullable=True)
    val_loss = Column(Float, nullable=True)
    path = Column(String(500), default="")     # local checkpoint dir (never uploaded)
    is_best = Column(Integer, default=0)        # 0/1
    note = Column(String(300), default="")
    created_at = Column(DateTime, default=_utcnow)

    run = relationship("TrainingRun", back_populates="checkpoints")


class CheckpointSecurity(Base):
    """Continuous Security (V2 Phase 2.3) — a security evaluation attached to a
    training checkpoint. Orchestration only; the evaluation itself reuses the
    existing Security Center engine. Local-only, additive."""

    __tablename__ = "checkpoint_security"

    id = Column(String(36), primary_key=True)  # uuid4
    run_id = Column(String(36), ForeignKey("training_runs.id"), nullable=False, index=True)
    checkpoint_id = Column(String(36), ForeignKey("checkpoints.id"), nullable=True)
    step = Column(Integer, nullable=False)
    target_model = Column(String(200), nullable=False)   # what was actually evaluated
    profile = Column(String(40), default="quick")         # quick/standard/full/custom
    status = Column(String(20), default="pending")        # pending/running/completed/failed/cancelled
    score = Column(Float, nullable=True)                   # overall security score 0–100
    categories = Column(JSON, default=list)               # [{category, score, fail_rate, risk_level}]
    findings = Column(JSON, default=list)                 # top vulnerabilities (compact)
    session_id = Column(String(36), nullable=True)        # link to the reused evaluation session
    # Runtime Registry linkage (Phase 2.5): which runnable model was evaluated —
    # a registered checkpoint adapter, or the base-model fallback.
    runtime_id = Column(String(80), nullable=True)        # registered_models.id
    provider = Column(String(40), nullable=True)
    error = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)


class RegisteredModel(Base):
    """Runtime Registry (V2 Phase 2.5) — a checkpoint made runnable through the
    Runtime Manager, so Playground / Security Center can use it like any model.

    Provider-agnostic: ``runtime_model`` is the name the runtime resolves to. When
    a provider can host the adapter it points at the real checkpoint model; when it
    cannot (or the simulation backend produced no adapter files) it falls back to
    the base model (``fallback=1``) with all identity/metadata stored for
    reproducibility. Additive; never breaks training."""

    __tablename__ = "registered_models"

    id = Column(String(80), primary_key=True)  # e.g. "ckpt-<run8>-step-<n>"
    run_id = Column(String(36), ForeignKey("training_runs.id"), nullable=True, index=True)
    checkpoint_id = Column(String(36), ForeignKey("checkpoints.id"), nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    label = Column(String(120), nullable=False)           # e.g. "Checkpoint 4 (step 40)"
    step = Column(Integer, nullable=True)
    base_model = Column(String(200), nullable=False)
    provider = Column(String(40), nullable=False)
    runtime_model = Column(String(200), nullable=False)   # what the runtime actually runs
    adapter_path = Column(String(500), nullable=True)
    fallback = Column(Integer, default=0)                 # 1 → resolved to base model
    status = Column(String(20), default="registered")     # registered/failed/unregistered
    model_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)


class Recommendation(Base):
    """Recommendation Engine output (V2 Phase 2.4) — how to improve a model after
    a weakness is found. Isolated: derived from existing security/training/dataset
    metadata, never a new evaluator/trainer. Stores accept/reject history so
    recommendation quality can be compared later. Local-only, additive."""

    __tablename__ = "recommendations"

    id = Column(String(36), primary_key=True)  # uuid4
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    run_id = Column(String(36), ForeignKey("training_runs.id"), nullable=True, index=True)
    target_model = Column(String(200), nullable=False)
    source = Column(String(40), default="security")   # what triggered it
    status = Column(String(20), default="proposed")    # proposed/accepted/rejected/applied
    # Full recommendation payload: weaknesses, strategy, hyperparameters, datasets,
    # attacks, prediction, rationale (see app.recommendations.engine).
    payload = Column(JSON, default=dict)
    outcome = Column(JSON, nullable=True)              # linked training outcome, if applied
    created_at = Column(DateTime, default=_utcnow)
    decided_at = Column(DateTime, nullable=True)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(200), nullable=False)
    report_data = Column(JSON, nullable=False)
    generated_at = Column(DateTime, default=_utcnow)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    model_list = Column(JSON, nullable=False)   # list[str]
    attack_suite = Column(JSON, nullable=False)  # list[int] attack IDs
    status = Column(String(30), nullable=False, default="pending")  # pending/running/completed/failed
    created_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    model_scores = relationship("ModelScore", back_populates="benchmark_run", cascade="all, delete-orphan")


class ModelScore(Base):
    __tablename__ = "model_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    benchmark_run_id = Column(Integer, ForeignKey("benchmark_runs.id"), nullable=False)
    model_name = Column(String(200), nullable=False)
    injection_rate = Column(Float, default=0.0)
    jailbreak_rate = Column(Float, default=0.0)
    hallucination_rate = Column(Float, default=0.0)
    data_leakage_rate = Column(Float, default=0.0)
    avg_latency_ms = Column(Float, default=0.0)
    overall_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=_utcnow)

    benchmark_run = relationship("BenchmarkRun", back_populates="model_scores")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(200), nullable=False)
    target_category = Column(String(50), nullable=True)
    max_rounds = Column(Integer, default=8)
    max_total_tokens = Column(Integer, default=20000)
    wall_clock_timeout_s = Column(Integer, default=120)
    status = Column(String(30), nullable=False, default="pending")
    # compromised / rounds_exhausted / token_budget_exceeded / timeout / strategies_exhausted
    outcome = Column(String(30), nullable=True)
    rounds_completed = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)

    findings = relationship("AgentFinding", back_populates="agent_run", cascade="all, delete-orphan")


class AgentFinding(Base):
    __tablename__ = "agent_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_run_id = Column(Integer, ForeignKey("agent_runs.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    attack_prompt = Column(Text, nullable=False)
    model_response = Column(Text)
    verdict = Column(String(20))
    score = Column(Float)
    escalated = Column(Integer, default=0)  # 0/1 — did model resistance trigger escalation?
    strategy = Column(String(50), nullable=True)         # adaptive agent: which strategy was used
    failure_reason = Column(Text, nullable=True)         # judge's reason when model resisted
    escalation_tier = Column(Integer, nullable=True)     # strategy tier (1=simplest, 4=most complex)
    created_at = Column(DateTime, default=_utcnow)

    agent_run = relationship("AgentRun", back_populates="findings")


class EvaluationSession(Base):
    """A durable, resumable evaluation session.

    Unlike the legacy in-memory batch job store, every field here is persisted,
    so a session survives browser refresh, backend restart, and interruption.
    """

    __tablename__ = "evaluation_sessions"

    id = Column(String(36), primary_key=True)  # UUID4 string
    session_type = Column(String(50), nullable=False)  # batch / benchmark / agent / single
    status = Column(String(20), nullable=False, default="pending")
    # pending / running / paused / completed / failed / cancelled
    selected_models = Column(JSON, nullable=False, default=list)      # list[str]
    selected_categories = Column(JSON, nullable=False, default=list)  # list[str]
    selected_tier = Column(String(50), nullable=True)
    total_tasks = Column(Integer, nullable=False, default=0)
    completed_tasks = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_seconds = Column(Float, nullable=True)
    actual_seconds = Column(Float, nullable=True)
    # "metadata" is reserved by SQLAlchemy's Declarative API, so the Python
    # attribute is renamed while the DB column stays "metadata".
    session_metadata = Column("metadata", JSON, nullable=True)

    events = relationship(
        "EvaluationEvent",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="EvaluationEvent.id",
    )


class EvaluationEvent(Base):
    """An append-only record of a significant action within a session.

    This is the backend foundation a future WebSocket feed will replay/stream.
    Events are never mutated after creation.
    """

    __tablename__ = "evaluation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        String(36), ForeignKey("evaluation_sessions.id"), nullable=False, index=True
    )
    timestamp = Column(DateTime, default=_utcnow)
    event_type = Column(String(50), nullable=False)
    # session_created / model_started / attack_started / response_received /
    # verdict_generated / session_completed / session_failed
    model_name = Column(String(200), nullable=True)
    category = Column(String(50), nullable=True)
    attack_name = Column(String(200), nullable=True)
    response_excerpt = Column(Text, nullable=True)
    verdict = Column(String(20), nullable=True)
    latency_ms = Column(Integer, nullable=True)
    event_metadata = Column("metadata", JSON, nullable=True)

    session = relationship("EvaluationSession", back_populates="events")


class DatasetEntry(Base):
    __tablename__ = "dataset_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attack_name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    prompt = Column(Text, nullable=False)
    model_name = Column(String(200), nullable=False)
    model_response = Column(Text)
    ground_truth_verdict = Column(String(20), nullable=False)  # PASS/FAIL/UNCERTAIN
    source = Column(String(50), default="auto")  # auto / manual
    created_at = Column(DateTime, default=_utcnow)


class BenchmarkResult(Base):
    """Benchmark Center (V2 Phase 3) — one model's result across the requested
    benchmark suites (performance, reasoning, security, …), run through an async
    queue that mirrors Continuous Security. Orchestration/results only: suites
    reuse existing engines (Security → Security Center; Performance → Runtime
    Manager). ``registry_id`` links a benchmarked checkpoint back to the Runtime
    Registry so base models, checkpoints, and final models compare on equal terms.
    Local-only, additive; distinct from the legacy ``benchmark_runs`` table."""

    __tablename__ = "benchmark_results"

    id = Column(String(36), primary_key=True)  # uuid4
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    run_id = Column(String(36), ForeignKey("training_runs.id"), nullable=True, index=True)
    registry_id = Column(String(80), nullable=True, index=True)   # registered_models.id
    target_model = Column(String(200), nullable=False)             # what was benchmarked
    provider = Column(String(40), nullable=True)
    runtime = Column(String(40), nullable=True)                    # runtime/label snapshot
    label = Column(String(120), nullable=True)
    suites = Column(JSON, default=list)                            # requested suite keys
    status = Column(String(20), default="pending")                # pending/running/completed/failed/cancelled
    overall_score = Column(Float, nullable=True)                  # mean of per-suite scores (0–100)
    scores = Column(JSON, default=dict)                           # {suite_key: score}
    metrics = Column(JSON, default=dict)                          # {suite_key: {detailed metrics}}
    duration_seconds = Column(Float, nullable=True)
    config = Column(JSON, default=dict)                           # sampling/suite config used
    error = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)
