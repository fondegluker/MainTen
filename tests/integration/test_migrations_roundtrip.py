import pytest
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth.providers import LocalAuthProvider
from app.core.config import settings
from app.models.models import User, UserRole


@pytest.fixture
def alembic_config():
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return config


def test_alembic_migrations_roundtrip_and_admin_seed(alembic_config):
    # 1. Upgrade to head
    upgrade(alembic_config, "head")

    # Verify head revision
    script = ScriptDirectory.from_config(alembic_config)
    head_revision = script.get_current_head()

    engine = create_engine(settings.DATABASE_URL)
    with Session(bind=engine) as session:
        admin_user = session.query(User).filter(User.username == "admin").one_or_none()
        assert admin_user is not None, "Admin user was not seeded by migration"
        assert admin_user.role == UserRole.ADMIN
        assert admin_user.username == "admin"
        assert LocalAuthProvider.verify_password("admin123", admin_user.password_hash)

    # 2. Downgrade to base
    downgrade(alembic_config, "base")

    # 3. Upgrade to head again (verifying idempotency and migration clean roundtrip)
    upgrade(alembic_config, "head")

    with Session(bind=engine) as session:
        admin_user = session.query(User).filter(User.username == "admin").one_or_none()
        assert admin_user is not None, "Admin user was not re-seeded cleanly on re-upgrade"
        assert admin_user.role == UserRole.ADMIN
        assert admin_user.username == "admin"
        assert LocalAuthProvider.verify_password("admin123", admin_user.password_hash)
