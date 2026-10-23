"""Add bounded comparison, routing and cost-control records.

Revision ID: c6b7a81d402e
Revises: f5a21d84c903
"""
from alembic import op
import sqlalchemy as sa

revision = "c6b7a81d402e"
down_revision = "f5a21d84c903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.models import ComparisonPlan, ModelPrice, ProjectBudget, RoutingPolicy, RoutingState, TraceEvent

    bind = op.get_bind()
    for model in (ComparisonPlan, RoutingPolicy, RoutingState, ModelPrice, ProjectBudget):
        model.__table__.create(bind, checkfirst=True)
    existing = {column["name"] for column in sa.inspect(bind).get_columns("trace_events")}
    for name, kind in (
        ("cached_input_tokens", sa.Integer()), ("reasoning_tokens", sa.Integer()),
        ("pricing_record_id", sa.String(36)), ("cost_calculated_at", sa.DateTime()),
        ("logical_call_key", sa.String(64)),
    ):
        if name not in existing:
            op.add_column("trace_events", sa.Column(name, kind, nullable=True))
    next(index for index in TraceEvent.__table__.indexes
         if index.name == "ix_trace_events_project_call").create(bind, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("Phase 3 records are auditable history; restore a backup instead")
