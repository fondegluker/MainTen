"""Scheduling engine service for CFMS (Iteration 4)."""

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


def get_window_calendar_days(computer_id: int, db: Session, today: date | None = None) -> dict[str, Any]:
    """Get all calendar days in selection window centered on trigger_date with selection state."""
    if today is None:
        today = datetime.now(timezone.utc).date()

    computer = db.query(Computer).filter(Computer.id == computer_id).first()
    if not computer:
        return {
            "days": [],
            "window_start": None,
            "window_end": None,
            "prompt_start_date": None,
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

    days = []
    has_selectable = False

    curr_d = window_start
    while curr_d <= window_end:
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

        disabled_reason = None
        if not is_future:
            disabled_reason = "Прошедшая дата"
        elif not is_work:
            disabled_reason = "Выходной / Праздник"
        elif comp_booked:
            disabled_reason = "Занято для этого ПК"
        elif not has_tech_capacity:
            disabled_reason = "Нет свободных техников"

        is_selectable = is_future and is_work and not comp_booked and has_tech_capacity
        if is_selectable:
            has_selectable = True

        days.append(
            {
                "date": curr_d,
                "date_str": curr_d.isoformat(),
                "formatted": curr_d.strftime("%d.%m.%Y (%a)"),
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
        "days": days,
        "window_start": window_start,
        "window_end": window_end,
        "prompt_start_date": prompt_start_date,
        "has_selectable": has_selectable,
    }


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
