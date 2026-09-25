"""Unit tests for 3+3 grid builder excluding Sunday (Step 2)."""

from datetime import date
from sqlalchemy.orm import Session

from app.services.scheduling_service import get_date_picker_grid


def test_grid_builder_3x2_structure_and_no_sunday(db_session: Session):
    """Test get_date_picker_grid produces 2 rows of 3 columns with no Sunday."""
    grid = get_date_picker_grid(2025, 5, db_session, locale="ru", current_date=date(2025, 1, 1))

    assert grid["header_row1"] == ["Пн", "Вт", "Ср"]
    assert grid["header_row2"] == ["Чт", "Пт", "Сб"]

    for week in grid["weeks"]:
        assert len(week["row1"]) == 3
        assert len(week["row2"]) == 3

        # Assert no cell is Sunday
        for cell in week["row1"] + week["row2"]:
            if cell is not None:
                assert cell["date"].weekday() != 6, f"Sunday found in grid: {cell['date']}"


def test_grid_builder_month_starting_on_sunday(db_session: Session):
    """Test month starting on Sunday (August 2027) skips Sunday 1st and starts Monday 2nd with 0 leading blanks."""
    grid = get_date_picker_grid(2027, 8, db_session, locale="ru", current_date=date(2025, 1, 1))

    assert grid["leading_blanks"] == 0
    first_cell = grid["weeks"][0]["row1"][0]
    assert first_cell is not None
    assert first_cell["day_number"] == 2
    assert first_cell["date"] == date(2027, 8, 2)


def test_grid_builder_leap_february_2028(db_session: Session):
    """Test leap February 2028 has 29 days total, 25 Mon-Sat days, and no Sunday."""
    grid = get_date_picker_grid(2028, 2, db_session, locale="en", current_date=date(2025, 1, 1))

    assert grid["header_row1"] == ["Mon", "Tue", "Wed"]
    assert grid["header_row2"] == ["Thu", "Fri", "Sat"]

    visible_cells = [
        cell
        for week in grid["weeks"]
        for cell in week["row1"] + week["row2"]
        if cell is not None
    ]
    # In Feb 2028 (29 days), 4 days are Sundays -> 25 visible Mon-Sat days
    assert len(visible_cells) == 25
    assert not any(cell["date"].weekday() == 6 for cell in visible_cells)
