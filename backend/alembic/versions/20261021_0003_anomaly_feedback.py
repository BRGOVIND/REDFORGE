"""Add local anomaly rules, alerts, and trace feedback cases.

Revision ID: d7e5a924b610
Revises: c9d4e7a52b13
"""
from alembic import op
import sqlalchemy as sa

revision = "d7e5a924b610"
down_revision = "c9d4e7a52b13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.models import AnomalyRule, AnomalyAlert, FeedbackCase
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("trace_events")}
    if "timed_out" not in columns:
        op.add_column("trace_events", sa.Column("timed_out", sa.Boolean(), nullable=False, server_default=sa.false()))
    for model in (AnomalyRule, AnomalyAlert, FeedbackCase):
        model.__table__.create(bind, checkfirst=True)
    feedback_columns = {column["name"] for column in sa.inspect(bind).get_columns("feedback_cases")}
    if "source_event_id" not in feedback_columns:
        op.add_column("feedback_cases", sa.Column("source_event_id", sa.String(128)))
        bind.execute(sa.text("UPDATE feedback_cases SET source_event_id = "
            "(SELECT event_id FROM trace_events WHERE trace_events.id = feedback_cases.trace_event_id "
            "AND trace_events.project_id = feedback_cases.project_id)"))


def downgrade() -> None:
    for name in ("feedback_cases", "anomaly_alerts", "anomaly_rules"):
        op.drop_table(name)
