"""seed default admin user

Revision ID: 63a1b2c4d5e6
Revises: 52f9a72b834e
Create Date: 2026-09-21 23:00:00.000000

"""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from alembic import op
from app.auth.providers import LocalAuthProvider
from app.models.models import User, UserRole

# revision identifiers, used by Alembic.
revision: str = "63a1b2c4d5e6"
down_revision: str | None = "52f9a72b834e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    existing_admin = session.query(User).filter(User.username == "admin").first()
    if not existing_admin:
        hashed_password = LocalAuthProvider.hash_password("admin123")
        admin_user = User(
            username="admin",
            email_or_login="admin@cfms.local",
            password_hash=hashed_password,
            role=UserRole.ADMIN,
            locale="ru",
            is_active=True,
        )
        session.add(admin_user)
        session.flush()
        session.commit()


def downgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)
    existing_admin = session.query(User).filter(User.username == "admin").first()
    if existing_admin:
        session.delete(existing_admin)
        session.flush()
        session.commit()
