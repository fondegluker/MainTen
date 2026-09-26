"""Unit tests required for Iteration 4 scope."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.models import (
    Computer,
    DayKind,
    MaintenanceEvent,
    MaintenanceEventStatus,
    User,
    WorkingCalendar,
)
from app.services.scheduling_service import (
    compute_available_dates,
    compute_next_maintenance_due_at,
    compute_window_bounds,
)


def test_compute_next_maintenance_due_at_rtc_and_non_rtc(db_session: Session):
    """Test compute_next_maintenance_due_at: RTC = +6 months, non-RTC = +12 months."""
    base_d = date(2025, 1, 15)

    comp_rtc = Computer(hostname="rtc-pc", is_round_the_clock=True)
    comp_non_rtc = Computer(hostname="non-rtc-pc", is_round_the_clock=False)

    due_rtc = compute_next_maintenance_due_at(comp_rtc, db_session, base_date=base_d)
    due_non_rtc = compute_next_maintenance_due_at(comp_non_rtc, db_session, base_date=base_d)

    assert due_rtc == date(2025, 7, 15)
    assert due_non_rtc == date(2026, 1, 15)


def test_window_bounds_centered_calculation(db_session: Session):
    """Test window bounds with selection_window_days = 20 and trigger_date = 2026-09-23 -> [2026-09-13 .. 2026-10-03]."""
    trigger_d = date(2026, 9, 23)
    start, end, prompt_start = compute_window_bounds(trigger_d, db_session)

    assert start == date(2026, 9, 13)
    assert end == date(2026, 10, 3)


def test_prompt_start_offset_calculation(db_session: Session):
    """Test prompt_start_offset_days = 10 and trigger_date = 2026-09-23 -> prompt starts 2026-09-13."""
    trigger_d = date(2026, 9, 23)
    start, end, prompt_start = compute_window_bounds(trigger_d, db_session)

    assert prompt_start == date(2026, 9, 13)


def test_selectability_rules_weekend_holiday_booked_past_outside_window(db_session: Session, regular_user: User, tech_user: User):
    """Test selectability rules for weekend, holiday, booked tech, booked comp, past, outside window."""
    comp = Computer(
        hostname="pc-rules-unit",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    today_ref = date(2025, 5, 1)

    # Seed holiday on 2025-05-09 (Friday)
    holiday_entry = WorkingCalendar(date=date(2025, 5, 9), is_working=False, kind=DayKind.HOLIDAY, description="Праздник")
    db_session.add(holiday_entry)

    # Book event for comp on 2025-05-12
    booked_ev = MaintenanceEvent(
        computer_id=comp.id,
        technician_id=tech_user.id,
        scheduled_date=date(2025, 5, 12),
        status=MaintenanceEventStatus.PLANNED,
    )
    db_session.add(booked_ev)
    db_session.commit()

    data = compute_available_dates(comp.id, db_session, today=today_ref)
    blocked_reasons = {b["date"]: b["reason"] for b in data["blocked"]}

    # Weekend (2025-05-10 Saturday) -> weekend
    assert blocked_reasons.get("2025-05-10") == "weekend"

    # Holiday (2025-05-09 Friday) -> holiday
    assert blocked_reasons.get("2025-05-09") == "holiday"

    # Booked computer (2025-05-12) -> booked
    assert blocked_reasons.get("2025-05-12") == "booked"


def test_empty_window_returns_no_available_dates_flag(db_session: Session, regular_user: User):
    """Test empty window case returning message and empty weeks."""
    comp = Computer(
        hostname="pc-empty-window",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2020, 1, 1),
    )
    db_session.add(comp)
    db_session.commit()

    today_ref = date(2025, 5, 1)
    data = compute_available_dates(comp.id, db_session, today=today_ref)

    assert data["has_selectable"] is False
    assert data["weeks"] == []
    assert data["message"] is not None


def test_leading_prefix_cut_preserves_middle_and_trailing_disabled(db_session: Session, regular_user: User):
    """Test grid starts at first selectable date, hiding leading disabled days while preserving middle/trailing."""
    comp = Computer(
        hostname="pc-leading-cut",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 10),
    )
    db_session.add(comp)
    db_session.commit()

    today_ref = date(2025, 5, 1)  # Thursday May 1st
    data = compute_available_dates(comp.id, db_session, today=today_ref)

    assert data["has_selectable"] is True
    first_selectable = date.fromisoformat(data["selectable"][0])

    for d in data["days"]:
        assert d["date"] >= first_selectable
