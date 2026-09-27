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
