"""Regression tests for Defect 1: /technician/schedule and /reports routes access control."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_defect1.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_defect1.db"):
        os.remove("./test_defect1.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def _create_user(db: Session, username: str, role: UserRole) -> User:
    provider = LocalAuthProvider()
    user = User(
        username=username,
        email_or_login=f"{username}@example.com",
        password_hash=provider.hash_password("password123"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_unauthenticated_redirects(db_session: Session):
    client = TestClient(app, follow_redirects=False)
    # Unauthenticated HTML requests redirect to /auth/login
    res1 = client.get("/technician/schedule", headers={"Accept": "text/html"})
    assert res1.status_code == 302
    assert res1.headers["location"] == "/auth/login"

    res2 = client.get("/reports", headers={"Accept": "text/html"})
    assert res2.status_code == 302
    assert res2.headers["location"] == "/auth/login"


def test_technician_schedule_role_access(db_session: Session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app, follow_redirects=False)

    admin = _create_user(db_session, "admin_def1", UserRole.ADMIN)
    tech = _create_user(db_session, "tech_def1", UserRole.TECHNICIAN)
    obs = _create_user(db_session, "obs_def1", UserRole.OBSERVER)
    usr = _create_user(db_session, "usr_def1", UserRole.USER)

    # ADMIN -> 200
    res = client.get("/technician/schedule", cookies={"session": generate_session_cookie(admin.id)})
    assert res.status_code == 200

    # TECHNICIAN -> 200
    res = client.get("/technician/schedule", cookies={"session": generate_session_cookie(tech.id)})
    assert res.status_code == 200

    # OBSERVER -> 403
    res = client.get("/technician/schedule", cookies={"session": generate_session_cookie(obs.id)})
    assert res.status_code == 403

    # USER -> 403
    res = client.get("/technician/schedule", cookies={"session": generate_session_cookie(usr.id)})
    assert res.status_code == 403

    app.dependency_overrides.clear()


def test_reports_role_access(db_session: Session):
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app, follow_redirects=False)

    admin = _create_user(db_session, "admin_def1_rep", UserRole.ADMIN)
    tech = _create_user(db_session, "tech_def1_rep", UserRole.TECHNICIAN)
    obs = _create_user(db_session, "obs_def1_rep", UserRole.OBSERVER)
    usr = _create_user(db_session, "usr_def1_rep", UserRole.USER)

    # ADMIN -> 200
    res = client.get("/reports", cookies={"session": generate_session_cookie(admin.id)})
    assert res.status_code == 200

    # TECHNICIAN -> 200
    res = client.get("/reports", cookies={"session": generate_session_cookie(tech.id)})
    assert res.status_code == 200

    # OBSERVER -> 200
    res = client.get("/reports", cookies={"session": generate_session_cookie(obs.id)})
    assert res.status_code == 200

    # USER -> 403
    res = client.get("/reports", cookies={"session": generate_session_cookie(usr.id)})
    assert res.status_code == 403

    app.dependency_overrides.clear()
