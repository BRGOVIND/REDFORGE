"""add_evaluation_session_tables

Revision ID: a1b2c3d4e5f6
Revises: e3f8b1d92c45
Create Date: 2026-07-06 10:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "e3f8b1d92c45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evaluation_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("selected_models", sa.JSON(), nullable=False),
        sa.Column("selected_categories", sa.JSON(), nullable=False),
        sa.Column("selected_tier", sa.String(length=50), nullable=True),
        sa.Column("total_tasks", sa.Integer(), nullable=False),
        sa.Column("completed_tasks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("estimated_seconds", sa.Float(), nullable=True),
        sa.Column("actual_seconds", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "evaluation_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("attack_name", sa.String(length=200), nullable=True),
        sa.Column("response_excerpt", sa.Text(), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["evaluation_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_events_session_id",
        "evaluation_events",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_events_session_id", table_name="evaluation_events")
    op.drop_table("evaluation_events")
    op.drop_table("evaluation_sessions")
