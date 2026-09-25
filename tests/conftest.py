"""Global Pytest fixtures for unit, integration, and E2E tests."""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.providers import LocalAuthProvider
from app.core.database import Base, get_db
from app.main import app
from app.models.models import User, UserRole

TEST_DB_URL = "sqlite:///./test_global.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_global.db"):
        os.remove("./test_global.db")


@pytest.fixture
def db_session(setup_db):
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session):
    provider = LocalAuthProvider()
    user = User(
        username="admin_global",
        email_or_login="admin@cfms.local",
        password_hash=provider.hash_password("admin123"),
        role=UserRole.ADMIN,
        locale="ru",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def regular_user(db_session):
    user = User(
        username="user_global",
        email_or_login="user@cfms.local",
        role=UserRole.USER,
        locale="ru",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def tech_user(db_session):
    provider = LocalAuthProvider()
    user = User(
        username="tech_global",
        email_or_login="tech@cfms.local",
        password_hash=provider.hash_password("tech123"),
        role=UserRole.TECHNICIAN,
        locale="ru",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def observer_user(db_session):
    provider = LocalAuthProvider()
    user = User(
        username="obs_global",
        email_or_login="obs@cfms.local",
        password_hash=provider.hash_password("obs123"),
        role=UserRole.OBSERVER,
        locale="ru",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
