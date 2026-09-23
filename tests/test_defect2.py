"""Regression tests for Defect 2: Fleet import documentation route."""

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

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_defect2.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_defect2.db"):
        os.remove("./test_defect2.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_fleet_import_doc_as_admin(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_def2",
        email_or_login="admin_def2@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    session_cookie = generate_session_cookie(admin.id)
    client.cookies.set("session", session_cookie)

    res1 = client.get("/admin/docs/fleet-import-format")
    assert res1.status_code == 200
    assert "FLEET_IMPORT_COLUMNS" in res1.text or "hostname" in res1.text

    res2 = client.get("/docs/fleet-import-format.md")
    assert res2.status_code == 200
    assert "FLEET_IMPORT_COLUMNS" in res2.text or "hostname" in res2.text

    app.dependency_overrides.clear()
