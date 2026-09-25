"""Unit tests for fixed 3+3 weekday slotting grid builder excluding Sunday (Step 4)."""

from datetime import date
from sqlalchemy.orm import Session

from app.services.scheduling_service import compute_available_dates, get_date_picker_grid


def test_grid_builder_fixed_weekday_slots_and_no_sunday(db_session: Session):
    """Test get_date_picker_grid places days strictly into their matching weekday columns."""
    grid = get_date_picker_grid(2025, 5, db_session, locale="ru", current_date=date(2025, 1, 1))

    for week in grid["weeks"]:
        assert len(week["row1"]) == 3
        assert len(week["row2"]) == 3

        # Row 1: Mon (slot 0), Tue (slot 1), Wed (slot 2)
        if week["row1"][0] is not None:
            assert week["row1"][0]["date"].weekday() == 0  # Monday
        if week["row1"][1] is not None:
            assert week["row1"][1]["date"].weekday() == 1  # Tuesday
        if week["row1"][2] is not None:
            assert week["row1"][2]["date"].weekday() == 2  # Wednesday

        # Row 2: Thu (slot 0), Fri (slot 1), Sat (slot 2)
        if week["row2"][0] is not None:
            assert week["row2"][0]["date"].weekday() == 3  # Thursday
        if week["row2"][1] is not None:
            assert week["row2"][1]["date"].weekday() == 4  # Friday
        if week["row2"][2] is not None:
            assert week["row2"][2]["date"].weekday() == 5  # Saturday


def test_grid_builder_midweek_month_start_empty_slots(db_session: Session):
    """Test May 2025 starting on Thursday (May 1st is Thursday = slot 0 of Row 2) leaves Row 1 empty."""
    grid = get_date_picker_grid(2025, 5, db_session, locale="ru", current_date=date(2025, 1, 1))

    first_week = grid["weeks"][0]
    # 2025-05-01 is Thursday (weekday 3)
    assert first_week["row1"][0] is None  # Monday
    assert first_week["row1"][1] is None  # Tuesday
    assert first_week["row1"][2] is None  # Wednesday
    assert first_week["row2"][0] is not None  # Thursday
    assert first_week["row2"][0]["day_number"] == 1


def test_compute_available_dates_3x2_slotted_weeks(db_session: Session, regular_user):
    """Test compute_available_dates organizes selection window into fixed 2x3 slotted weeks."""
    from app.models.models import Computer

    comp = Computer(
        hostname="pc-slotted-grid",
        ip="192.168.1.190",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    data = compute_available_dates(comp.id, db_session, today=date(2025, 5, 1))
    assert "weeks" in data
    assert len(data["weeks"]) > 0

    for week in data["weeks"]:
        assert len(week["row1"]) == 3
        assert len(week["row2"]) == 3

        # Verify slotted weekday indices
        if week["row1"][0] is not None:
            assert week["row1"][0]["weekday_idx"] == 0
        if week["row1"][1] is not None:
            assert week["row1"][1]["weekday_idx"] == 1
        if week["row1"][2] is not None:
            assert week["row1"][2]["weekday_idx"] == 2
        if week["row2"][0] is not None:
            assert week["row2"][0]["weekday_idx"] == 3
        if week["row2"][1] is not None:
            assert week["row2"][1]["weekday_idx"] == 4
        if week["row2"][2] is not None:
            assert week["row2"][2]["weekday_idx"] == 5
