"""Unit and integration tests for date selection rules and weekend rejection (Issue 4)."""

from datetime import date
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.tokens import create_access_token
from app.models.models import Computer, User
from app.services.scheduling_service import validate_maintenance_date


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
    is_valid_past, msg_past = validate_maintenance_date(
        comp.id, date(2025, 4, 30), db_session, today=today_ref
    )
    assert not is_valid_past
    assert "будущую" in msg_past

    # 2. Weekend date (2025-05-03 is Saturday)
    is_valid_sat, msg_sat = validate_maintenance_date(
        comp.id, date(2025, 5, 3), db_session, today=today_ref
    )
    assert not is_valid_sat
    assert "выходным" in msg_sat or "праздничным" in msg_sat

    # 3. Valid working date (2025-05-02 is Friday)
    is_valid_fri, msg_fri = validate_maintenance_date(
        comp.id, date(2025, 5, 2), db_session, today=today_ref
    )
    assert is_valid_fri
    assert msg_fri is None


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
