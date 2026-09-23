"""Regression tests for Defect 8: User landing page date picker as primary element & computer detail view."""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_magic_link_token, generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import (
    AuditLog,
    Computer,
    MaintenanceEvent,
    MaintenanceEventStatus,
    User,
    UserRole,
    WorkingCalendar,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_defect8.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_defect8.db"):
        os.remove("./test_defect8.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_magic_link_landing_active_window_date_picker_primary(db_session: Session):
    provider = LocalAuthProvider()
    user = User(
        username="usr_d8_active",
        email_or_login="usr_d8_active@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    tech = User(
        username="tech_d8",
        email_or_login="tech_d8@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.TECHNICIAN,
        is_active=True,
    )
    db_session.add_all([user, tech])
    db_session.commit()

    today = datetime.now(timezone.utc).date()
    due_date = today + timedelta(days=10)  # window is active (0 <= today <= due_date)

    comp = Computer(
        hostname="PC-D8-ACTIVE",
        owner_user_id=user.id,
        next_maintenance_due_at=datetime.combine(due_date, datetime.min.time()),
        status="active",
    )
    db_session.add(comp)
    db_session.commit()

    # Seed 1 working day and 1 weekend day
    work_day = today + timedelta(days=2)
    weekend_day = today + timedelta(days=3)

    cal_work = WorkingCalendar(date=work_day, is_working=True, kind="workday", description="Workday")
    cal_weekend = WorkingCalendar(date=weekend_day, is_working=False, kind="weekend", description="Weekend")
    db_session.add_all([cal_work, cal_weekend])
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app, follow_redirects=False)

    # Magic link
    magic_token = generate_magic_link_token(user.id, computer_id=comp.id)
    res_ml = client.get(f"/auth/magic-link?token={magic_token}", headers={"Accept": "text/html"})
    assert res_ml.status_code == 302

    # GET /user/my-computers
    session_cookie = generate_session_cookie(user.id)
    res_page = client.get("/user/my-computers", headers={"Cookie": f"session={session_cookie}"})
    assert res_page.status_code == 200
    assert "Выберите дату технического обслуживания" in res_page.text
    assert work_day.isoformat() in res_page.text
    assert weekend_day.isoformat() not in res_page.text
    assert f"info-btn-{comp.id}" in res_page.text
    assert "Информация о моём компьютере" in res_page.text

    # Submit date selection
    res_sub = client.post(
        f"/user/schedule/{comp.id}",
        data={"scheduled_date_str": work_day.isoformat()},
        headers={"Cookie": f"session={session_cookie}"},
    )
    assert res_sub.status_code == 302

    # Verify event and audit log created
    event = (
        db_session.query(MaintenanceEvent)
        .filter(MaintenanceEvent.computer_id == comp.id, MaintenanceEvent.scheduled_date == work_day)
        .first()
    )
    assert event is not None
    assert event.status == MaintenanceEventStatus.PLANNED

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "create_maintenance_event", AuditLog.entity_id == event.id)
        .first()
    )
    assert audit is not None

    # Verify info route /user/my-computers/{comp.id}
    res_info = client.get(f"/user/my-computers/{comp.id}", headers={"Cookie": f"session={session_cookie}"})
    assert res_info.status_code == 200
    assert "Характеристики ПК" in res_info.text
    assert "PC-D8-ACTIVE" in res_info.text
    assert work_day.strftime("%d.%m.%Y") in res_info.text

    app.dependency_overrides.clear()


def test_window_future_state(db_session: Session):
    provider = LocalAuthProvider()
    user = User(
        username="usr_d8_future",
        email_or_login="usr_d8_future@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    today = datetime.now(timezone.utc).date()
    due_date = today + timedelta(days=60)  # window opens 20 days prior (today + 40)

    comp = Computer(
        hostname="PC-D8-FUTURE",
        owner_user_id=user.id,
        next_maintenance_due_at=datetime.combine(due_date, datetime.min.time()),
        status="active",
    )
    db_session.add(comp)
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    session_cookie = generate_session_cookie(user.id)
    client.cookies.set("session", session_cookie)

    res = client.get("/user/my-computers")
    assert res.status_code == 200
    assert "Окно выбора откроется" in res.text
    prompt_start = due_date - timedelta(days=20)
    assert prompt_start.strftime("%d.%m.%Y") in res.text

    app.dependency_overrides.clear()


def test_window_expired_state(db_session: Session):
    provider = LocalAuthProvider()
    user = User(
        username="usr_d8_expired",
        email_or_login="usr_d8_expired@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    today = datetime.now(timezone.utc).date()
    expired_due = today - timedelta(days=5)

    comp = Computer(
        hostname="PC-D8-EXPIRED",
        owner_user_id=user.id,
        next_maintenance_due_at=datetime.combine(expired_due, datetime.min.time()),
        status="active",
    )
    db_session.add(comp)
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    session_cookie = generate_session_cookie(user.id)
    client.cookies.set("session", session_cookie)

    res = client.get("/user/my-computers")
    assert res.status_code == 200
    assert "Срок выбора даты ТО истек" in res.text
    assert "эскалация" in res.text

    app.dependency_overrides.clear()
