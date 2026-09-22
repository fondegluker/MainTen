"""seed default admin user

Revision ID: 63a1b2c4d5e6
Revises: 52f9a72b834e
Create Date: 2026-09-21 23:00:00.000000

"""
from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
from passlib.context import CryptContext

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '63a1b2c4d5e6'
down_revision: str | None = '52f9a72b834e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

pwd_context = CryptContext(schemes=["argon2", "bcrypt"], deprecated="auto")

def upgrade() -> None:
    users_table = sa.table(
        'users',
        sa.column('id', sa.Integer),
        sa.column('username', sa.String),
        sa.column('email_or_login', sa.String),
        sa.column('password_hash', sa.String),
        sa.column('role', sa.String),
        sa.column('locale', sa.String),
        sa.column('is_active', sa.Boolean),
        sa.column('created_at', sa.DateTime),
    )

    hashed_password = pwd_context.hash("admin123")

    op.bulk_insert(
        users_table,
        [
            {
                'username': 'admin',
                'email_or_login': 'admin@cfms.local',
                'password_hash': hashed_password,
                'role': 'ADMIN',
                'locale': 'ru',
                'is_active': True,
                'created_at': datetime.now(timezone.utc),
            }
        ]
    )

def downgrade() -> None:
    op.execute("DELETE FROM users WHERE username = 'admin'")
