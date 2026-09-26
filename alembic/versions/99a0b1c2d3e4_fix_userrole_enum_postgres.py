"""fix_userrole_enum_postgres

Revision ID: 99a0b1c2d3e4
Revises: 88b9c0d1e2f3
Create Date: 2026-09-26 14:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "99a0b1c2d3e4"
down_revision: str | None = "88b9c0d1e2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE users ALTER COLUMN role TYPE text")
        op.execute("UPDATE users SET role = LOWER(role)")
        op.execute("DROP TYPE userrole")
        op.execute("CREATE TYPE userrole AS ENUM ('admin', 'technician', 'user', 'observer')")
        op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE users ALTER COLUMN role TYPE text")
        op.execute("UPDATE users SET role = UPPER(role)")
        op.execute("DROP TYPE userrole")
        op.execute("CREATE TYPE userrole AS ENUM ('ADMIN', 'TECHNICIAN', 'USER', 'OBSERVER')")
        op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::userrole")
