"""Unit tests for Monday-first calendar grid builder (Issue 1)."""

from datetime import date
from sqlalchemy.orm import Session

from app.services.scheduling_service import get_month_calendar_grid


def test_calendar_grid_leap_february_2028(db_session: Session):
    """Test February in a leap year (2028) has 29 days and weeks of 7 columns."""
    grid = get_month_calendar_grid(2028, 2, db_session, current_date=date(2025, 1, 1))

    assert grid["num_days"] == 29
    assert grid["year"] == 2028
    assert grid["month"] == 2

    for week in grid["weeks"]:
        assert len(week) == 7

    # Count non-blank cells
    non_blanks = [cell for week in grid["weeks"] for cell in week if cell is not None]
    assert len(non_blanks) == 29
    assert non_blanks[0]["day_number"] == 1
    assert non_blanks[-1]["day_number"] == 29


def test_calendar_grid_non_leap_february_2027(db_session: Session):
    """Test February in a non-leap year (2027) has 28 days."""
    grid = get_month_calendar_grid(2027, 2, db_session, current_date=date(2025, 1, 1))

    assert grid["num_days"] == 28
    non_blanks = [cell for week in grid["weeks"] for cell in week if cell is not None]
    assert len(non_blanks) == 28


def test_calendar_grid_month_starting_on_sunday(db_session: Session):
    """Test a month starting on Sunday (e.g. August 2027) has 6 leading blanks."""
    # 2027-08-01 is Sunday (ISO weekday 6 -> 6 leading blanks)
    grid = get_month_calendar_grid(2027, 8, db_session, current_date=date(2025, 1, 1))

    assert grid["leading_blanks"] == 6
    assert grid["weeks"][0][0] is None
    assert grid["weeks"][0][5] is None
    assert grid["weeks"][0][6] is not None
    assert grid["weeks"][0][6]["day_number"] == 1


def test_calendar_grid_year_boundaries_and_clamping(db_session: Session):
    """Test December -> January navigation and 10-year range bounding."""
    curr_date = date(2025, 1, 1)

    # Dec 2025 -> next month is Jan 2026
    dec_grid = get_month_calendar_grid(2025, 12, db_session, current_date=curr_date)
    assert dec_grid["next_year"] == 2026
    assert dec_grid["next_month"] == 1

    # Request year beyond current + 10 (e.g. 2040) -> clamped to 2035
    clamped_grid = get_month_calendar_grid(2040, 5, db_session, current_date=curr_date)
    assert clamped_grid["year"] == 2035

    # Request year prior to current -> clamped to 2025
    clamped_past_grid = get_month_calendar_grid(2020, 5, db_session, current_date=curr_date)
    assert clamped_past_grid["year"] == 2025
