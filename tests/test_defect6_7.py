"""Regression tests for Defect 6 & Defect 7: Last maintenance date in computer list and edit form."""

import os
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import AuditLog, Computer, User, UserRole

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_defect6_7.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_defect6_7.db"):
        os.remove("./test_defect6_7.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_computer_list_last_maintenance_column_and_sorting(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_d67",
        email_or_login="admin_d67@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    c1 = Computer(
        hostname="COMP-A",
        last_maintenance_at=datetime(2024, 5, 10, 0, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    c2 = Computer(
        hostname="COMP-B",
        last_maintenance_at=None,
        status="active",
    )
    db_session.add_all([admin, c1, c2])
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

    # 1. RU header and values
    res_ru = client.get("/admin/computers?lang=ru")
    assert res_ru.status_code == 200
    assert "Дата последнего обслуживания" in res_ru.text
    assert "2024-05-10" in res_ru.text
    assert "—" in res_ru.text

    # 2. EN header
    res_en = client.get("/admin/computers?lang=en")
    assert res_en.status_code == 200
    assert "Last maintenance" in res_en.text

    # 3. Sorting by last_maintenance_at asc
    res_sort_asc = client.get("/admin/computers?sort_by=last_maintenance_at&sort_order=asc")
    assert res_sort_asc.status_code == 200

    app.dependency_overrides.clear()


def test_edit_computer_last_maintenance_validation_and_recalculation(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_edit_d67",
        email_or_login="admin_edit_d67@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    comp_rtc = Computer(
        hostname="EDIT-COMP-RTC",
        is_round_the_clock=True,
        last_maintenance_at=datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc),
        next_maintenance_due_at=datetime(2024, 7, 15, 0, 0, 0, tzinfo=timezone.utc),
        status="active",
    )
    db_session.add_all([admin, comp_rtc])
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

    # 1. Validation error on future date
    future_date_str = (datetime.now(timezone.utc).date() + timedelta(days=10)).isoformat()
    res_future = client.post(
        f"/admin/computers/{comp_rtc.id}/edit",
        data={
            "hostname": comp_rtc.hostname,
            "last_maintenance_at": future_date_str,
            "is_round_the_clock": "on",
        },
    )
    assert res_future.status_code == 400
    assert "не может быть в будущем" in res_future.text

    # 2. Valid past date update: 2025-01-10 -> RTC next due date should be 2025-07-10
    res_valid = client.post(
        f"/admin/computers/{comp_rtc.id}/edit",
        data={
            "hostname": comp_rtc.hostname,
            "last_maintenance_at": "2025-01-10",
            "is_round_the_clock": "on",
        },
    )
    assert res_valid.status_code == 302

    db_session.refresh(comp_rtc)
    assert comp_rtc.last_maintenance_at.date() == date(2025, 1, 10)
    assert comp_rtc.next_maintenance_due_at.date() == date(2025, 7, 10)

    # Verify audit_log entry
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "update_computer", AuditLog.entity_id == comp_rtc.id)
        .first()
    )
    assert audit is not None
    assert audit.before_json["last_maintenance_at"] is not None
    assert "2025-01-10" in audit.after_json["last_maintenance_at"]

    app.dependency_overrides.clear()
