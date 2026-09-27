"""Unit & Integration tests for Technician features and Iteration 5 requirements."""

import io
from datetime import date, datetime, timezone

import pytest
from app.auth.providers import LocalAuthProvider
from app.models.models import (
    Computer,
    MaintenanceEvent,
    MaintenanceEventAttachment,
    MaintenanceEventCheck,
    MaintenanceEventStatus,
    MaintenanceProtocolItem,
)
from app.services.notification_service import generate_technician_daily_digests


@pytest.fixture
def test_computer(db_session):
    comp = Computer(
        hostname="WORKSTATION-99",
        ip="192.168.1.99",
        mac="00:11:22:33:44:99",
        os="Windows 11 Pro",
        location="Room 303",
        is_round_the_clock=False,
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)
    return comp


@pytest.fixture
def sample_protocol_items(db_session):
    item1 = MaintenanceProtocolItem(
        order_index=1,
        title_ru="Очистка от пыли",
        title_en="Dust cleaning",
        description="Продувка системного блока",
        is_active=True,
    )
    item2 = MaintenanceProtocolItem(
        order_index=2,
        title_ru="Проверка HDD/SSD",
        title_en="Check HDD/SSD",
        description="Проверка SMART параметров",
        is_active=True,
    )
    db_session.add_all([item1, item2])
    db_session.commit()
    db_session.refresh(item1)
    db_session.refresh(item2)
    return [item1, item2]


def test_technician_schedule_view(client, tech_user, test_computer, db_session):
    """Test day view schedule for technician."""
    client.post("/auth/login", data={"username": "tech@cfms.local", "password": "tech123"})

    today_d = date.today()
    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=today_d,
        status=MaintenanceEventStatus.PLANNED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    resp = client.get("/technician/schedule")
    assert resp.status_code == 200
    assert "WORKSTATION-99" in resp.text
    assert "График техника" in resp.text


def test_technician_week_view(client, tech_user, test_computer, db_session):
    """Test week view schedule for technician."""
    client.post("/auth/login", data={"username": "tech@cfms.local", "password": "tech123"})

    today_d = date.today()
    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=today_d,
        status=MaintenanceEventStatus.PLANNED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    resp = client.get("/technician/week")
    assert resp.status_code == 200
    assert "WORKSTATION-99" in resp.text
    assert "Неделя" in resp.text


def test_unplanned_event_creation(client, tech_user, test_computer, db_session):
    """Test creating an unplanned event by technician."""
    client.post("/auth/login", data={"username": "tech@cfms.local", "password": "tech123"})

    today_d = date.today().isoformat()
    resp = client.post(
        "/technician/unplanned",
        data={
            "computer_id": test_computer.id,
            "scheduled_date": today_d,
            "scheduled_slot": "14:00 - 15:00",
            "comment": "Срочный ремонт кулера",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert "Внеплановое ТО успешно создано" in resp.text

    event = db_session.query(MaintenanceEvent).filter(MaintenanceEvent.computer_id == test_computer.id).first()
    assert event is not None
    assert event.is_unplanned is True
    assert event.technician_id == tech_user.id
    assert event.comment == "Срочный ремонт кулера"


def test_event_start_and_finish_transitions(client, tech_user, test_computer, sample_protocol_items, db_session):
    """Test event start transition and finishing event with checklist verification and next due date recalculation."""
    client.post("/auth/login", data={"username": "tech@cfms.local", "password": "tech123"})

    today_d = date.today()
    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=today_d,
        status=MaintenanceEventStatus.PLANNED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    # 1. Start event
    resp_start = client.post(f"/technician/events/{event.id}/start", follow_redirects=True)
    assert resp_start.status_code == 200
    assert "Обслуживание начато" in resp_start.text

    db_session.refresh(event)
    assert event.status == MaintenanceEventStatus.IN_PROGRESS
    assert event.started_at is not None

    # 2. Try finish without checking item 2 -> should fail with error
    item1, item2 = sample_protocol_items
    resp_finish_incomplete = client.post(
        f"/technician/events/{event.id}/finish",
        data={
            f"check_{item1.id}": "done",
            f"comment_{item1.id}": "Пыль убрана",
        },
        follow_redirects=True,
    )
    assert resp_finish_incomplete.status_code == 200
    assert "все активные пункты" in resp_finish_incomplete.text or "все пункты" in resp_finish_incomplete.text

    # 3. Complete finish with all items checked
    resp_finish = client.post(
        f"/technician/events/{event.id}/finish",
        data={
            f"check_{item1.id}": "done",
            f"comment_{item1.id}": "Пыль убрана",
            f"check_{item2.id}": "done",
            f"comment_{item2.id}": "SMART OK",
            "comment": "Всё работает отлично",
        },
        follow_redirects=True,
    )
    assert resp_finish.status_code == 200
    assert "Обслуживание успешно завершено" in resp_finish.text

    db_session.refresh(event)
    db_session.refresh(test_computer)

    assert event.status == MaintenanceEventStatus.DONE
    assert event.finished_at is not None
    assert event.comment == "Всё работает отлично"

    # Check maintenance checks saved
    checks = db_session.query(MaintenanceEventCheck).filter(MaintenanceEventCheck.event_id == event.id).all()
    assert len(checks) == 2
    assert all(c.is_done for c in checks)

    # Verify computer dates recalculated
    assert test_computer.last_maintenance_at is not None
    assert test_computer.next_maintenance_due_at is not None


def test_mark_event_as_missed(client, tech_user, test_computer, db_session):
    """Test marking an event as missed with mandatory reason."""
    client.post("/auth/login", data={"username": "tech@cfms.local", "password": "tech123"})

    today_d = date.today()
    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=today_d,
        status=MaintenanceEventStatus.PLANNED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    # Empty reason -> should fail
    resp_empty = client.post(
        f"/technician/events/{event.id}/missed",
        data={"reason": "   "},
        follow_redirects=True,
    )
    assert "Причина пропуска обязательна" in resp_empty.text

    # Valid reason
    resp_missed = client.post(
        f"/technician/events/{event.id}/missed",
        data={"reason": "Пользователь был на больничном"},
        follow_redirects=True,
    )
    assert resp_missed.status_code == 200
    assert "Отмечено как пропущенное" in resp_missed.text

    db_session.refresh(event)
    assert event.status == MaintenanceEventStatus.MISSED
    assert "Пользователь был на больничном" in event.comment


def test_attachment_upload(client, tech_user, test_computer, db_session):
    """Test attachment file upload for an event."""
    client.post("/auth/login", data={"username": "tech@cfms.local", "password": "tech123"})

    today_d = date.today()
    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=today_d,
        status=MaintenanceEventStatus.IN_PROGRESS,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    file_content = b"Sample diagnostic report text content"
    file_tuple = ("report.txt", io.BytesIO(file_content), "text/plain")

    resp = client.post(
        f"/technician/events/{event.id}/attachments",
        files={"file": file_tuple},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert "Файл успешно загружен" in resp.text

    attachment = db_session.query(MaintenanceEventAttachment).filter(MaintenanceEventAttachment.event_id == event.id).first()
    assert attachment is not None
    assert attachment.filename == "report.txt"
    assert attachment.mime == "text/plain"


def test_technician_daily_digest_notification(db_session, tech_user, test_computer):
    """Test generating daily schedule digest for technician."""
    today_d = date.today()
    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=today_d,
        status=MaintenanceEventStatus.PLANNED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()

    notifs = generate_technician_daily_digests(db_session, today_d)
    assert len(notifs) == 1
    assert notifs[0].user_id == tech_user.id
    assert notifs[0].payload_json["type"] == "technician_daily_digest"
    assert notifs[0].payload_json["event_count"] == 1

    # Idempotency check: running again on same day should produce no new digests
    notifs_again = generate_technician_daily_digests(db_session, today_d)
    assert len(notifs_again) == 0
