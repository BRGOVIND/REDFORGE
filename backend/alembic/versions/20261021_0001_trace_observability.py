"""Add project trace tokens and observed LLM events.

Revision ID: b6a47d2e19f0
Revises: a1b2c3d4e5f6
"""

from alembic import op

revision = "b6a47d2e19f0"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Desktop startup has historically used create_all before Alembic stamping.
    # Check first so that both upgrade paths preserve existing installations.
    from app.db.models import TraceEvent, TraceToken

    TraceToken.__table__.create(bind, checkfirst=True)
    TraceEvent.__table__.create(bind, checkfirst=True)
    for index in TraceEvent.__table__.indexes:
        index.create(bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("trace_events")
    op.drop_table("trace_tokens")
