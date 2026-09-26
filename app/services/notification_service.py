"""Backend notification processing service for CFMS (Iteration 4)."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import (
    Computer,
    MaintenanceEvent,
    MaintenanceEventStatus,
    Notification,
    User,
    UserRole,
)
from app.services.scheduling_service import (
    compute_next_maintenance_due_at,
    compute_window_bounds,
)


def create_notification(
    db: Session,
    user_id: int,
    computer_id: int | None = None,
    event_id: int | None = None,
    channel: str = "windows_agent",
    payload: dict[str, Any] | None = None,
) -> Notification:
    """Create and persist a notification entry for auditability."""
    notif = Notification(
        user_id=user_id,
        computer_id=computer_id,
        event_id=event_id,
        channel=channel,
        payload_json=payload or {},
        sent_at=datetime.now(timezone.utc),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def process_daily_notifications(db: Session, today: datetime | None = None) -> list[Notification]:
    """Process daily reminders and escalations for computers in active notification windows.
    Idempotent: creates at most one reminder notification per user per computer per calendar day.
    """
    if today is None:
        today_d = datetime.now(timezone.utc).date()
    elif isinstance(today, datetime):
        today_d = today.date()
    else:
        today_d = today

    created_notifications = []
    active_computers = db.query(Computer).filter(Computer.status == "active").all()
    techs_and_admins = db.query(User).filter(User.role.in_([UserRole.ADMIN, UserRole.TECHNICIAN]), User.is_active == True).all()

    for comp in active_computers:
        if not comp.owner_user_id:
            continue

        if not comp.next_maintenance_due_at:
            comp.next_maintenance_due_at = compute_next_maintenance_due_at(comp, db)
            db.add(comp)
            db.commit()

        due_date = (
            comp.next_maintenance_due_at.date()
            if isinstance(comp.next_maintenance_due_at, datetime)
            else comp.next_maintenance_due_at
        )

        window_start, window_end, prompt_start_date = compute_window_bounds(due_date, db)

        # Check if today is within prompt window [prompt_start_date .. window_end]
        if prompt_start_date <= today_d <= window_end:
            # Check if user already picked a date
            planned = (
                db.query(MaintenanceEvent)
                .filter(
                    MaintenanceEvent.computer_id == comp.id,
                    MaintenanceEvent.status == MaintenanceEventStatus.PLANNED,
                )
                .first()
            )

            if not planned:
                # Idempotency check: check if reminder already sent today
                start_of_day = datetime.combine(today_d, datetime.min.time(), tzinfo=timezone.utc)
                end_of_day = datetime.combine(today_d, datetime.max.time(), tzinfo=timezone.utc)

                sent_today = (
                    db.query(Notification)
                    .filter(
                        Notification.user_id == comp.owner_user_id,
                        Notification.computer_id == comp.id,
                        Notification.sent_at >= start_of_day,
                        Notification.sent_at <= end_of_day,
                    )
                    .first()
                )

                if not sent_today:
                    notif = create_notification(
                        db=db,
                        user_id=comp.owner_user_id,
                        computer_id=comp.id,
                        payload={
                            "type": "daily_reminder",
                            "computer_hostname": comp.hostname,
                            "due_date": due_date.isoformat(),
                            "window_end": window_end.isoformat(),
                            "message": f"Пожалуйста, выберите дату технического обслуживания для {comp.hostname}.",
                        },
                    )
                    created_notifications.append(notif)

        # Window expired escalation
        elif today_d > window_end:
            planned = (
                db.query(MaintenanceEvent)
                .filter(
                    MaintenanceEvent.computer_id == comp.id,
                    MaintenanceEvent.status.in_([MaintenanceEventStatus.PLANNED, MaintenanceEventStatus.IN_PROGRESS]),
                )
                .first()
            )

            if not planned:
                # Escalate to technicians and admins
                for recipient in techs_and_admins:
                    start_of_day = datetime.combine(today_d, datetime.min.time(), tzinfo=timezone.utc)
                    end_of_day = datetime.combine(today_d, datetime.max.time(), tzinfo=timezone.utc)

                    escalated_today = (
                        db.query(Notification)
                        .filter(
                            Notification.user_id == recipient.id,
                            Notification.computer_id == comp.id,
                            Notification.sent_at >= start_of_day,
                            Notification.sent_at <= end_of_day,
                        )
                        .first()
                    )

                    if not escalated_today:
                        notif = create_notification(
                            db=db,
                            user_id=recipient.id,
                            computer_id=comp.id,
                            payload={
                                "type": "window_expired_escalation",
                                "computer_hostname": comp.hostname,
                                "due_date": due_date.isoformat(),
                                "message": f"Окно выбора даты ТО для {comp.hostname} истекло без выбора даты пользователем.",
                            },
                        )
                        created_notifications.append(notif)

    return created_notifications
