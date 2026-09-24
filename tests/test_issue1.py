"""Regression tests for Issue 1: Systemic optional query parameter parsing helper."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import Computer, User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_issue1.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_issue1.db"):
        os.remove("./test_issue1.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_optional_owner_id_query_parameter_handling(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_i1",
        email_or_login="admin_i1@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    owner42 = User(
        id=42,
        username="owner42_i1",
        email_or_login="owner42_i1@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    c1 = Computer(hostname="PC-ALL-OWNERS-1", owner_user_id=None, status="active")
    c2 = Computer(hostname="PC-OWNER-42", owner_user_id=42, status="active")
    db_session.add_all([admin, owner42, c1, c2])
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app, follow_redirects=False)
    session_cookie = generate_session_cookie(admin.id)
    client.cookies.set("session", session_cookie)

    # 1. Empty string owner_id= -> 200, all rows shown (no 422 error!)
    res_empty = client.get("/admin/computers?owner_id=")
    assert res_empty.status_code == 200
    assert "PC-ALL-OWNERS-1" in res_empty.text
    assert "PC-OWNER-42" in res_empty.text

    # 2. owner_id=null / owner_id=undefined -> 200, all rows shown
    res_null = client.get("/admin/computers?owner_id=null")
    assert res_null.status_code == 200
    assert "PC-ALL-OWNERS-1" in res_null.text

    # 3. owner_id=42 -> 200, only owner 42
    res_42 = client.get("/admin/computers?owner_id=42")
    assert res_42.status_code == 200
    assert "PC-OWNER-42" in res_42.text

    # 4. Invalid string owner_id=abc -> 422
    res_invalid = client.get("/admin/computers?owner_id=abc")
    assert res_invalid.status_code == 422
    assert "unable to parse" in res_invalid.text or "valid integer" in res_invalid.text

    # 5. Check other list endpoints with empty parameters
    # GET /admin/users?role=&status=
    res_users = client.get("/admin/users?role=&status=")
    assert res_users.status_code == 200

    # GET /admin/audit?entity=&action=
    res_audit = client.get("/admin/audit?entity=&action=")
    assert res_audit.status_code == 200

    app.dependency_overrides.clear()
