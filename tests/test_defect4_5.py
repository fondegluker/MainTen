"""Regression tests for Defect 4 & Defect 5: Magic-link Copy/Open buttons and token invalidation/regeneration."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import AuditLog, User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_defect4_5.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_defect4_5.db"):
        os.remove("./test_defect4_5.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_magic_link_copy_open_buttons_and_regeneration(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_d45",
        email_or_login="admin_d45@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    target_user = User(
        username="target_d45",
        email_or_login="target_d45@example.com",
        password_hash=provider.hash_password("targetpass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add_all([admin, target_user])
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

    # 1. GET magic link page -> assert Copy and Open buttons present
    res_get = client.get(f"/admin/users/{target_user.id}/magic-link")
    assert res_get.status_code == 200
    assert "copy-btn" in res_get.text
    assert "open-btn" in res_get.text
    assert "Скопировать" in res_get.text
    assert "Открыть" in res_get.text

    # Extract original token
    import re

    match = re.search(r'id="magic-url-input"[^>]*value="([^"]+)"', res_get.text)
    initial_url = match.group(1)
    old_token = initial_url.split("token=")[1]

    # Verify old token works initially
    res_old_login = client.get(f"/auth/magic-link?token={old_token}", headers={"Accept": "text/html"})
    assert res_old_login.status_code == 302

    # 2. Regenerate magic link (JSON mode as Admin)
    res_regen = client.post(
        f"/admin/users/{target_user.id}/magic-link/regenerate",
        headers={"Accept": "application/json", "Cookie": f"session={session_cookie}"},
    )
    assert res_regen.status_code == 200
    data = res_regen.json()
    new_url = data["magic_url"]
    new_token = new_url.split("token=")[1]
    assert new_token != old_token
    assert "timestamp" in data

    # 3. Verify old token is now invalidated (401 Unauthorized)
    res_old_invalid = client.get(f"/auth/magic-link?token={old_token}", headers={"Accept": "text/html"})
    assert res_old_invalid.status_code == 401

    # 4. Verify new token works
    res_new_valid = client.get(f"/auth/magic-link?token={new_token}", headers={"Accept": "text/html"})
    assert res_new_valid.status_code == 302

    # 5. Verify audit log entry written
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "reissue_magic_link", AuditLog.entity_id == target_user.id)
        .first()
    )
    assert audit is not None

    app.dependency_overrides.clear()
