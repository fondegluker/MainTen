"""Regression tests for Issue 3: Admin Settings Page."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import AuditLog, Setting, User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_issue3.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_issue3.db"):
        os.remove("./test_issue3.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_admin_settings_access_and_crud(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_i3",
        email_or_login="admin_i3@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    user = User(
        username="user_i3",
        email_or_login="user_i3@example.com",
        password_hash=provider.hash_password("userpass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add_all([admin, user])
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app, follow_redirects=False)

    # 1. Non-admin -> 403
    client.cookies.set("session", generate_session_cookie(user.id))
    res_user = client.get("/admin/settings")
    assert res_user.status_code == 403

    # 2. Admin -> 200
    client.cookies.set("session", generate_session_cookie(admin.id))
    res_admin = client.get("/admin/settings")
    assert res_admin.status_code == 200
    assert "Ширина окна выбора даты" in res_admin.text

    # 3. Save invalid values (offset > window) -> 422
    res_invalid = client.post(
        "/admin/settings",
        data={
            "interval_rtc_months": 6,
            "interval_non_rtc_months": 12,
            "selection_window_days": 20,
            "prompt_start_offset_days": 25,  # Invalid: offset > window
            "technician_daily_capacity": 1,
            "timezone": "Europe/Minsk",
        },
    )
    assert res_invalid.status_code == 422

    # 4. Save valid values -> 302, DB updated, audit log created
    res_valid = client.post(
        "/admin/settings",
        data={
            "interval_rtc_months": 3,
            "interval_non_rtc_months": 9,
            "selection_window_days": 14,
            "prompt_start_offset_days": 7,
            "technician_daily_capacity": 2,
            "allow_short_days": "on",
            "timezone": "Europe/Minsk",
        },
    )
    assert res_valid.status_code == 302

    setting_row = db_session.query(Setting).filter(Setting.key == "app_settings").first()
    assert setting_row is not None
    assert setting_row.value_json["selection_window_days"] == 14

    audit = db_session.query(AuditLog).filter(AuditLog.action == "update_settings").first()
    assert audit is not None

    # 5. Reset to defaults -> 302, DB restored
    res_reset = client.post("/admin/settings/reset")
    assert res_reset.status_code == 302

    db_session.refresh(setting_row)
    assert setting_row.value_json["selection_window_days"] == 20

    app.dependency_overrides.clear()
