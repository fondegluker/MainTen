"""Unit and integration tests for compute_available_dates, date selection rules, and API endpoint."""

from datetime import date, datetime, timezone

from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.tokens import create_access_token
from app.models.models import Computer, MaintenanceEvent, MaintenanceEventStatus, User
from app.services.scheduling_service import compute_available_dates, validate_maintenance_date


def test_compute_available_dates_structure_and_blocked_reasons(db_session: Session, regular_user: User):
    """Test compute_available_dates returns selectable and blocked lists with clear reasons."""
    comp = Computer(
        hostname="pc-comp-test",
        ip="192.168.1.185",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    today_ref = date(2025, 5, 1)

    data = compute_available_dates(comp.id, db_session, today=today_ref)
    assert "window_start" in data
    assert "window_end" in data
    assert isinstance(data["selectable"], list)
    assert isinstance(data["blocked"], list)

    # 2025-05-03 is Saturday -> must be in blocked with reason='weekend'
    blocked_dates = {item["date"]: item["reason"] for item in data["blocked"]}
    assert "2025-05-03" in blocked_dates
    assert blocked_dates["2025-05-03"] == "weekend"

    # 2025-05-02 is Friday -> must be in selectable
    assert "2025-05-02" in data["selectable"]


def test_compute_available_dates_when_already_booked(db_session: Session, regular_user: User, tech_user: User):
    """Test a date already booked for the computer is placed in blocked list with reason='booked'."""
    comp = Computer(
        hostname="pc-booked-test",
        ip="192.168.1.186",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    # Book event on 2025-05-02
    event = MaintenanceEvent(
        computer_id=comp.id,
        technician_id=tech_user.id,
        scheduled_date=date(2025, 5, 2),
        status=MaintenanceEventStatus.PLANNED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    today_ref = date(2025, 5, 1)
    data = compute_available_dates(comp.id, db_session, today=today_ref)

    blocked_dates = {item["date"]: item["reason"] for item in data["blocked"]}
    assert "2025-05-02" in blocked_dates
    assert blocked_dates["2025-05-02"] == "booked"
    assert "2025-05-02" not in data["selectable"]


def test_validate_maintenance_date_rejects_weekends_and_past(db_session: Session, regular_user: User):
    """Test validate_maintenance_date helper rejects weekend and past dates."""
    comp = Computer(
        hostname="pc-rule-test",
        ip="192.168.1.180",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    today_ref = date(2025, 5, 1)

    # 1. Past date
    is_valid_past, msg_past = validate_maintenance_date(comp.id, date(2025, 4, 30), db_session, today=today_ref)
    assert not is_valid_past
    assert "будущую" in msg_past

    # 2. Weekend date (2025-05-03 is Saturday)
    is_valid_sat, msg_sat = validate_maintenance_date(comp.id, date(2025, 5, 3), db_session, today=today_ref)
    assert not is_valid_sat
    assert "выходным" in msg_sat or "праздничным" in msg_sat


def test_server_rejects_weekend_submission_with_422(client: TestClient, db_session: Session, regular_user: User):
    """Test server POST /user/schedule/{id} returns 422 for weekend submission."""
    comp = Computer(
        hostname="pc-submit-weekend",
        ip="192.168.1.181",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    token = create_access_token({"sub": str(regular_user.id)})
    headers = {"Cookie": f"access_token={token}"}

    # Attempt to submit 2025-05-03 (Saturday)
    res = client.post(
        f"/user/schedule/{comp.id}",
        data={"scheduled_date_str": "2025-05-03"},
        headers=headers,
        follow_redirects=False,
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "detail" in res.json()
    assert res.json()["detail"] == "Выбранный день является выходным или праздничным"


def test_api_available_dates_endpoint(client: TestClient, db_session: Session, regular_user: User):
    """Test GET /api/computers/{id}/available-dates returns valid JSON metadata."""
    comp = Computer(
        hostname="pc-api-dates",
        ip="192.168.1.182",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    token = create_access_token({"sub": str(regular_user.id)})
    headers = {"Cookie": f"access_token={token}"}

    res = client.get(f"/api/computers/{comp.id}/available-dates", headers=headers)
    assert res.status_code == status.HTTP_200_OK
    body = res.json()
    assert "window_start" in body
    assert "window_end" in body
    assert "selectable" in body
    assert "blocked" in body
