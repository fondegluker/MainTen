import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.base import AuthCredentials
from app.auth.providers import LocalAuthProvider
from app.core.database import Base
from app.models.models import User, UserRole

TEST_DB_URL = "sqlite:///./test_admin_seed.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module")
def setup_admin_db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    # Seed default admin user
    provider = LocalAuthProvider()
    admin = User(
        username="admin",
        email_or_login="admin@cfms.local",
        password_hash=provider.hash_password("admin123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    session.add(admin)
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_admin_seed.db"):
        os.remove("./test_admin_seed.db")

def test_default_admin_seed(setup_admin_db):
    admin = setup_admin_db.query(User).filter(User.username == "admin").first()
    assert admin is not None
    assert admin.username == "admin"
    assert admin.email_or_login == "admin@cfms.local"
    assert admin.role == UserRole.ADMIN
    assert admin.is_active is True

    # Test authentication with default password
    provider = LocalAuthProvider()
    auth_user = provider.authenticate(setup_admin_db, AuthCredentials("admin", "admin123"))
    assert auth_user is not None
    assert auth_user.id == admin.id
