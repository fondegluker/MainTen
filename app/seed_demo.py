"""Deterministic demo data seeding script for CFMS."""

import argparse
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth.providers import LocalAuthProvider
from app.core.database import SessionLocal
from app.models.models import (
    Computer,
    DayKind,
    MaintenanceEvent,
    MaintenanceEventCheck,
    MaintenanceEventStatus,
    MaintenanceProtocolItem,
    User,
    UserRole,
    WorkingCalendar,
)
from app.services.scheduling_service import compute_next_maintenance_due_at

logger = logging.getLogger(__name__)


def clean_demo(db: Session) -> dict:
    """Remove demo data created by seed_demo."""
    # Find demo computers
    demo_computers = db.query(Computer).filter(Computer.hostname.like("DEMO-PC-%")).all()
    demo_comp_ids = [c.id for c in demo_computers]

    deleted_checks_count = 0
    deleted_events_count = 0

    if demo_comp_ids:
        # Find events associated with demo computers
        demo_events = db.query(MaintenanceEvent).filter(MaintenanceEvent.computer_id.in_(demo_comp_ids)).all()
        demo_event_ids = [e.id for e in demo_events]

        if demo_event_ids:
            # Delete checks
            deleted_checks_count = (
                db.query(MaintenanceEventCheck)
                .filter(MaintenanceEventCheck.event_id.in_(demo_event_ids))
                .delete(synchronize_session=False)
            )
            # Delete events
            deleted_events_count = (
                db.query(MaintenanceEvent)
                .filter(MaintenanceEvent.id.in_(demo_event_ids))
                .delete(synchronize_session=False)
            )

        # Delete demo computers
        db.query(Computer).filter(Computer.id.in_(demo_comp_ids)).delete(synchronize_session=False)

    # Delete demo users (tech_demo, user_demo)
    deleted_users_count = (
        db.query(User).filter(User.username.in_(["tech_demo", "user_demo"])).delete(synchronize_session=False)
    )

    db.commit()

    return {
        "deleted_computers": len(demo_comp_ids),
        "deleted_events": deleted_events_count,
        "deleted_checks": deleted_checks_count,
        "deleted_users": deleted_users_count,
    }


def seed_demo(db: Session) -> dict:
    """Seed deterministic demo dataset for CFMS."""
    provider = LocalAuthProvider()

    # 1. Admin (only if no ADMIN exists)
    admin = db.query(User).filter(User.role == UserRole.ADMIN).first()
    if not admin:
        admin = User(
            username="admin",
            email_or_login="admin@cfms.local",
            password_hash=provider.hash_password("admin123"),
            role=UserRole.ADMIN,
            locale="ru",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(admin)
        db.flush()

    # 2. Technician (tech_demo)
    tech_demo = db.query(User).filter(User.username == "tech_demo").first()
    if not tech_demo:
        tech_demo = User(
            username="tech_demo",
            email_or_login="tech_demo@cfms.local",
            password_hash=provider.hash_password("tech_demo123"),
            role=UserRole.TECHNICIAN,
            locale="ru",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(tech_demo)
        db.flush()

    # 3. User (user_demo)
    user_demo = db.query(User).filter(User.username == "user_demo").first()
    if not user_demo:
        user_demo = User(
            username="user_demo",
            email_or_login="user_demo@cfms.local",
            password_hash=provider.hash_password("user_demo123"),
            role=UserRole.USER,
            locale="ru",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user_demo)
        db.flush()

    db.commit()

    # 4. Working Calendar (Ensure current and next year are seeded per Belarus defaults)
    today_dt = datetime.now(timezone.utc)
    today = today_dt.date()
    start_year = today.year
    years = [start_year, start_year + 1]
    holidays_fixed = {(1, 1), (1, 7), (3, 8), (5, 1), (5, 9), (7, 3), (11, 7), (12, 25)}

    for year in years:
        curr_d = date(year, 1, 1)
        end_d = date(year, 12, 31)

        while curr_d <= end_d:
            exists = db.query(WorkingCalendar).filter(WorkingCalendar.date == curr_d).first()
            if not exists:
                if (curr_d.month, curr_d.day) in holidays_fixed:
                    kind = DayKind.HOLIDAY
                    is_work = False
                    desc = "Государственный праздник"
                elif curr_d.weekday() in (5, 6):
                    kind = DayKind.WEEKEND
                    is_work = False
                    desc = "Выходной день"
                else:
                    kind = DayKind.WORKDAY
                    is_work = True
                    desc = "Рабочий день"

                cal_entry = WorkingCalendar(
                    date=curr_d,
                    is_working=is_work,
                    kind=kind,
                    description=desc,
                )
                db.add(cal_entry)
            curr_d += timedelta(days=1)

    db.commit()

    # Helper to find next N working days from a reference date
    def get_next_working_days(start_date: date, count: int) -> list[date]:
        working_days = []
        curr = start_date
        while len(working_days) < count:
            cal = db.query(WorkingCalendar).filter(WorkingCalendar.date == curr).first()
            is_w = cal.is_working if cal else (curr.weekday() < 5)
            if is_w and curr > today:
                working_days.append(curr)
            curr += timedelta(days=1)
        return working_days

    # 5. Protocol Items (only if none exist)
    protocol_items = (
        db.query(MaintenanceProtocolItem)
        .filter(MaintenanceProtocolItem.is_active == True)
        .order_by(MaintenanceProtocolItem.order_index.asc())
        .all()
    )
    if not protocol_items:
        items_spec = [
            (0, "Визуальный осмотр и чистка", "Visual inspection & dust cleaning", "Очистка системного блока от пыли"),
            (1, "Проверка системы охлаждения", "Cooling system check", "Тестирование вентиляторов и температур"),
            (2, "Диагностика накопителей (HDD/SSD)", "Storage diagnostics", "Проверка SMART и свободного места"),
            (3, "Обновление ПО и антивируса", "OS & Antivirus updates", "Установка критических обновлений безопасности"),
            (4, "Тестирование оперативной памяти", "RAM stress test", "Проверка модулей памяти на ошибки"),
        ]
        for idx, t_ru, t_en, desc in items_spec:
            p = MaintenanceProtocolItem(
                order_index=idx,
                title_ru=t_ru,
                title_en=t_en,
                description=desc,
                is_active=True,
                created_at=today_dt,
                updated_at=today_dt,
            )
            db.add(p)
        db.commit()
        protocol_items = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.is_active == True).all()

    # 6. 5 computers owned by user_demo
    demo_computers = []
    for i in range(1, 6):
        hostname = f"DEMO-PC-0{i}"
        comp = db.query(Computer).filter(Computer.hostname == hostname).first()
        is_rtc = i in (1, 2)
        ip = f"192.168.10.1{i}"
        os_name = "Windows 11 Pro" if i % 2 == 1 else "Ubuntu 22.04"
        location = f"Room 10{i}"

        if is_rtc:
            last_maint = today_dt - timedelta(days=180 - 5)  # ~6 months - 5 days ago
        else:
            last_maint = today_dt - timedelta(days=365 - 7)  # ~12 months - 7 days ago

        if not comp:
            comp = Computer(
                hostname=hostname,
                ip=ip,
                mac=f"00:11:22:33:44:0{i}",
                os=os_name,
                location=location,
                owner_user_id=user_demo.id,
                is_round_the_clock=is_rtc,
                last_maintenance_at=last_maint,
                status="active",
                notes="seeded-by-seed_demo",
                created_at=today_dt,
            )
            db.add(comp)
            db.flush()
        else:
            comp.owner_user_id = user_demo.id
            comp.is_round_the_clock = is_rtc
            comp.last_maintenance_at = last_maint
            comp.notes = "seeded-by-seed_demo"
            db.add(comp)

        # Compute next_maintenance_due_at
        next_due_d = compute_next_maintenance_due_at(comp, db, base_date=last_maint.date())
        comp.next_maintenance_due_at = datetime.combine(next_due_d, datetime.min.time(), tzinfo=timezone.utc)

        demo_computers.append(comp)

    db.commit()

    # 7. 5 planned maintenance events + 1 unplanned event
    target_working_days = get_next_working_days(today + timedelta(days=1), 5)

    created_events = []
    for idx, comp in enumerate(demo_computers):
        sched_d = target_working_days[idx]
        event = (
            db.query(MaintenanceEvent)
            .filter(
                MaintenanceEvent.computer_id == comp.id,
                MaintenanceEvent.is_unplanned == False,
                MaintenanceEvent.status == MaintenanceEventStatus.PLANNED,
            )
            .first()
        )
        if not event:
            event = MaintenanceEvent(
                computer_id=comp.id,
                technician_id=tech_demo.id,
                scheduled_date=sched_d,
                scheduled_slot="10:00",
                status=MaintenanceEventStatus.PLANNED,
                is_unplanned=False,
                comment=f"Плановое ТО для {comp.hostname}",
                created_at=today_dt,
                updated_at=today_dt,
            )
            db.add(event)
            db.flush()

            # Pre-populate event checks
            for p_item in protocol_items:
                chk = MaintenanceEventCheck(
                    event_id=event.id,
                    protocol_item_id=p_item.id,
                    is_done=False,
                )
                db.add(chk)

        created_events.append(event)

    # Create ONE additional unplanned event on today for DEMO-PC-05
    demo_pc5 = demo_computers[4]
    unplanned_event = (
        db.query(MaintenanceEvent)
        .filter(
            MaintenanceEvent.computer_id == demo_pc5.id,
            MaintenanceEvent.is_unplanned == True,
        )
        .first()
    )
    if not unplanned_event:
        unplanned_event = MaintenanceEvent(
            computer_id=demo_pc5.id,
            technician_id=tech_demo.id,
            scheduled_date=today,
            scheduled_slot="15:00",
            status=MaintenanceEventStatus.PLANNED,
            is_unplanned=True,
            comment="Срочный вызов по замене термопасты",
            created_at=today_dt,
            updated_at=today_dt,
        )
        db.add(unplanned_event)
        db.flush()

        for p_item in protocol_items:
            chk = MaintenanceEventCheck(
                event_id=unplanned_event.id,
                protocol_item_id=p_item.id,
                is_done=False,
            )
            db.add(chk)

        created_events.append(unplanned_event)

    db.commit()

    return {
        "status": "seeded",
        "computers": [c.hostname for c in demo_computers],
        "events_count": len(created_events),
        "tech": tech_demo.username,
        "user": user_demo.username,
    }


def main():
    parser = argparse.ArgumentParser(description="Seed demo dataset for CFMS.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate demo data.")
    parser.add_argument("--clean", action="store_true", help="Remove demo data only.")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.clean:
            res = clean_demo(db)
            print(f"Cleaned demo data: {res}")
        elif args.reset:
            clean_res = clean_demo(db)
            print(f"Cleaned prior demo data: {clean_res}")
            seed_res = seed_demo(db)
            print(f"Seeded fresh demo data: {seed_res}")
        else:
            seed_res = seed_demo(db)
            print(f"Seeded demo data: {seed_res}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
