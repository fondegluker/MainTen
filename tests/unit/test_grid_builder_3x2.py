"""Unit tests for fixed 3+3 weekday slotting grid builder cutting leading disabled prefix (Step 4)."""

from datetime import date

from sqlalchemy.orm import Session

from app.models.models import Computer
from app.services.scheduling_service import compute_available_dates, get_date_picker_grid


def test_grid_builder_fixed_weekday_slots_and_no_sunday(db_session: Session):
    """Test get_date_picker_grid places days strictly into their matching weekday columns (Mon..Sat = slots 0..5)."""
    grid = get_date_picker_grid(2025, 5, db_session, locale="ru", current_date=date(2025, 1, 1))

    for week in grid["weeks"]:
        assert len(week["slots"]) == 6

        for idx in range(6):
            cell = week["slots"][idx]
            if cell is not None:
                assert cell["date"].weekday() == idx
                assert "formatted_short" in cell
                assert cell["formatted_short"] == cell["date"].strftime("%d.%m")


def test_cut_leading_disabled_prefix(db_session: Session, regular_user):
    """Test compute_available_dates cuts leading past/disabled days before first_selectable_date."""
    comp = Computer(
        hostname="pc-prefix-cut",
        ip="192.168.1.195",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 10),
    )
    db_session.add(comp)
    db_session.commit()

    # today is May 1st 2025 (Thursday)
    today_ref = date(2025, 5, 1)

    data = compute_available_dates(comp.id, db_session, today=today_ref)
    assert data["has_selectable"] is True

    first_selectable = date.fromisoformat(data["selectable"][0])
    # Ensure all rendered days are >= first_selectable_date
    for d in data["days"]:
        assert d["date"] >= first_selectable

    # Check first week structure
    first_week = data["weeks"][0]
    first_mon_cell = first_week["slots"][0]
    # Monday of May 2nd's week is April 28th (past, before first_selectable) -> None
    assert first_mon_cell is None


def test_first_selectable_tuesday_empty_monday_placeholder(db_session: Session, regular_user):
    """Test if first selectable date is Tuesday, Monday of that week is an empty slot placeholder."""
    comp = Computer(
        hostname="pc-tuesday-start",
        ip="192.168.1.196",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 20),
    )
    db_session.add(comp)
    db_session.commit()

    # 2025-05-05 is Monday, 2025-05-06 is Tuesday
    today_ref = date(2025, 5, 5)  # Monday May 5 is today -> past/not future

    data = compute_available_dates(comp.id, db_session, today=today_ref)
    first_selectable = date.fromisoformat(data["selectable"][0])
    assert first_selectable == date(2025, 5, 6)  # Tuesday May 6

    first_week = data["weeks"][0]
    # Slot 0 (Monday) is None, Slot 1 (Tuesday May 6) is present
    assert first_week["slots"][0] is None
    assert first_week["slots"][1] is not None
    assert first_week["slots"][1]["date"] == date(2025, 5, 6)


def test_middle_disabled_day_remains_visible(db_session: Session, regular_user):
    """Test disabled days (e.g. weekend Saturday) AFTER first_selectable_date remain visible."""
    comp = Computer(
        hostname="pc-mid-disabled",
        ip="192.168.1.197",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2025, 5, 15),
    )
    db_session.add(comp)
    db_session.commit()

    today_ref = date(2025, 5, 1)  # Thursday
    data = compute_available_dates(comp.id, db_session, today=today_ref)

    # 2025-05-03 is Saturday (disabled weekend after May 2nd first selectable date)
    may_3 = [d for d in data["days"] if d["date"] == date(2025, 5, 3)]
    assert len(may_3) == 1
    assert may_3[0]["is_selectable"] is False
    assert "Выходной" in may_3[0]["disabled_reason"]


def test_empty_window_returns_no_weeks(db_session: Session, regular_user):
    """Test window with no selectable dates returns weeks=[] and has_selectable=False."""
    comp = Computer(
        hostname="pc-no-dates",
        ip="192.168.1.198",
        owner_user_id=regular_user.id,
        next_maintenance_due_at=date(2020, 1, 1),  # Far past due date
    )
    db_session.add(comp)
    db_session.commit()

    today_ref = date(2025, 5, 1)
    data = compute_available_dates(comp.id, db_session, today=today_ref)

    assert data["has_selectable"] is False
    assert data["weeks"] == []
    assert data["message"] is not None
