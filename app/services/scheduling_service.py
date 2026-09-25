"""Scheduling engine service for CFMS (Iteration 4)."""

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.models import (
    Computer,
    DayKind,
    MaintenanceEvent,
    MaintenanceEventStatus,
    Setting,
    User,
    UserRole,
    WorkingCalendar,
)
from app.services.audit_service import log_audit

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


def generate_calendar_seed_data(years: tuple[int, ...] = (2025, 2026)) -> list[dict[str, Any]]:
    records = []
    for year in years:
        current_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        while current_date <= end_date:
            month_day = (current_date.month, current_date.day)
            weekday = current_date.weekday()

            if month_day in BELARUS_HOLIDAYS:
                is_working = False
                kind = DayKind.HOLIDAY
                desc = BELARUS_HOLIDAYS[month_day]
            elif weekday >= 5:
                is_working = False
                kind = DayKind.WEEKEND
                desc = "Выходной день"
            else:
                is_working = True
                kind = DayKind.WORKDAY
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


def is_working_day(target_date: date, db: Session) -> bool:
    """Single source of truth helper to check if target_date is a selectable working day."""
    entry = db.query(WorkingCalendar).filter(WorkingCalendar.date == target_date).first()
    allow_short_days = bool(get_setting_value(db, "allow_short_days", True))

    if entry:
        if entry.kind == DayKind.HOLIDAY or entry.kind == DayKind.WEEKEND or not entry.is_working:
            return False
        if entry.kind == DayKind.SHORT_DAY:
            return allow_short_days
        return True

    # Fallback to standard Mon-Fri
    return target_date.weekday() < 5


def compute_window_bounds(trigger_date: date, db: Session) -> tuple[date, date, date]:
    """Compute (window_start, window_end, prompt_start_date) centered on trigger_date."""
    selection_window_days = int(get_setting_value(db, "selection_window_days", 20))
    prompt_start_offset_days = int(get_setting_value(db, "prompt_start_offset_days", selection_window_days // 2))

    half_window = selection_window_days // 2
    window_start = trigger_date - timedelta(days=half_window)
    window_end = trigger_date + timedelta(days=half_window)
    prompt_start_date = trigger_date - timedelta(days=prompt_start_offset_days)

    return window_start, window_end, prompt_start_date


def compute_available_dates(
    computer_id: int, db: Session, today: date | None = None, locale: str = "ru"
) -> dict[str, Any]:
    """Single source of truth function for available, selectable, and blocked maintenance dates."""
    if today is None:
        today = datetime.now(timezone.utc).date()

    from app.core.i18n import format_date_localized

    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return {
            "window_start": None,
            "window_end": None,
            "prompt_start": None,
            "selectable": [],
            "blocked": [],
            "days": [],
            "has_selectable": False,
        }

    if not computer.next_maintenance_due_at:
        computer.next_maintenance_due_at = compute_next_maintenance_due_at(computer, db)
        db.add(computer)
        db.commit()

    trigger_date = (
        computer.next_maintenance_due_at.date()
        if isinstance(computer.next_maintenance_due_at, datetime)
        else computer.next_maintenance_due_at
    )

    window_start, window_end, prompt_start_date = compute_window_bounds(trigger_date, db)
    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()
    capacity_per_tech = int(get_setting_value(db, "technician_daily_capacity", 1))

    entries = (
        db.query(WorkingCalendar)
        .filter(WorkingCalendar.date >= window_start, WorkingCalendar.date <= window_end)
        .all()
    )
    entry_map = {e.date: e for e in entries}

    days = []
    selectable_dates = []
    blocked_dates = []
    has_selectable = False

    curr_d = window_start
    while curr_d <= window_end:
        if curr_d.weekday() == 6:  # Exclude Sunday completely
            curr_d += timedelta(days=1)
            continue

        is_work = is_working_day(curr_d, db)
        is_future = curr_d > today

        # Check if same computer is booked
        comp_booked = (
            db.query(MaintenanceEvent)
            .filter(
                MaintenanceEvent.computer_id == computer_id,
                MaintenanceEvent.scheduled_date == curr_d,
                MaintenanceEvent.status.in_([MaintenanceEventStatus.PLANNED, MaintenanceEventStatus.IN_PROGRESS]),
            )
            .first()
            is not None
        )

        # Check technician capacity
        assigned_events = (
            db.query(MaintenanceEvent.technician_id, func.count(MaintenanceEvent.id).label("event_count"))
            .filter(
                MaintenanceEvent.scheduled_date == curr_d,
                MaintenanceEvent.status.in_([MaintenanceEventStatus.PLANNED, MaintenanceEventStatus.IN_PROGRESS]),
            )
            .group_by(MaintenanceEvent.technician_id)
            .all()
        )
        tech_load = {tech_id: count for tech_id, count in assigned_events}
        has_tech_capacity = any(tech_load.get(tech.id, 0) < capacity_per_tech for tech in technicians)

        entry = entry_map.get(curr_d)
        is_holiday = bool(entry and (entry.kind == DayKind.HOLIDAY or getattr(entry.kind, "value", str(entry.kind)) == "holiday"))

        disabled_reason = None
        block_code = None
        if not is_future:
            disabled_reason = "Прошедшая дата" if locale == "ru" else "Past date"
            block_code = "past"
        elif is_holiday:
            disabled_reason = "Праздник" if locale == "ru" else "Holiday"
            block_code = "holiday"
        elif not is_work:
            disabled_reason = "Выходной" if locale == "ru" else "Weekend"
            block_code = "weekend"
        elif comp_booked:
            disabled_reason = "Занято для этого ПК" if locale == "ru" else "Already booked"
            block_code = "booked"
        elif not has_tech_capacity:
            disabled_reason = "Нет свободных техников" if locale == "ru" else "No available technicians"
            block_code = "capacity_full"

        is_selectable = is_future and is_work and not comp_booked and has_tech_capacity
        d_str = curr_d.isoformat()

        if is_selectable:
            has_selectable = True
            selectable_dates.append(d_str)
        else:
            blocked_dates.append({"date": d_str, "reason": block_code or "disabled"})

        days.append(
            {
                "date": curr_d,
                "date_str": d_str,
                "formatted": format_date_localized(curr_d, locale=locale),
                "is_selectable": is_selectable,
                "disabled_reason": disabled_reason,
            }
        )
        curr_d += timedelta(days=1)

    # Empty window escalation
    if not has_selectable and today >= prompt_start_date:
        log_audit(
            db=db,
            actor_user_id=None,
            action="escalate_empty_window",
            entity="computers",
            entity_id=computer.id,
            after={
                "message": "Selection window has no available working dates",
                "trigger_date": trigger_date.isoformat(),
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
            },
        )

    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "prompt_start": prompt_start_date.isoformat(),
        "selectable": selectable_dates,
        "blocked": blocked_dates,
        "days": days,
        "has_selectable": has_selectable,
    }


def get_window_calendar_days(computer_id: int, db: Session, today: date | None = None, locale: str = "ru") -> dict[str, Any]:
    """Wrapper returning compute_available_dates for calendar template rendering."""
    return compute_available_dates(computer_id, db, today=today, locale=locale)


def get_setting_value(db: Session, key: str, default: Any) -> Any:
    """Retrieve configuration setting from single-row/keyed settings table."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting and setting.value_json is not None:
        return setting.value_json
    return default


def compute_next_maintenance_due_at(computer: Computer, db: Session, base_date: date | None = None) -> date:
    """Compute next_maintenance_due_at based on computer RTC status and settings intervals."""
    interval_rtc = int(get_setting_value(db, "interval_rtc_months", 6))
    interval_non_rtc = int(get_setting_value(db, "interval_non_rtc_months", 12))

    months_to_add = interval_rtc if computer.is_round_the_clock else interval_non_rtc

    if base_date is None:
        if computer.last_maintenance_at:
            base_date = (
                computer.last_maintenance_at.date()
                if isinstance(computer.last_maintenance_at, datetime)
                else computer.last_maintenance_at
            )
        else:
            base_date = datetime.now(timezone.utc).date()

    # Add months
    year = base_date.year + (base_date.month + months_to_add - 1) // 12
    month = (base_date.month + months_to_add - 1) % 12 + 1
    # Handle end of month boundary
    day = min(base_date.day, 28)
    return date(year, month, day)


def is_notification_window_open(computer: Computer, db: Session, today: date | None = None) -> bool:
    """Check if today is within the active notification window for picking a maintenance date."""
    if today is None:
        today = datetime.now(timezone.utc).date()

    if not computer.next_maintenance_due_at:
        computer.next_maintenance_due_at = compute_next_maintenance_due_at(computer, db)
        db.add(computer)

    due_date = (
        computer.next_maintenance_due_at.date()
        if isinstance(computer.next_maintenance_due_at, datetime)
        else computer.next_maintenance_due_at
    )
    window_days = int(get_setting_value(db, "selection_window_days", 20))

    window_start = due_date - timedelta(days=window_days)
    return today >= window_start


def get_available_dates(
    computer_id: int, db: Session, today: date | None = None, days_ahead: int = 30
) -> list[dict[str, Any]]:
    """Get list of future working days with available technician capacity."""
    if today is None:
        today = datetime.now(timezone.utc).date()

    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return []

    # Get active technicians
    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()
    if not technicians:
        return []

    capacity_per_tech = int(get_setting_value(db, "technician_daily_capacity", 1))

    if not computer.next_maintenance_due_at:
        computer.next_maintenance_due_at = compute_next_maintenance_due_at(computer, db)
        db.add(computer)
        db.commit()

    due_date = (
        computer.next_maintenance_due_at.date()
        if isinstance(computer.next_maintenance_due_at, datetime)
        else computer.next_maintenance_due_at
    )

    end_date = (
        min(today + timedelta(days=days_ahead), due_date) if due_date >= today else today + timedelta(days=days_ahead)
    )

    # Query calendar for future dates
    calendar_entries = (
        db.query(WorkingCalendar)
        .filter(WorkingCalendar.date > today, WorkingCalendar.date <= end_date, WorkingCalendar.is_working == True)
        .order_by(WorkingCalendar.date.asc())
        .all()
    )

    available_dates = []

    for entry in calendar_entries:
        cal_date = entry.date

        # Check technician loads on cal_date
        assigned_events = (
            db.query(MaintenanceEvent.technician_id, func.count(MaintenanceEvent.id).label("event_count"))
            .filter(
                MaintenanceEvent.scheduled_date == cal_date,
                MaintenanceEvent.status.in_([MaintenanceEventStatus.PLANNED, MaintenanceEventStatus.IN_PROGRESS]),
            )
            .group_by(MaintenanceEvent.technician_id)
            .all()
        )

        tech_load = {tech_id: count for tech_id, count in assigned_events}

        # Check if at least one technician has remaining capacity
        has_capacity = any(tech_load.get(tech.id, 0) < capacity_per_tech for tech in technicians)

        if has_capacity:
            available_dates.append(
                {
                    "date": cal_date,
                    "date_str": cal_date.isoformat(),
                    "formatted": cal_date.strftime("%d.%m.%Y (%A)"),
                    "is_working": entry.is_working,
                    "description": entry.description or "",
                }
            )

    return available_dates


def validate_maintenance_date(
    computer_id: int, target_date: date, db: Session, today: date | None = None
) -> tuple[bool, str | None]:
    """Validate if target_date can be scheduled for computer_id using compute_available_dates as single source of truth."""
    if today is None:
        today = datetime.now(timezone.utc).date()

    if target_date <= today:
        return False, "Выберите будущую дату"

    if not is_working_day(target_date, db):
        return False, "Выбранный день является выходным или праздничным"

    data = compute_available_dates(computer_id, db, today=today)
    target_str = target_date.isoformat()

    if target_str in data["selectable"]:
        return True, None

    for item in data["blocked"]:
        if item["date"] == target_str:
            reason = item["reason"]
            if reason == "past":
                return False, "Выберите будущую дату"
            if reason == "weekend":
                return False, "Выбранный день является выходным или праздничным"
            if reason == "booked":
                return False, "Эта дата уже забронирована для данного компьютера"
            if reason == "capacity_full":
                return False, "На выбранную дату нет свободных техников"

    return False, "Дата находится за пределами допустимого окна выбора"


def schedule_maintenance(computer_id: int, selected_date: date, user_id: int, db: Session) -> MaintenanceEvent:
    """Schedule a maintenance event for computer on selected_date, assigning an available technician."""
    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        raise ValueError("Computer not found")

    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()
    if not technicians:
        raise ValueError("No active technicians available")

    capacity_per_tech = int(get_setting_value(db, "technician_daily_capacity", 1))

    # Find technician with capacity on selected_date
    assigned_tech = None
    for tech in technicians:
        current_count = (
            db.query(func.count(MaintenanceEvent.id))
            .filter(
                MaintenanceEvent.technician_id == tech.id,
                MaintenanceEvent.scheduled_date == selected_date,
                MaintenanceEvent.status.in_([MaintenanceEventStatus.PLANNED, MaintenanceEventStatus.IN_PROGRESS]),
            )
            .scalar()
            or 0
        )

        if current_count < capacity_per_tech:
            assigned_tech = tech
            break

    if not assigned_tech:
        raise ValueError(f"No technician capacity available on {selected_date}")

    # Check if there is already a planned event for this computer
    existing = (
        db.query(MaintenanceEvent)
        .filter(MaintenanceEvent.computer_id == computer_id, MaintenanceEvent.status == MaintenanceEventStatus.PLANNED)
        .first()
    )

    if existing:
        before_json = {"scheduled_date": existing.scheduled_date.isoformat(), "technician_id": existing.technician_id}
        existing.scheduled_date = selected_date
        existing.technician_id = assigned_tech.id
        existing.updated_at = datetime.now(timezone.utc)
        event = existing
        log_audit(
            db=db,
            actor_user_id=user_id,
            action="reschedule_maintenance_event",
            entity="maintenance_events",
            entity_id=event.id,
            before=before_json,
            after={"scheduled_date": selected_date.isoformat(), "technician_id": assigned_tech.id},
        )
    else:
        event = MaintenanceEvent(
            computer_id=computer_id,
            technician_id=assigned_tech.id,
            scheduled_date=selected_date,
            status=MaintenanceEventStatus.PLANNED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(event)
        db.flush()
        log_audit(
            db=db,
            actor_user_id=user_id,
            action="create_maintenance_event",
            entity="maintenance_events",
            entity_id=event.id,
            after={
                "computer_id": computer_id,
                "scheduled_date": selected_date.isoformat(),
                "technician_id": assigned_tech.id,
                "status": "planned",
            },
        )

    db.commit()
    return event


def process_unselected_windows(db: Session, today: date | None = None) -> int:
    """Shift next_maintenance_due_at forward by 30 days for computers whose notification window expired without a date choice."""
    if today is None:
        today = datetime.now(timezone.utc).date()

    shifted_count = 0
    computers = db.query(Computer).filter(Computer.status == "active").all()

    for comp in computers:
        if not comp.next_maintenance_due_at:
            comp.next_maintenance_due_at = compute_next_maintenance_due_at(comp, db)
            db.add(comp)
            continue

        due_date = (
            comp.next_maintenance_due_at.date()
            if isinstance(comp.next_maintenance_due_at, datetime)
            else comp.next_maintenance_due_at
        )

        # Check if due date has passed without a planned or completed event for this cycle
        if today > due_date:
            has_planned = (
                db.query(MaintenanceEvent)
                .filter(
                    MaintenanceEvent.computer_id == comp.id,
                    MaintenanceEvent.status.in_([MaintenanceEventStatus.PLANNED, MaintenanceEventStatus.IN_PROGRESS]),
                )
                .first()
            )

            if not has_planned:
                before_date = comp.next_maintenance_due_at
                comp.next_maintenance_due_at = due_date + timedelta(days=30)
                shifted_count += 1
                log_audit(
                    db=db,
                    actor_user_id=None,
                    action="escalate_window_expiry_shift",
                    entity="computers",
                    entity_id=comp.id,
                    before={
                        "next_maintenance_due_at": before_date.isoformat()
                        if isinstance(before_date, date)
                        else str(before_date)
                    },
                    after={"next_maintenance_due_at": comp.next_maintenance_due_at.isoformat()},
                )

    db.commit()
    return shifted_count


def get_month_calendar_grid(year: int, month: int, db: Session, current_date: date | None = None) -> dict[str, Any]:
    """Calculate Monday-first 7-column calendar grid for a given year/month bounded to current_year .. current_year + 10."""
    if current_date is None:
        current_date = datetime.now(timezone.utc).date()

    curr_year = current_date.year
    min_year = curr_year
    max_year = curr_year + 10

    if year < min_year:
        year = min_year
    elif year > max_year:
        year = max_year

    if not (1 <= month <= 12):
        month = current_date.month

    first_day = date(year, month, 1)
    _, num_days = calendar.monthrange(year, month)

    # Monday = 0, Tuesday = 1, ..., Sunday = 6
    leading_blanks = first_day.weekday()

    start_d = date(year, month, 1)
    end_d = date(year, month, num_days)
    entries = db.query(WorkingCalendar).filter(
        WorkingCalendar.date >= start_d, WorkingCalendar.date <= end_d
    ).all()
    entry_map = {e.date: e for e in entries}

    days_cells = []
    for _ in range(leading_blanks):
        days_cells.append(None)

    for d in range(1, num_days + 1):
        c_date = date(year, month, d)
        entry = entry_map.get(c_date)
        if not entry:
            is_w = c_date.weekday() < 5
            k = DayKind.WORKDAY if is_w else DayKind.WEEKEND
            entry = WorkingCalendar(date=c_date, is_working=is_w, kind=k, description="", source="seed")

        kind_val = entry.kind.value if hasattr(entry.kind, "value") else str(entry.kind)
        days_cells.append({
            "date": c_date,
            "day_number": d,
            "entry": entry,
            "kind": kind_val,
            "is_working": entry.is_working,
            "description": entry.description or "",
            "is_today": (c_date == current_date),
            "is_weekend": (c_date.weekday() >= 5),
        })

    total_cells = len(days_cells)
    remainder = total_cells % 7
    trailing_blanks = (7 - remainder) % 7
    for _ in range(trailing_blanks):
        days_cells.append(None)

    weeks = [days_cells[i : i + 7] for i in range(0, len(days_cells), 7)]

    if month == 1:
        prev_month = 12
        prev_year = year - 1 if year > min_year else min_year
    else:
        prev_month = month - 1
        prev_year = year

    if month == 12:
        next_month = 1
        next_year = year + 1 if year < max_year else max_year
    else:
        next_month = month + 1
        next_year = year

    return {
        "year": year,
        "month": month,
        "weeks": weeks,
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
        "min_year": min_year,
        "max_year": max_year,
        "leading_blanks": leading_blanks,
        "num_days": num_days,
        "trailing_blanks": trailing_blanks,
    }


def get_date_picker_grid(
    year: int, month: int, db: Session, locale: str = "ru", current_date: date | None = None
) -> dict[str, Any]:
    """Calculate 3+3 grid (6 cells per week: Row 1 = Mon/Tue/Wed, Row 2 = Thu/Fri/Sat) excluding Sunday."""
    if current_date is None:
        current_date = datetime.now(timezone.utc).date()

    curr_year = current_date.year
    min_year = curr_year
    max_year = curr_year + 10

    if year < min_year:
        year = min_year
    elif year > max_year:
        year = max_year

    if not (1 <= month <= 12):
        month = current_date.month

    from app.core.i18n import WEEK_LAYOUT, WEEKDAYS_6_EN, WEEKDAYS_6_RU, format_date_localized

    _, num_days = calendar.monthrange(year, month)

    month_days = []
    for d in range(1, num_days + 1):
        c_date = date(year, month, d)
        if c_date.weekday() != 6:  # Skip Sunday
            month_days.append(c_date)

    if not month_days:
        leading_blanks = 0
    else:
        first_mon_sat = month_days[0]
        leading_blanks = first_mon_sat.weekday()  # 0 for Mon, 1 for Tue, ..., 5 for Sat

    start_d = date(year, month, 1)
    end_d = date(year, month, num_days)
    entries = db.query(WorkingCalendar).filter(
        WorkingCalendar.date >= start_d, WorkingCalendar.date <= end_d
    ).all()
    entry_map = {e.date: e for e in entries}

    cells = []
    for _ in range(leading_blanks):
        cells.append(None)

    for c_date in month_days:
        entry = entry_map.get(c_date)
        if not entry:
            is_w = c_date.weekday() < 5
            k = DayKind.WORKDAY if is_w else DayKind.WEEKEND
            entry = WorkingCalendar(date=c_date, is_working=is_w, kind=k, description="", source="seed")

        kind_val = entry.kind.value if hasattr(entry.kind, "value") else str(entry.kind)
        cells.append({
            "date": c_date,
            "date_str": c_date.isoformat(),
            "day_number": c_date.day,
            "formatted": format_date_localized(c_date, locale=locale),
            "entry": entry,
            "kind": kind_val,
            "is_working": entry.is_working,
            "description": entry.description or "",
            "is_today": (c_date == current_date),
            "is_weekend": (c_date.weekday() == 5),
        })

    total_cells = len(cells)
    remainder = total_cells % 6
    trailing_blanks = (6 - remainder) % 6
    for _ in range(trailing_blanks):
        cells.append(None)

    weeks_6 = []
    for i in range(0, len(cells), 6):
        block = cells[i : i + 6]
        weeks_6.append({
            "row1": block[0:3],
            "row2": block[3:6],
        })

    weekday_headers = WEEKDAYS_6_EN if locale == "en" else WEEKDAYS_6_RU

    return {
        "year": year,
        "month": month,
        "weeks": weeks_6,
        "week_layout": WEEK_LAYOUT,
        "header_row1": weekday_headers[0:3],
        "header_row2": weekday_headers[3:6],
        "num_days": num_days,
        "visible_days_count": len(month_days),
        "leading_blanks": leading_blanks,
        "trailing_blanks": trailing_blanks,
    }
