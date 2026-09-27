"""Integration tests for hotfix route aliases, reports placeholder, and attachment endpoint security."""

import io
from datetime import date, datetime, timezone

import pytest
from app.auth.providers import LocalAuthProvider
from app.models.models import (
    Computer,
    MaintenanceEvent,
    MaintenanceEventAttachment,
    MaintenanceEventStatus,
    User,
    UserRole,
)


@pytest.fixture
def other_tech_user(db_session):
    provider = LocalAuthProvider()
    user = User(
        username="tech_other",
        email_or_login="tech_other@cfms.local",
        password_hash=provider.hash_password("tech123"),
        role=UserRole.TECHNICIAN,
        locale="ru",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_computer(db_session):
    comp = Computer(
        hostname="PC-HOTFIX-01",
        ip="192.168.1.150",
        mac="00:11:22:33:44:55",
        os="Windows 11",
        location="Lab 101",
        is_round_the_clock=False,
        status="active",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(comp)
    db_session.commit()
    db_session.refresh(comp)
    return comp


@pytest.fixture
def sample_event(db_session, tech_user, test_computer):
    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=date.today(),
        status=MaintenanceEventStatus.IN_PROGRESS,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


def test_technician_schedule_and_day_role_access(client, admin_user, tech_user, regular_user, observer_user):
    """Verify role access for /technician/schedule and /technician/day alias."""
    # 1. Unauthenticated -> login redirect or 401
    resp = client.get("/technician/schedule", follow_redirects=False)
    assert resp.status_code in (302, 401)

    # 2. TECHNICIAN -> 200
    client.post("/auth/login", data={"username": "tech@cfms.local", "password": "tech123"})
    resp_tech_sched = client.get("/technician/schedule")
    assert resp_tech_sched.status_code == 200
    resp_tech_day = client.get("/technician/day")
    assert resp_tech_day.status_code in (200, 302)
    resp_tech_day_date = client.get("/technician/day?date=2025-05-10")
    assert resp_tech_day_date.status_code == 200
    client.get("/auth/logout")

    # 3. ADMIN -> 200
    client.post("/auth/login", data={"username": "admin@cfms.local", "password": "admin123"})
    resp_admin_sched = client.get("/technician/schedule")
    assert resp_admin_sched.status_code == 200
    resp_admin_day = client.get("/technician/day")
    assert resp_admin_day.status_code in (200, 302)
    resp_admin_day_date = client.get("/technician/day?date=2025-05-10")
    assert resp_admin_day_date.status_code == 200
    client.get("/auth/logout")

    # 4. USER -> 403
    client.post("/auth/login", data={"username": "user@cfms.local", "password": ""}) # user login via magic or dummy session
    # Let's set cookie directly or authenticate
    # USER role
    session_cookie = f"mock_{regular_user.id}"
    client.cookies.set("session", session_cookie)
    # login as regular user using magic link session token
    from app.auth.tokens import generate_session_cookie
    tok = generate_session_cookie(regular_user.id)
    client.cookies.set("session", tok)

    assert client.get("/technician/schedule").status_code == 403
    assert client.get("/technician/day").status_code == 403
    assert client.get("/technician/day?date=2025-05-10").status_code == 403

    # 5. OBSERVER -> 403
    tok_obs = generate_session_cookie(observer_user.id)
    client.cookies.set("session", tok_obs)
    assert client.get("/technician/schedule").status_code == 403
    assert client.get("/technician/day").status_code == 403
    assert client.get("/technician/day?date=2025-05-10").status_code == 403


def test_reports_role_access_and_placeholder(client, admin_user, tech_user, regular_user, observer_user):
    """Verify /reports returns 200 with placeholder message for ADMIN, TECHNICIAN, OBSERVER, and 403 for USER."""
    from app.auth.tokens import generate_session_cookie

    # ADMIN -> 200
    client.cookies.set("session", generate_session_cookie(admin_user.id))
    resp_admin = client.get("/reports")
    assert resp_admin.status_code == 200
    assert "Отчёт" in resp_admin.text or "Reports" in resp_admin.text

    # TECHNICIAN -> 200
    client.cookies.set("session", generate_session_cookie(tech_user.id))
    resp_tech = client.get("/reports")
    assert resp_tech.status_code == 200

    # OBSERVER -> 200
    client.cookies.set("session", generate_session_cookie(observer_user.id))
    resp_obs = client.get("/reports")
    assert resp_obs.status_code == 200

    # USER -> 403
    client.cookies.set("session", generate_session_cookie(regular_user.id))
    resp_user = client.get("/reports")
    assert resp_user.status_code == 403


def test_attachment_endpoint_security_and_content_types(
    client, db_session, sample_event, tech_user, other_tech_user, admin_user, regular_user, observer_user
):
    """Verify attachment serving endpoint permission controls and content-types."""
    from app.auth.tokens import generate_session_cookie

    # Upload attachments to sample_event
    client.cookies.set("session", generate_session_cookie(tech_user.id))

    # PNG
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    client.post(
        f"/technician/events/{sample_event.id}/attachments",
        files={"file": ("photo.png", io.BytesIO(png_bytes), "image/png")},
    )

    # TXT
    txt_bytes = b"System diagnostic log content"
    client.post(
        f"/technician/events/{sample_event.id}/attachments",
        files={"file": ("log.txt", io.BytesIO(txt_bytes), "text/plain")},
    )

    # PDF
    pdf_bytes = b"%PDF-1.4 sample pdf content"
    client.post(
        f"/technician/events/{sample_event.id}/attachments",
        files={"file": ("doc.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )

    attachments = db_session.query(MaintenanceEventAttachment).filter(MaintenanceEventAttachment.event_id == sample_event.id).all()
    assert len(attachments) == 3

    png_att = next(a for a in attachments if a.filename == "photo.png")
    txt_att = next(a for a in attachments if a.filename == "log.txt")
    pdf_att = next(a for a in attachments if a.filename == "doc.pdf")

    # 1. GET as assigned TECHNICIAN -> 200 with correct Content-Type
    client.cookies.set("session", generate_session_cookie(tech_user.id))

    res_png = client.get(f"/technician/events/{sample_event.id}/attachments/{png_att.id}")
    assert res_png.status_code == 200
    assert "image/" in res_png.headers["content-type"].lower() or "png" in res_png.headers["content-type"].lower()
    assert "inline" in res_png.headers["content-disposition"].lower()

    res_txt = client.get(f"/technician/events/{sample_event.id}/attachments/{txt_att.id}")
    assert res_txt.status_code == 200
    assert "text/plain" in res_txt.headers["content-type"].lower()
    assert res_txt.headers.get("x-content-type-options") == "nosniff"

    res_pdf = client.get(f"/technician/events/{sample_event.id}/attachments/{pdf_att.id}")
    assert res_pdf.status_code == 200
    assert "pdf" in res_pdf.headers["content-type"].lower()

    # 2. GET as ADMIN -> 200
    client.cookies.set("session", generate_session_cookie(admin_user.id))
    assert client.get(f"/technician/events/{sample_event.id}/attachments/{png_att.id}").status_code == 200

    # 3. GET as another TECHNICIAN -> 403
    client.cookies.set("session", generate_session_cookie(other_tech_user.id))
    assert client.get(f"/technician/events/{sample_event.id}/attachments/{png_att.id}").status_code == 403

    # 4. GET as USER -> 403
    client.cookies.set("session", generate_session_cookie(regular_user.id))
    assert client.get(f"/technician/events/{sample_event.id}/attachments/{png_att.id}").status_code == 403

    # 5. GET as OBSERVER -> 403
    client.cookies.set("session", generate_session_cookie(observer_user.id))
    assert client.get(f"/technician/events/{sample_event.id}/attachments/{png_att.id}").status_code == 403

    # 6. Nonexistent attachment ID -> 404
    client.cookies.set("session", generate_session_cookie(tech_user.id))
    assert client.get(f"/technician/events/{sample_event.id}/attachments/999999").status_code == 404

    # 7. Attachment belonging to another event -> 404
    event2 = MaintenanceEvent(
        computer_id=sample_event.computer_id,
        technician_id=tech_user.id,
        scheduled_date=date.today(),
        status=MaintenanceEventStatus.PLANNED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event2)
    db_session.commit()

    assert client.get(f"/technician/events/{event2.id}/attachments/{png_att.id}").status_code == 404


def test_schedule_switcher_component(client, tech_user):
    """Verify schedule switcher partial presence and aria-current="page" on day, week, and month pages."""
    from app.auth.tokens import generate_session_cookie

    client.cookies.set("session", generate_session_cookie(tech_user.id))

    # 1. Day View -> active_view = 'day'
    resp_day = client.get("/technician/schedule")
    assert resp_day.status_code == 200
    assert 'aria-label="Schedule View"' in resp_day.text
    assert 'aria-current="page"' in resp_day.text

    # 2. Week View -> active_view = 'week'
    resp_week = client.get("/technician/week")
    assert resp_week.status_code == 200
    assert 'aria-label="Schedule View"' in resp_week.text
    assert 'aria-current="page"' in resp_week.text

    # 3. Month View -> active_view = 'month'
    resp_month = client.get("/technician/month")
    assert resp_month.status_code == 200
    assert 'aria-label="Schedule View"' in resp_month.text
    assert 'aria-current="page"' in resp_month.text


def test_technician_month_view_grid_alignment(client, tech_user, admin_user, regular_user, observer_user, db_session):
    """Verify 7-column weekday alignment, leading placeholders count, 32 interactive cells, next month days, and role access."""
    from app.auth.tokens import generate_session_cookie
    from app.services.scheduling_service import get_technician_month_grid

    # Check grid structure for October 2026 with align=0 (October 1, 2026 is a Thursday = weekday 3)
    today = date(2026, 10, 15)
    grid_align0 = get_technician_month_grid(2026, 10, align=False, today=today, technician_id=tech_user.id, db=db_session)
    assert grid_align0["leading_placeholders_count"] == 3  # Thu = 3 (Mon=0, Tue=1, Wed=2)
    assert len(grid_align0["date_cells"]) == 32

    # Check date cells span into next month (October has 31 days, cell 32 is Nov 1, 2026)
    last_cell = grid_align0["date_cells"][-1]
    assert last_cell["is_next_month"] is True
    assert last_cell["date"] == date(2026, 11, 1)

    # TECHNICIAN endpoint -> 200
    client.cookies.set("session", generate_session_cookie(tech_user.id))
    resp_month = client.get("/technician/month?month=2026-10&align=0")
    assert resp_month.status_code == 200
    assert "Пн" in resp_month.text or "Mon" in resp_month.text
    assert "Вс" in resp_month.text or "Sun" in resp_month.text

    # USER & OBSERVER -> 403
    client.cookies.set("session", generate_session_cookie(regular_user.id))
    assert client.get("/technician/month").status_code == 403

    client.cookies.set("session", generate_session_cookie(observer_user.id))
    assert client.get("/technician/month").status_code == 403

    # ADMIN with ?technician_id= -> 200
    client.cookies.set("session", generate_session_cookie(admin_user.id))
    resp_admin = client.get(f"/technician/month?technician_id={tech_user.id}")
    assert resp_admin.status_code == 200


def test_edit_closed_event(
    client, db_session, test_computer, tech_user, other_tech_user, admin_user, regular_user, observer_user
):
    """Verify editing closed events: permissions, audit logging, date recalculation omission, and status/field protections."""
    from app.auth.tokens import generate_session_cookie
    from app.models.models import AuditLog

    event = MaintenanceEvent(
        computer_id=test_computer.id,
        technician_id=tech_user.id,
        scheduled_date=date.today(),
        status=MaintenanceEventStatus.DONE,
        finished_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    last_maint_before = test_computer.last_maintenance_at
    next_maint_before = test_computer.next_maintenance_due_at

    # 1. TECHNICIAN edits own done event -> 200, comment updated, audit logged, computer dates UNCHANGED
    client.cookies.set("session", generate_session_cookie(tech_user.id))
    resp_edit = client.post(
        f"/technician/events/{event.id}/edit",
        data={"comment": "Обновленный комментарий техника"},
        follow_redirects=True,
    )
    assert resp_edit.status_code == 200
    assert "Изменения успешно сохранены" in resp_edit.text

    db_session.refresh(event)
    db_session.refresh(test_computer)
    assert event.comment == "Обновленный комментарий техника"
    assert test_computer.last_maintenance_at == last_maint_before
    assert test_computer.next_maintenance_due_at == next_maint_before

    audit_entry = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "edit_closed_event", AuditLog.entity_id == event.id)
        .first()
    )
    assert audit_entry is not None

    # 2. TECHNICIAN tries to change scheduled_date -> 403
    resp_tech_date = client.post(
        f"/technician/events/{event.id}/edit",
        data={"scheduled_date": "2026-01-01"},
    )
    assert resp_tech_date.status_code == 403

    # 3. TECHNICIAN tries to edit another tech's done event -> 403
    client.cookies.set("session", generate_session_cookie(other_tech_user.id))
    assert client.post(f"/technician/events/{event.id}/edit", data={"comment": "test"}).status_code == 403

    # 4. USER & OBSERVER -> 403
    client.cookies.set("session", generate_session_cookie(regular_user.id))
    assert client.post(f"/technician/events/{event.id}/edit", data={"comment": "test"}).status_code == 403

    client.cookies.set("session", generate_session_cookie(observer_user.id))
    assert client.post(f"/technician/events/{event.id}/edit", data={"comment": "test"}).status_code == 403

    # 5. ADMIN edits scheduled_date on done event -> 200, computer dates UNCHANGED
    client.cookies.set("session", generate_session_cookie(admin_user.id))
    resp_admin_date = client.post(
        f"/technician/events/{event.id}/edit",
        data={"scheduled_date": "2026-06-15"},
        follow_redirects=True,
    )
    assert resp_admin_date.status_code == 200
    db_session.refresh(event)
    db_session.refresh(test_computer)
    assert event.scheduled_date == date(2026, 6, 15)
    assert test_computer.last_maintenance_at == last_maint_before
    assert test_computer.next_maintenance_due_at == next_maint_before

    # 6. Attempt to change status via edit -> 422 rejected
    resp_status = client.post(
        f"/technician/events/{event.id}/edit",
        data={"status": "in_progress"},
    )
    assert resp_status.status_code == 422


def test_attachment_persistence_and_missing_file_handling(client, db_session, sample_event, tech_user):
    """Verify attachment volume file existence, missing file localized 404 handling, and DB row retention."""
    import os
    from app.auth.tokens import generate_session_cookie

    client.cookies.set("session", generate_session_cookie(tech_user.id))

    # 1. Upload attachment
    file_bytes = b"Sample test file content for persistence check"
    res_upload = client.post(
        f"/technician/events/{sample_event.id}/attachments",
        files={"file": ("test_persist.txt", io.BytesIO(file_bytes), "text/plain")},
        follow_redirects=True,
    )
    assert res_upload.status_code == 200

    # 2. Verify file exists on disk
    attachment = (
        db_session.query(MaintenanceEventAttachment)
        .filter(MaintenanceEventAttachment.event_id == sample_event.id, MaintenanceEventAttachment.filename == "test_persist.txt")
        .first()
    )
    assert attachment is not None
    assert os.path.exists(attachment.blob_path)

    # GET endpoint -> 200
    res_get = client.get(f"/technician/events/{sample_event.id}/attachments/{attachment.id}")
    assert res_get.status_code == 200

    # 3. Simulate missing file by removing it from disk
    os.remove(attachment.blob_path)
    assert not os.path.exists(attachment.blob_path)

    # GET endpoint -> 404 with localized error message
    res_missing = client.get(f"/technician/events/{sample_event.id}/attachments/{attachment.id}")
    assert res_missing.status_code == 404
    assert "не найден на сервере" in res_missing.text or "not found on the server" in res_missing.text

    # 4. Verify database row still exists (no auto-deletion)
    db_session.refresh(attachment)
    row_check = db_session.query(MaintenanceEventAttachment).filter(MaintenanceEventAttachment.id == attachment.id).first()
    assert row_check is not None
