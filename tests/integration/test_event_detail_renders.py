"""Regression test ensuring event detail page renders with HTTP 200 for all event statuses and enforces role access."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.auth.provider import LocalAuthProvider
from app.main import app
from app.models.models import (
    Computer,
    MaintenanceEvent,
    MaintenanceEventStatus,
    User,
    UserRole,
)


def _make_technician(db, username):
    provider = LocalAuthProvider()
    u = User(
        username=username,
        email_or_login=f"{username}@test.local",
        password_hash=provider.hash_password("password123"),
        role=UserRole.TECHNICIAN,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def _make_event(db, tech, computer, status=MaintenanceEventStatus.PLANNED):
    ev = MaintenanceEvent(
        computer_id=computer.id,
        technician_id=tech.id,
        scheduled_date=datetime.now(timezone.utc).date(),
        status=status,
    )
    db.add(ev)
    db.flush()
    return ev


def test_event_detail_renders_for_each_status(db):
    tech = _make_technician(db, "tech_evd")
    comp = Computer(hostname="EVD-PC-1", status="active")
    db.add(comp)
    db.commit()

    client = TestClient(app, raise_server_exceptions=True)
    resp_login = client.post("/auth/login", data={"username": "tech_evd", "password": "password123"})
    assert resp_login.status_code == 302
    cookies = resp_login.cookies

    for st in [
        MaintenanceEventStatus.PLANNED,
        MaintenanceEventStatus.IN_PROGRESS,
        MaintenanceEventStatus.DONE,
        MaintenanceEventStatus.MISSED,
    ]:
        ev = _make_event(db, tech, comp, st)
        db.commit()
        r = client.get(f"/technician/events/{ev.id}", cookies=cookies)
        assert r.status_code == 200, f"{st}: {r.status_code}"


def test_event_detail_role_access(db):
    tech = _make_technician(db, "tech_evd2")
    other_tech = _make_technician(db, "tech_other")
    user_end = User(
        username="user_evd",
        email_or_login="user_evd@test.local",
        password_hash=LocalAuthProvider().hash_password("password123"),
        role=UserRole.USER,
        is_active=True,
    )
    observer = User(
        username="obs_evd",
        email_or_login="obs_evd@test.local",
        password_hash=LocalAuthProvider().hash_password("password123"),
        role=UserRole.OBSERVER,
        is_active=True,
    )
    admin = User(
        username="admin_evd",
        email_or_login="admin_evd@test.local",
        password_hash=LocalAuthProvider().hash_password("password123"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add_all([user_end, observer, admin])

    comp = Computer(hostname="EVD-PC-2", status="active")
    db.add(comp)
    db.commit()

    ev = _make_event(db, tech, comp)
    db.commit()

    client = TestClient(app, raise_server_exceptions=True)

    def get_cookies(username):
        res = client.post("/auth/login", data={"username": username, "password": "password123"})
        return res.cookies

    admin_cookies = get_cookies("admin_evd")
    tech_cookies = get_cookies("tech_evd2")
    other_cookies = get_cookies("tech_other")
    obs_cookies = get_cookies("obs_evd")
    user_cookies = get_cookies("user_evd")

    assert client.get(f"/technician/events/{ev.id}", cookies=admin_cookies).status_code == 200
    assert client.get(f"/technician/events/{ev.id}", cookies=tech_cookies).status_code == 200
    assert client.get(f"/technician/events/{ev.id}", cookies=other_cookies).status_code == 403
    assert client.get(f"/technician/events/{ev.id}", cookies=obs_cookies).status_code == 403
    assert client.get(f"/technician/events/{ev.id}", cookies=user_cookies).status_code == 403
