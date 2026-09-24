"""Tests for Iteration 4: Scheduling Engine + User Date Selection Pages."""

import os
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.core.database import Base, get_db
from app.main import app
from app.models.models import (
    AuditLog,
    Computer,
    MaintenanceEventStatus,
    User,
    UserRole,
    WorkingCalendar,
)
from app.services.scheduling_service import (
    compute_next_maintenance_due_at,
    get_available_dates,
    is_notification_window_open,
    process_unselected_windows,
    schedule_maintenance,
)

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_iteration4.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_iteration4.db"):
        os.remove("./test_iteration4.db")


@pytest.fixture
def db_session(setup_db):
    session = TestingSessionLocal()
    yield session
    session.rollback()
    session.close()


def test_compute_next_maintenance_due_at(db_session):
    """Test 6 months for RTC computers and 12 months for non-RTC computers."""
    provider = LocalAuthProvider()
    owner = User(
        username="owner_it4",
        email_or_login="owner_it4@cfms.local",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()

    base_d = date(2025, 1, 15)

    comp_rtc = Computer(
        hostname="COMP-RTC",
        owner_user_id=owner.id,
        is_round_the_clock=True,
        last_maintenance_at=datetime.combine(base_d, datetime.min.time()),
        status="active",
    )

    comp_non_rtc = Computer(
        hostname="COMP-NON-RTC",
        owner_user_id=owner.id,
        is_round_the_clock=False,
        last_maintenance_at=datetime.combine(base_d, datetime.min.time()),
        status="active",
    )

    db_session.add_all([comp_rtc, comp_non_rtc])
    db_session.commit()

    due_rtc = compute_next_maintenance_due_at(comp_rtc, db_session)
    assert due_rtc == date(2025, 7, 15)

    due_non_rtc = compute_next_maintenance_due_at(comp_non_rtc, db_session)
    assert due_non_rtc == date(2026, 1, 15)


def test_notification_window_open(db_session):
    """Test notification window opens 20 days prior to due_date."""
    provider = LocalAuthProvider()
    owner = User(
        username="owner_win",
        email_or_login="owner_win@cfms.local",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()

    due_date = date(2025, 6, 1)
    comp = Computer(
        hostname="COMP-WIN",
        owner_user_id=owner.id,
        next_maintenance_due_at=datetime.combine(due_date, datetime.min.time()),
        status="active",
    )
    db_session.add(comp)
    db_session.commit()

    # 25 days before due date -> window closed
    assert not is_notification_window_open(comp, db_session, today=date(2025, 5, 5))

    # 20 days before due date -> window open
    assert is_notification_window_open(comp, db_session, today=date(2025, 5, 12))

    # On due date -> window open
    assert is_notification_window_open(comp, db_session, today=date(2025, 6, 1))


def test_get_available_dates_and_scheduling(db_session):
    """Test retrieving future working days with technician capacity and scheduling an event."""
    provider = LocalAuthProvider()
    tech = User(
        username="tech_it4",
        email_or_login="tech_it4@cfms.local",
        password_hash=provider.hash_password("techpass"),
        role=UserRole.TECHNICIAN,
        is_active=True,
    )
    owner = User(
        username="owner_sched",
        email_or_login="owner_sched@cfms.local",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add_all([tech, owner])
    db_session.commit()

    comp = Computer(
        hostname="COMP-SCHED",
        owner_user_id=owner.id,
        status="active",
    )
    db_session.add(comp)
    db_session.commit()

    today = date(2025, 3, 10)
    work_date_1 = date(2025, 3, 11)
    work_date_2 = date(2025, 3, 12)

    # Seed calendar working days
    cal1 = WorkingCalendar(date=work_date_1, is_working=True, kind="workday", description="Regular day")
    cal2 = WorkingCalendar(date=work_date_2, is_working=True, kind="workday", description="Regular day")
    db_session.add_all([cal1, cal2])
    db_session.commit()

    avail = get_available_dates(comp.id, db_session, today=today, days_ahead=10)
    assert len(avail) == 2
    dates = [a["date"] for a in avail]
    assert work_date_1 in dates
    assert work_date_2 in dates

    # Schedule maintenance on work_date_1
    event = schedule_maintenance(comp.id, work_date_1, owner.id, db_session)
    assert event is not None
    assert event.computer_id == comp.id
    assert event.technician_id == tech.id
    assert event.scheduled_date == work_date_1
    assert event.status == MaintenanceEventStatus.PLANNED

    # Audit log check
    audit = db_session.query(AuditLog).filter(AuditLog.action == "create_maintenance_event").first()
    assert audit is not None


def test_window_expiry_shift(db_session):
    """Test process_unselected_windows shifts due date forward by 30 days when window expires without event choice."""
    provider = LocalAuthProvider()
    owner = User(
        username="owner_exp",
        email_or_login="owner_exp@cfms.local",
        password_hash=provider.hash_password("pass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()

    expired_due = date(2025, 2, 1)
    comp = Computer(
        hostname="COMP-EXP",
        owner_user_id=owner.id,
        next_maintenance_due_at=datetime.combine(expired_due, datetime.min.time()),
        status="active",
    )
    db_session.add(comp)
    db_session.commit()

    today = date(2025, 2, 15)
    shifted = process_unselected_windows(db_session, today=today)
    assert shifted == 1

    db_session.refresh(comp)
    expected_new_due = expired_due + timedelta(days=30)
    comp_due_date = (
        comp.next_maintenance_due_at.date()
        if isinstance(comp.next_maintenance_due_at, datetime)
        else comp.next_maintenance_due_at
    )
    assert comp_due_date == expected_new_due


def test_user_my_computers_and_manager_aggregation(db_session):
    """Test /user/my-computers page rendering and multi-computer manager aggregation."""
    provider = LocalAuthProvider()
    manager = User(
        username="manager_it4",
        email_or_login="manager_it4@cfms.local",
        password_hash=provider.hash_password("mgrpass"),
        role=UserRole.USER,
        is_active=True,
    )
    db_session.add(manager)
    db_session.flush()

    now_d = datetime.now(timezone.utc)
    c1 = Computer(
        hostname="MGR-PC-1",
        owner_user_id=manager.id,
        status="active",
        next_maintenance_due_at=now_d + timedelta(days=30),
    )
    c2 = Computer(
        hostname="MGR-PC-2",
        owner_user_id=manager.id,
        status="active",
        next_maintenance_due_at=now_d + timedelta(days=30),
    )
    db_session.add_all([c1, c2])
    db_session.commit()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)

    session_cookie = generate_session_cookie(manager.id)
    client.cookies.set("session", session_cookie)

    res = client.get("/user/my-computers")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    assert "MGR-PC-1" in res.text
    assert "MGR-PC-2" in res.text
    assert "Менеджер" in res.text

    app.dependency_overrides.clear()
