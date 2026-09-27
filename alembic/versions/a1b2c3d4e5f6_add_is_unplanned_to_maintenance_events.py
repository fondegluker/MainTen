"""add is_unplanned column to maintenance_events

Revision ID: a1b2c3d4e5f6
Revises: 99a0b1c2d3e4
Create Date: 2026-09-26 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "99a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("maintenance_events")]
    if "is_unplanned" not in columns:
        op.add_column(
            "maintenance_events",
            sa.Column("is_unplanned", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("maintenance_events")]
    if "is_unplanned" in columns:
        op.drop_column("maintenance_events", "is_unplanned")
