"""Regression tests for Issue 5: Working Calendar Editor."""

import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import AuditLog, DayKind, User, UserRole, WorkingCalendar
from app.services.scheduling_service import is_working_day

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_issue5.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_issue5.db"):
        os.remove("./test_issue5.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_working_calendar_editor_and_is_working_day_helper(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_i5",
        email_or_login="admin_i5@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    user = User(
        username="user_i5",
        email_or_login="user_i5@example.com",
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

    # 1. Access Control: USER -> 403, ADMIN -> 200
    client.cookies.set("session", generate_session_cookie(user.id))
    assert client.get("/admin/calendar").status_code == 403

    client.cookies.set("session", generate_session_cookie(admin.id))
    assert client.get("/admin/calendar").status_code == 200

    # 2. Toggle a workday (2026-05-15) -> non-working
    test_d = date(2026, 5, 15)  # Friday
    res_toggle = client.post("/admin/calendar/toggle", data={"date": test_d.isoformat()})
    assert res_toggle.status_code == 302

    entry = db_session.query(WorkingCalendar).filter(WorkingCalendar.date == test_d).first()
    assert entry is not None
    assert not entry.is_working
    assert entry.source == "admin"
    assert not is_working_day(test_d, db_session)

    # Toggle back -> working
    client.post("/admin/calendar/toggle", data={"date": test_d.isoformat()})
    db_session.refresh(entry)
    assert entry.is_working
    assert is_working_day(test_d, db_session)

    # 3. Mark a day as holiday with notes
    res_edit = client.post(
        "/admin/calendar/edit-day",
        data={"date": test_d.isoformat(), "kind": "holiday", "description": "Праздник"},
    )
    assert res_edit.status_code == 302

    db_session.refresh(entry)
    assert entry.kind == DayKind.HOLIDAY
    assert not entry.is_working
    assert not is_working_day(test_d, db_session)

    # 4. Bulk import CSV valid file
    csv_content = "date,kind,is_working,description\n2026-06-01,workday,true,День защиты детей\n"
    res_import = client.post(
        "/admin/calendar/bulk-import",
        files={"file": ("test_cal.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert res_import.status_code == 302

    imported = db_session.query(WorkingCalendar).filter(WorkingCalendar.date == date(2026, 6, 1)).first()
    assert imported is not None
    assert imported.kind == DayKind.WORKDAY

    # 5. Reset to default Belarus calendar
    res_reset = client.post("/admin/calendar/reset")
    assert res_reset.status_code == 302

    audit = db_session.query(AuditLog).filter(AuditLog.action == "reset_calendar").first()
    assert audit is not None

    app.dependency_overrides.clear()
