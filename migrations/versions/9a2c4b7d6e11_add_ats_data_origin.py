"""track the origin of raw ATS facts

Revision ID: 9a2c4b7d6e11
Revises: 7f2b0019f51a
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a2c4b7d6e11"
down_revision: str | Sequence[str] | None = "7f2b0019f51a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fact_recommendation",
        sa.Column("data_origin", sa.String(length=32), nullable=False, server_default="synthetic"),
    )
    op.add_column(
        "fact_funnel_event",
        sa.Column("data_origin", sa.String(length=32), nullable=False, server_default="synthetic"),
    )
    op.create_index("ix_recommendation_data_origin", "fact_recommendation", ["data_origin"])
    op.create_index("ix_funnel_event_data_origin", "fact_funnel_event", ["data_origin"])


def downgrade() -> None:
    op.drop_index("ix_funnel_event_data_origin", table_name="fact_funnel_event")
    op.drop_index("ix_recommendation_data_origin", table_name="fact_recommendation")
    op.drop_column("fact_funnel_event", "data_origin")
    op.drop_column("fact_recommendation", "data_origin")
