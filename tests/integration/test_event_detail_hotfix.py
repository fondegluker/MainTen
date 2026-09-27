"""Integration regression test for GET /technician/events/{id} detail view hotfix (Step 4)."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth.provider import LocalAuthProvider
from app.main import app
from app.models.models import (
    MaintenanceEvent,
    User,
    UserRole,
)
from app.seed_demo import seed_demo


@pytest.fixture
def seeded_demo_data(db):
    """Seed demo data via seed_demo and return users and events."""
    res = seed_demo(db)

    admin = db.query(User).filter(User.username == "admin").first()
    tech_demo = db.query(User).filter(User.username == "tech_demo").first()
    user_demo = db.query(User).filter(User.username == "user_demo").first()

    # Create unassigned technician & observer for permission checks
    provider = LocalAuthProvider()
    tech2 = db.query(User).filter(User.username == "tech2_test").first()
    if not tech2:
        tech2 = User(
            username="tech2_test",
            email_or_login="tech2@test.local",
            password_hash=provider.hash_password("tech2pass"),
            role=UserRole.TECHNICIAN,
            locale="ru",
            is_active=True,
        )
        db.add(tech2)

    observer = db.query(User).filter(User.username == "obs_test").first()
    if not observer:
        observer = User(
            username="obs_test",
            email_or_login="obs@test.local",
            password_hash=provider.hash_password("obspass"),
            role=UserRole.OBSERVER,
            locale="ru",
            is_active=True,
        )
        db.add(observer)

    db.commit()

    events = db.query(MaintenanceEvent).all()
    return {
        "admin": admin,
        "tech_demo": tech_demo,
        "tech2": tech2,
        "user_demo": user_demo,
        "observer": observer,
        "events": events,
    }


def test_seeded_events_detail_access_permissions_and_render(seeded_demo_data):
    """Integration test using seed_demo:
    1. Runs seed_demo
    2. GETs /technician/events/{id} for all 6 events as assigned technician (tech_demo) -> 200
    3. GETs as admin -> 200
    4. GETs as unassigned tech -> 403
    5. GETs as user and observer -> 403
    """
    data = seeded_demo_data
    client = TestClient(app, raise_server_exceptions=True)

    def login_user(username: str, password: str = "tech_demo123") -> dict:
        resp = client.post("/auth/login", data={"username": username, "password": password})
        assert resp.status_code == 302, f"Login failed for {username}"
        return resp.cookies

    tech_cookies = login_user("tech_demo", "tech_demo123")
    admin_cookies = login_user("admin", "admin123")
    tech2_cookies = login_user("tech2_test", "tech2pass")
    user_cookies = login_user("user_demo", "user_demo123")
    observer_cookies = login_user("obs_test", "obspass")

    events = data["events"]
    assert len(events) >= 6, f"Expected at least 6 events from seed, got {len(events)}"

    # 1. Assigned Technician (tech_demo) -> 200
    for ev in events:
        r = client.get(f"/technician/events/{ev.id}", cookies=tech_cookies)
        assert r.status_code == 200, f"Expected 200 for tech_demo on event {ev.id}, got {r.status_code}"
        assert f"#{ev.id}" in r.text

    # 2. Admin -> 200
    for ev in events:
        r = client.get(f"/technician/events/{ev.id}", cookies=admin_cookies)
        assert r.status_code == 200, f"Expected 200 for admin on event {ev.id}, got {r.status_code}"

    # 3. Unassigned Tech -> 403
    for ev in events:
        r = client.get(f"/technician/events/{ev.id}", cookies=tech2_cookies)
        assert r.status_code == 403, f"Expected 403 for tech2 on event {ev.id}, got {r.status_code}"

    # 4. User -> 403
    for ev in events:
        r = client.get(f"/technician/events/{ev.id}", cookies=user_cookies)
        assert r.status_code == 403, f"Expected 403 for user on event {ev.id}, got {r.status_code}"

    # 5. Observer -> 403
    for ev in events:
        r = client.get(f"/technician/events/{ev.id}", cookies=observer_cookies)
        assert r.status_code == 403, f"Expected 403 for observer on event {ev.id}, got {r.status_code}"


def test_template_compile_smoke():
    """Smoke test ensuring Jinja2 event detail template compiles without syntax errors."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("app/templates"))
    tmpl = env.get_template("technician/event_detail.html")
    assert tmpl is not None
