"""add analysis filter indexes

Revision ID: 7f2b0019f51a
Revises: 138813db0d60
Create Date: 2026-08-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f2b0019f51a"
down_revision: str | Sequence[str] | None = "138813db0d60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = (
    (
        "ix_recommendation_analysis_filters",
        "fact_recommendation",
        ["recommended_at", "source", "model_version_id", "recruiter_id", "job_id"],
    ),
    (
        "ix_funnel_event_analysis_lookup",
        "fact_funnel_event",
        ["recommendation_id", "stage", "status", "event_at"],
    ),
    (
        "ix_daily_funnel_analysis_filters",
        "mart_daily_funnel",
        ["metric_date", "source", "job_category", "region", "metric_version"],
    ),
)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgresql():
        with op.get_context().autocommit_block():
            for name, table, columns in INDEXES:
                op.create_index(
                    name,
                    table,
                    columns,
                    unique=False,
                    postgresql_concurrently=True,
                )
        return
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    if _is_postgresql():
        with op.get_context().autocommit_block():
            for name, table, _ in reversed(INDEXES):
                op.drop_index(
                    name,
                    table_name=table,
                    postgresql_concurrently=True,
                )
        return
    for name, table, _ in reversed(INDEXES):
        op.drop_index(name, table_name=table)
