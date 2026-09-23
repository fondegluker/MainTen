"""add working_calendar table and seed Belarus calendar

Revision ID: 52f9a72b834e
Revises: 4573d757029f
Create Date: 2026-09-21 22:30:00.000000

"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "52f9a72b834e"
down_revision: Union[str, None] = "4573d757029f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Official public holidays in Belarus (Month, Day) -> Name
BELARUS_HOLIDAYS = {
    (1, 1): "Новый год",
    (1, 2): "Новый год",
    (1, 7): "Рождество Христово (православное)",
    (3, 8): "День женщин",
    (5, 1): "Праздник труда",
    (5, 9): "День Победы",
    (7, 3): "День Независимости Республики Беларусь",
    (11, 7): "День Октябрьской революции",
    (12, 25): "Рождество Христово (католическое)",
}


def generate_calendar_seed_data():
    records = []
    # Generate for years 2025 and 2026
    for year in (2025, 2026):
        current_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        while current_date <= end_date:
            month_day = (current_date.month, current_date.day)
            weekday = current_date.weekday()  # 0 = Mon, 6 = Sun

            if month_day in BELARUS_HOLIDAYS:
                is_working = False
                kind = "holiday"
                desc = BELARUS_HOLIDAYS[month_day]
            elif weekday >= 5:  # Saturday or Sunday
                is_working = False
                kind = "weekend"
                desc = "Выходной день"
            else:
                is_working = True
                kind = "workday"
                desc = "Рабочий день"

            records.append(
                {
                    "date": current_date,
                    "is_working": is_working,
                    "kind": kind,
                    "description": desc,
                }
            )
            current_date += timedelta(days=1)
    return records


def upgrade() -> None:
    day_kind_enum = sa.Enum("workday", "weekend", "holiday", name="daykind")

    calendar_table = op.create_table(
        "working_calendar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("is_working", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("kind", day_kind_enum, nullable=False, server_default="workday"),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_working_calendar_id"), "working_calendar", ["id"], unique=False)
    op.create_index(op.f("ix_working_calendar_date"), "working_calendar", ["date"], unique=True)

    # Seed calendar data
    seed_records = generate_calendar_seed_data()
    op.bulk_insert(calendar_table, seed_records)


def downgrade() -> None:
    op.drop_index(op.f("ix_working_calendar_date"), table_name="working_calendar")
    op.drop_index(op.f("ix_working_calendar_id"), table_name="working_calendar")
    op.drop_table("working_calendar")
    day_kind_enum = sa.Enum("workday", "weekend", "holiday", name="daykind")
    day_kind_enum.drop(op.get_bind(), checkfirst=True)
