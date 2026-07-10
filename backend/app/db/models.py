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
