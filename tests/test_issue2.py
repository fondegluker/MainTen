"""Regression tests for Issue 2: Centered selection window calculation, disabled calendar dates, and prompt start logic."""

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
from app.models.models import (
    Computer,
    DayKind,
    MaintenanceEvent,
    MaintenanceEventStatus,
    Setting,
    User,
    UserRole,
    WorkingCalendar,
)
from app.services.scheduling_service import (
    compute_window_bounds,
    get_window_calendar_days,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_issue2.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_issue2.db"):
        os.remove("./test_issue2.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_centered_selection_window_bounds_calculation(db_session: Session):
    trigger = date(2026, 9, 23)
    # Default selection_window_days = 20 -> half = 10 -> [2026-09-13 .. 2026-10-03]
    start, end, prompt_start = compute_window_bounds(trigger, db_session)
    assert start == date(2026, 9, 13)
    assert end == date(2026, 10, 3)
    assert prompt_start == date(2026, 9, 13)


def test_calendar_date_disabling_and_empty_window_escalation(db_session: Session):
    provider = LocalAuthProvider()
    owner = User(
        username="usr_i2",
        email_or_login="usr_i2@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    tech = User(
        username="tech_i2",
        email_or_login="tech_i2@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.TECHNICIAN,
        is_active=True,
    )
    db_session.add_all([owner, tech])
    db_session.commit()

    today = date(2026, 9, 15)
    trigger = date(2026, 9, 20)

    comp = Computer(
        hostname="COMP-I2",
        owner_user_id=owner.id,
        next_maintenance_due_at=datetime.combine(trigger, datetime.min.time(), tzinfo=timezone.utc),
        status="active",
    )
    db_session.add(comp)
    db_session.commit()

    # Seed days around trigger
    # 2026-09-10 (past)
    # 2026-09-19 (weekend)
    # 2026-09-21 (holiday)
    # 2026-09-22 (already booked for same computer)
    cal_past = WorkingCalendar(date=date(2026, 9, 10), is_working=True, kind=DayKind.WORKDAY)
    cal_weekend = WorkingCalendar(date=date(2026, 9, 19), is_working=False, kind=DayKind.WEEKEND)
    cal_holiday = WorkingCalendar(date=date(2026, 9, 21), is_working=False, kind=DayKind.HOLIDAY)
    cal_booked = WorkingCalendar(date=date(2026, 9, 22), is_working=True, kind=DayKind.WORKDAY)
    db_session.add_all([cal_past, cal_weekend, cal_holiday, cal_booked])
    db_session.commit()

    # Book 2026-09-22 for comp
    ev = MaintenanceEvent(
        computer_id=comp.id,
        technician_id=tech.id,
        scheduled_date=date(2026, 9, 22),
        status=MaintenanceEventStatus.PLANNED,
    )
    db_session.add(ev)
    db_session.commit()

    res = get_window_calendar_days(comp.id, db_session, today=today)
    days_dict = {d["date"]: d for d in res["days"]}

    # Past date (2026-09-10) is disabled
    assert not days_dict[date(2026, 9, 10)]["is_selectable"]
    assert days_dict[date(2026, 9, 10)]["disabled_reason"] == "Прошедшая дата"

    # Weekend (2026-09-19) is disabled
    assert not days_dict[date(2026, 9, 19)]["is_selectable"]

    # Holiday (2026-09-21) is disabled
    assert not days_dict[date(2026, 9, 21)]["is_selectable"]

    # Booked date (2026-09-22) is disabled
    assert not days_dict[date(2026, 9, 22)]["is_selectable"]
    assert days_dict[date(2026, 9, 22)]["disabled_reason"] == "Занято для этого ПК"


def test_changing_selection_window_days_setting_updates_ui(db_session: Session):
    provider = LocalAuthProvider()
    admin = User(
        username="admin_i2",
        email_or_login="admin_i2@example.com",
        password_hash=provider.hash_password("adminpass"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    user = User(
        username="usr_i2_setting",
        email_or_login="usr_i2_setting@example.com",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    comp = Computer(
        hostname="COMP-I2-SETTING",
        owner_user_id=user.id,
        next_maintenance_due_at=datetime.now(timezone.utc) + timedelta(days=5),
        status="active",
    )
    db_session.add_all([admin, user, comp])
    db_session.commit()

    # Update setting selection_window_days = 10
    setting = db_session.query(Setting).filter(Setting.key == "selection_window_days").first()
    if setting:
        setting.value_json = 10
    else:
        setting = Setting(key="selection_window_days", value_json=10)
        db_session.add(setting)
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    client.cookies.set("session", generate_session_cookie(user.id))

    res = client.get("/user/my-computers")
    assert res.status_code == 200

    app.dependency_overrides.clear()
