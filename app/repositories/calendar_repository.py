from datetime import date

from sqlalchemy.orm import Session

from app.models.models import WorkingCalendar


class CalendarRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_day(self, target_date: date) -> WorkingCalendar | None:
        return self.db.query(WorkingCalendar).filter(WorkingCalendar.date == target_date).first()

    def is_working_day(self, target_date: date) -> bool:
        day = self.get_day(target_date)
        if day is not None:
            return day.is_working
        # Fallback to Mon-Fri if not found in table
        return target_date.weekday() < 5

    def get_working_days_range(self, start_date: date, end_date: date) -> list[WorkingCalendar]:
        return (
            self.db.query(WorkingCalendar)
            .filter(
                WorkingCalendar.date >= start_date,
                WorkingCalendar.date <= end_date,
                WorkingCalendar.is_working == True,
            )
            .order_by(WorkingCalendar.date.asc())
            .all()
        )
