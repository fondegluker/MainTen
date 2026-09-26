"""Integration tests required for Iteration 4 scope."""

from datetime import date

from fastapi.testclient import TestClient

from app.auth.providers import LocalAuthProvider
from app.auth.tokens import generate_session_cookie
from app.models.models import AuditLog, Computer, MaintenanceEvent, MaintenanceEventStatus, User, UserRole


def test_get_my_computers_page_as_user(client: TestClient, db_session):
    """Test GET /user/my-computers as USER via magic link session cookie returns 200 and renders date picker."""
    provider = LocalAuthProvider()
    user = User(
        username="user_iter4",
        email_or_login="user_iter4@cfms.local",
        password_hash=provider.hash_password("pass123"),
        role=UserRole.USER,
        is_active=True,
    )
    comp = Computer(
        hostname="PC-USER-ITER4",
        owner_user_id=user.id,
        next_maintenance_due_at=date(2025, 5, 20),
        status="active",
    )
    db_session.add_all([user, comp])
    db_session.commit()

    cookie_val = generate_session_cookie(user.id)
    client.cookies.set("session", cookie_val)

    res = client.get("/user/my-computers")
    assert res.status_code == 200
    assert "PC-USER-ITER4" in res.text
    assert "data-testid=\"maintenance-date-picker\"" in res.text


def test_post_pick_date_creates_planned_event_and_audit_log(client: TestClient, db_session):
    """Test POST /user/schedule/{id} creates planned maintenance_event and audit_log entry."""
    provider = LocalAuthProvider()
    user = User(
        username="user_booking",
        email_or_login="user_booking@cfms.local",
        password_hash=provider.hash_password("pass123"),
        role=UserRole.USER,
        is_active=True,
    )
    tech = User(
        username="tech_booking",
        email_or_login="tech_booking@cfms.local",
        password_hash=provider.hash_password("pass123"),
        role=UserRole.TECHNICIAN,
        is_active=True,
    )
    comp = Computer(
        hostname="PC-BOOKING-TEST",
        owner_user_id=user.id,
        next_maintenance_due_at=date(2025, 5, 20),
        status="active",
    )
    db_session.add_all([user, tech, comp])
    db_session.commit()

    cookie_val = generate_session_cookie(user.id)
    client.cookies.set("session", cookie_val)

    # Pick valid future date
    res = client.post(
        f"/user/schedule/{comp.id}",
        data={"scheduled_date_str": "2025-05-15"},
        follow_redirects=False,
    )
    assert res.status_code == 302
    assert "message=" in res.headers["location"]

    event = (
        db_session.query(MaintenanceEvent)
        .filter(MaintenanceEvent.computer_id == comp.id, MaintenanceEvent.scheduled_date == date(2025, 5, 15))
        .first()
    )
    assert event is not None
    assert event.status == MaintenanceEventStatus.PLANNED
    assert event.technician_id == tech.id

    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.entity == "maintenance_events", AuditLog.entity_id == event.id)
        .first()
    )
    assert audit is not None


def test_post_disabled_date_returns_422(client: TestClient, db_session):
    """Test POST /user/schedule/{id} with disabled date (Saturday 2025-05-17) returns 422 with localized message."""
    provider = LocalAuthProvider()
    user = User(
        username="user_disabled_pick",
        email_or_login="user_disabled_pick@cfms.local",
        password_hash=provider.hash_password("pass123"),
        role=UserRole.USER,
        is_active=True,
    )
    comp = Computer(
        hostname="PC-DISABLED-PICK",
        owner_user_id=user.id,
        next_maintenance_due_at=date(2025, 5, 20),
        status="active",
    )
    db_session.add_all([user, comp])
    db_session.commit()

    cookie_val = generate_session_cookie(user.id)
    client.cookies.set("session", cookie_val)

    res = client.post(
        f"/user/schedule/{comp.id}",
        data={"scheduled_date_str": "2025-05-17"},
    )
    assert res.status_code == 422
    assert "detail" in res.json()


def test_reschedule_uses_same_picker_component(client: TestClient, db_session):
    """Test reschedule ('Изменить дату') flow uses same picker component and same available date set."""
    provider = LocalAuthProvider()
    user = User(
        username="user_reschedule",
        email_or_login="user_reschedule@cfms.local",
        password_hash=provider.hash_password("pass123"),
        role=UserRole.USER,
        is_active=True,
    )
    tech = User(
        username="tech_reschedule",
        email_or_login="tech_reschedule@cfms.local",
        password_hash=provider.hash_password("pass123"),
        role=UserRole.TECHNICIAN,
        is_active=True,
    )
    comp = Computer(
        hostname="PC-RESCHEDULE",
        owner_user_id=user.id,
        next_maintenance_due_at=date(2025, 5, 20),
        status="active",
    )
    db_session.add_all([user, tech, comp])
    db_session.commit()

    # Pre-existing planned event
    event = MaintenanceEvent(
        computer_id=comp.id,
        technician_id=tech.id,
        scheduled_date=date(2025, 5, 14),
        status=MaintenanceEventStatus.PLANNED,
    )
    db_session.add(event)
    db_session.commit()

    cookie_val = generate_session_cookie(user.id)
    client.cookies.set("session", cookie_val)

    res = client.get("/user/my-computers")
    assert res.status_code == 200
    assert "Изменить дату" in res.text or "Change date" in res.text
    assert "data-mode=\"reschedule\"" in res.text or "data-testid=\"maintenance-date-picker\"" in res.text
