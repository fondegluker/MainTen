"""Idempotent E2E dataset seeding script for CFMS."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.auth.providers import LocalAuthProvider
from app.core.database import SessionLocal
from app.models.models import (
    Computer,
    DayKind,
    MaintenanceProtocolItem,
    User,
    UserRole,
    WorkingCalendar,
)


def seed_e2e(db: Session) -> dict:
    """Seed minimal idempotent dataset for end-to-end smoke testing."""
    provider = LocalAuthProvider()

    # 1. Users
    users_spec = [
        ("admin", "admin@cfms.local", "admin123", UserRole.ADMIN),
        ("tech_e2e", "tech_e2e@cfms.local", "tech123", UserRole.TECHNICIAN),
        ("obs_e2e", "obs_e2e@cfms.local", "obs123", UserRole.OBSERVER),
        ("user_e2e", "user_e2e@cfms.local", "user123", UserRole.USER),
    ]

    created_users = {}
    for username, email, pwd, role in users_spec:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = User(
                username=username,
                email_or_login=email,
                password_hash=provider.hash_password(pwd),
                role=role,
                is_active=True,
                locale="ru",
            )
            db.add(user)
            db.flush()
        created_users[username] = user

    db.commit()

    user_e2e = created_users["user_e2e"]

    # 2. Computers (1 RTC, 1 non-RTC)
    now_d = datetime.now(timezone.utc)
    comps_spec = [
        ("COMP-E2E-RTC", True, now_d + timedelta(days=10)),
        ("COMP-E2E-NONRTC", False, now_d + timedelta(days=10)),
    ]

    created_comps = []
    for hostname, rtc, due_dt in comps_spec:
        comp = db.query(Computer).filter(Computer.hostname == hostname).first()
        if not comp:
            comp = Computer(
                hostname=hostname,
                ip="192.168.1.100",
                mac="00:11:22:33:44:55",
                os="Windows 11 Pro",
                location="Room 101",
                owner_user_id=user_e2e.id,
                is_round_the_clock=rtc,
                status="active",
                next_maintenance_due_at=due_dt,
            )
            db.add(comp)
            db.flush()
        else:
            comp.owner_user_id = user_e2e.id
            comp.next_maintenance_due_at = due_dt
            db.add(comp)
        created_comps.append(comp)

    db.commit()

    # 3. Protocol Item
    proto = db.query(MaintenanceProtocolItem).filter(MaintenanceProtocolItem.title_en == "Check system unit").first()
    if not proto:
        proto = MaintenanceProtocolItem(
            order_index=1,
            title_ru="Проверка системного блока",
            title_en="Check system unit",
            description="Визуальный осмотр и очистка от пыли",
            is_active=True,
        )
        db.add(proto)
        db.commit()

    # 4. Working Calendar (2025 and 2026)
    start_year = datetime.now(timezone.utc).year
    years = [start_year, start_year + 1]

    for year in years:
        curr_d = date(year, 1, 1)
        end_d = date(year, 12, 31)

        # Basic Belarus holidays (fixed date samples)
        holidays_fixed = {(1, 1), (1, 7), (3, 8), (5, 1), (5, 9), (7, 3), (11, 7), (12, 25)}

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

    return {
        "status": "seeded",
        "users": list(created_users.keys()),
        "computers": [c.hostname for c in created_comps],
    }


if __name__ == "__main__":
    session = SessionLocal()
    try:
        res = seed_e2e(session)
        print(f"E2E Seeding completed successfully: {res}")
    finally:
        session.close()
