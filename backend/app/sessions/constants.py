"""String constants and small helpers for the evaluation session lifecycle.

These are plain string classes (not ``enum.Enum``) so the values serialize
directly to the ``String`` columns and to JSON without extra coercion, matching
the convention used elsewhere in the codebase (e.g. verdict/status columns).
"""
from __future__ import annotations


class SessionStatus:
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = (PENDING, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED)
    # Statuses from which no further execution happens.
    TERMINAL = (COMPLETED, CANCELLED)
    # Statuses that a resume request may pick up and continue.
    RESUMABLE = (PENDING, RUNNING, PAUSED, FAILED)


class SessionType:
    BATCH = "batch"
    BENCHMARK = "benchmark"
    AGENT = "agent"
    SINGLE = "single"

    ALL = (BATCH, BENCHMARK, AGENT, SINGLE)


class EventType:
    SESSION_CREATED = "session_created"
    MODEL_STARTED = "model_started"
    ATTACK_STARTED = "attack_started"
    RESPONSE_RECEIVED = "response_received"
    VERDICT_GENERATED = "verdict_generated"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"
    # Sprint 3 — adaptive execution and intelligent pipeline events.
    MODEL_PROFILED = "model_profiled"
    PLAN_GENERATED = "plan_generated"
    MUTATION_APPLIED = "mutation_applied"
    ATTACK_RETRIED = "attack_retried"
    ANALYSIS_COMPLETED = "analysis_completed"
    REPORT_GENERATED = "report_generated"
    # Emitted periodically while a single attack waits on a slow model response,
    # so the live terminal never appears frozen.
    HEARTBEAT = "heartbeat"

    ALL = (
        SESSION_CREATED,
        MODEL_STARTED,
        ATTACK_STARTED,
        RESPONSE_RECEIVED,
        VERDICT_GENERATED,
        SESSION_COMPLETED,
        SESSION_FAILED,
        MODEL_PROFILED,
        PLAN_GENERATED,
        MUTATION_APPLIED,
        ATTACK_RETRIED,
        ANALYSIS_COMPLETED,
        REPORT_GENERATED,
        HEARTBEAT,
    )


# How long, on average, a single (model x attack) task is assumed to take.
# Used only to seed ``estimated_seconds`` at creation time.
AVG_TASK_SECONDS = 3.0

# Maximum characters stored in an event's ``response_excerpt``.
RESPONSE_EXCERPT_LEN = 500
