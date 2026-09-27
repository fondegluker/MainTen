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


def generate_technician_daily_digests(db: Session, today: datetime | None = None) -> list[Notification]:
    """Generate daily schedule digests for active technicians."""
    if today is None:
        today_d = datetime.now(timezone.utc).date()
    elif isinstance(today, datetime):
        today_d = today.date()
    else:
        today_d = today

    created = []
    technicians = db.query(User).filter(User.role == UserRole.TECHNICIAN, User.is_active == True).all()

    start_of_day = datetime.combine(today_d, datetime.min.time(), tzinfo=timezone.utc)
    end_of_day = datetime.combine(today_d, datetime.max.time(), tzinfo=timezone.utc)

    for tech in technicians:
        events = (
            db.query(MaintenanceEvent)
            .filter(
                MaintenanceEvent.technician_id == tech.id,
                MaintenanceEvent.scheduled_date == today_d,
            )
            .all()
        )
        if not events:
            continue

        sent_today = (
            db.query(Notification)
            .filter(
                Notification.user_id == tech.id,
                Notification.sent_at >= start_of_day,
                Notification.sent_at <= end_of_day,
            )
            .all()
        )
        has_digest = any(
            n.payload_json and n.payload_json.get("type") == "technician_daily_digest"
            for n in sent_today
        )

        if not has_digest:
            hostnames = [e.computer.hostname for e in events if e.computer]
            notif = create_notification(
                db=db,
                user_id=tech.id,
                payload={
                    "type": "technician_daily_digest",
                    "date": today_d.isoformat(),
                    "event_count": len(events),
                    "computers": hostnames,
                    "message": f"Ваш график на сегодня ({today_d.isoformat()}): {len(events)} мероприятий ТО.",
                },
            )
            created.append(notif)

    return created


def process_daily_notifications(db: Session, today: datetime | None = None) -> list[Notification]:
    """Process daily reminders and escalations for computers in active notification windows,
    as well as technician daily schedule digests.
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

    digest_notifications = generate_technician_daily_digests(db, today_d)
    created_notifications.extend(digest_notifications)

    return created_notifications
