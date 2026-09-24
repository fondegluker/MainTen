"""add short_day kind and source column to working_calendar

Revision ID: 88b9c0d1e2f3
Revises: 77a8b9c0d1e2
Create Date: 2026-09-23 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "88b9c0d1e2f3"
down_revision: str | None = "77a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE daykind ADD VALUE IF NOT EXISTS 'short_day'")

    # Add source column to working_calendar if it does not exist
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("working_calendar")]
    if "source" not in columns:
        op.add_column(
            "working_calendar",
            sa.Column("source", sa.String(length=50), nullable=False, server_default="seed"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("working_calendar")]
    if "source" in columns:
        op.drop_column("working_calendar", "source")
