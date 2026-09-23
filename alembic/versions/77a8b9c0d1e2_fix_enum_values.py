"""fix_enum_values_in_initial_schema

Revision ID: 77a8b9c0d1e2
Revises: 63a1b2c4d5e6
Create Date: 2026-09-22 19:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "77a8b9c0d1e2"
down_revision: str | None = "63a1b2c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Update any uppercase enum values in maintenance_events status column if created in Postgres
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE maintenanceeventstatus RENAME TO maintenanceeventstatus_old")
        op.execute(
            "CREATE TYPE maintenanceeventstatus AS ENUM ('planned', 'in_progress', 'done', 'missed', 'cancelled')"
        )
        op.execute(
            "ALTER TABLE maintenance_events ALTER COLUMN status TYPE maintenanceeventstatus "
            "USING status::text::maintenanceeventstatus"
        )
        op.execute("DROP TYPE maintenanceeventstatus_old")


def downgrade() -> None:
    pass
