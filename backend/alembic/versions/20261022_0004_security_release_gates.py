"""Add reviewed trace security candidates and versioned release gates.

Revision ID: f5a21d84c903
Revises: d7e5a924b610
"""
from alembic import op

revision = "f5a21d84c903"
down_revision = "d7e5a924b610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.models import (
        SecurityCandidate, SecurityCandidateVersion, SecurityCandidateRun,
        ReleaseGatePolicy, ReleaseGateDecision, TraceEvent,
    )
    bind = op.get_bind()
    for model in (SecurityCandidate, SecurityCandidateVersion, SecurityCandidateRun,
                  ReleaseGatePolicy, ReleaseGateDecision):
        model.__table__.create(bind, checkfirst=True)
    next(index for index in TraceEvent.__table__.indexes
         if index.name == "ix_trace_events_release_metrics").create(bind, checkfirst=True)


def downgrade() -> None:
    # Destructive downgrade deliberately unsupported: deleting audit decisions,
    # approved cases, or test results would violate release-history integrity.
    raise RuntimeError("Phase 5 tables contain immutable audit history; restore a backup instead")
