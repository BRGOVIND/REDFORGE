"""Extend workbench prompts and add project trace governance.

Revision ID: c9d4e7a52b13
Revises: b6a47d2e19f0
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d4e7a52b13"
down_revision = "b6a47d2e19f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.models import (
        EvaluationCollection, EvaluationResult, GovernanceAuditEvent, Prompt,
        PromptSet, PromptVersion, TracePrivacyPolicy, WorkbenchSession,
    )

    bind = op.get_bind()
    # Older desktops used create_all for these tables; a fresh Alembic install
    # has never had them. Both paths must converge before altering columns.
    for model in (EvaluationCollection, PromptSet, Prompt, PromptVersion,
                  WorkbenchSession, EvaluationResult):
        model.__table__.create(bind, checkfirst=True)
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("eval_prompts")}
    for name, kind in (
        ("active_version", sa.Integer()), ("description", sa.Text()),
        ("variables_schema", sa.JSON()), ("draft", sa.JSON()),
        ("author", sa.String(120)), ("archived_at", sa.DateTime()),
    ):
        if name not in columns:
            op.add_column("eval_prompts", sa.Column(name, kind, nullable=True))
    columns = {c["name"] for c in sa.inspect(bind).get_columns("eval_prompt_versions")}
    for name, kind in (("author", sa.String(120)), ("content_hash", sa.String(64))):
        if name not in columns:
            op.add_column("eval_prompt_versions", sa.Column(name, kind, nullable=True))
    bind.execute(sa.text("UPDATE eval_prompts SET active_version = current_version WHERE active_version IS NULL"))
    constraints = {x.get("name") for x in sa.inspect(bind).get_unique_constraints("eval_prompt_versions")}
    indexes = {x.get("name") for x in sa.inspect(bind).get_indexes("eval_prompt_versions")}
    if "uq_eval_prompt_version" not in constraints | indexes:
        bind.execute(sa.text("CREATE UNIQUE INDEX uq_eval_prompt_version ON eval_prompt_versions (prompt_id, version)"))
    TracePrivacyPolicy.__table__.create(bind, checkfirst=True)
    GovernanceAuditEvent.__table__.create(bind, checkfirst=True)
    for index in GovernanceAuditEvent.__table__.indexes:
        index.create(bind, checkfirst=True)


def downgrade() -> None:
    # SQLite cannot safely drop the additive prompt columns on older installations.
    op.drop_table("governance_audit_events")
    op.drop_table("trace_privacy_policies")
    op.execute("DROP INDEX IF EXISTS uq_eval_prompt_version")
