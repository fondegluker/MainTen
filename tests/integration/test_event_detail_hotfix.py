"""Integration regression test for GET /technician/events/{id} detail view hotfix (Step 4)."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth.provider import LocalAuthProvider
from app.main import app
from app.models.models import (
    Computer,
    MaintenanceEvent,
    MaintenanceEventCheck,
    MaintenanceEventStatus,
    MaintenanceProtocolItem,
    User,
    UserRole,
)


@pytest.fixture
def setup_event_detail_data(db):
    """Create test users (admin, tech1, tech2, user, observer), computer, protocol items, and 3 events:
    - planned event with full relations and checks,
    - done event with start/finish dates,
    - unplanned event created via unplanned flow.
    """
    # 1. Users
    hasher = LocalAuthProvider()
    pwd_hash = hasher.hash_password("password123")

    admin = User(
        username="admin_hotfix",
        email_or_login="admin_hotfix@test.com",
        password_hash=pwd_hash,
        role=UserRole.ADMIN,
        locale="ru",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    tech1 = User(
        username="tech1_hotfix",
        email_or_login="tech1_hotfix@test.com",
        password_hash=pwd_hash,
        role=UserRole.TECHNICIAN,
        locale="ru",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    tech2 = User(
        username="tech2_hotfix",
        email_or_login="tech2_hotfix@test.com",
        password_hash=pwd_hash,
        role=UserRole.TECHNICIAN,
        locale="ru",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    user_end = User(
        username="enduser_hotfix",
        email_or_login="enduser_hotfix@test.com",
        password_hash=pwd_hash,
        role=UserRole.USER,
        locale="ru",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    observer = User(
        username="observer_hotfix",
        email_or_login="observer_hotfix@test.com",
        password_hash=pwd_hash,
        role=UserRole.OBSERVER,
        locale="ru",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add_all([admin, tech1, tech2, user_end, observer])
    db.commit()

    # 2. Computer
    comp = Computer(
        hostname="PC-DETAIL-TEST",
        ip="192.168.1.150",
        location="Room 303",
        os="Windows 11",
        owner_user_id=user_end.id,
        status="active",
    )
    db.add(comp)
    db.commit()

    # 3. Protocol Item
    item = MaintenanceProtocolItem(
        order_index=1,
        title_ru="Проверка пыли",
        title_en="Dust Check",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(item)
    db.commit()

    # 4. Events
    # Event 1: Planned event
    ev_planned = MaintenanceEvent(
        computer_id=comp.id,
        technician_id=tech1.id,
        scheduled_date=datetime.now(timezone.utc).date(),
        scheduled_slot="10:00",
        status=MaintenanceEventStatus.PLANNED,
        is_unplanned=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(ev_planned)
    db.flush()

    chk1 = MaintenanceEventCheck(
        event_id=ev_planned.id,
        protocol_item_id=item.id,
        is_done=False,
    )
    db.add(chk1)

    # Event 2: Done event
    now_dt = datetime.now(timezone.utc)
    ev_done = MaintenanceEvent(
        computer_id=comp.id,
        technician_id=tech1.id,
        scheduled_date=now_dt.date(),
        scheduled_slot="14:00",
        status=MaintenanceEventStatus.DONE,
        started_at=now_dt,
        finished_at=now_dt,
        comment="Обслуживание выполнено в полном объеме",
        is_unplanned=False,
        created_at=now_dt,
        updated_at=now_dt,
    )
    db.add(ev_done)

    # Event 3: Unplanned event
    ev_unplanned = MaintenanceEvent(
        computer_id=comp.id,
        technician_id=tech1.id,
        scheduled_date=now_dt.date(),
        scheduled_slot=None,
        status=MaintenanceEventStatus.PLANNED,
        comment="Срочная заявка",
        is_unplanned=True,
        created_at=now_dt,
        updated_at=now_dt,
    )
    db.add(ev_unplanned)
    db.commit()

    return {
        "admin": admin,
        "tech1": tech1,
        "tech2": tech2,
        "user_end": user_end,
        "observer": observer,
        "ev_planned": ev_planned,
        "ev_done": ev_done,
        "ev_unplanned": ev_unplanned,
    }


def test_event_detail_access_permissions_and_render(setup_event_detail_data):
    """Regression test for GET /technician/events/{id}:
    - 200 for assigned technician on planned, done, unplanned events
    - 200 for ADMIN on all events
    - 403 for another technician (tech2)
    - 403 for USER and OBSERVER
    """
    data = setup_event_detail_data
    client = TestClient(app, raise_server_exceptions=True)

    # Helper for login cookie
    def login_user(username: str) -> dict:
        resp = client.post("/auth/login", data={"username": username, "password": "password123"})
        assert resp.status_code == 302, f"Login failed for {username}"
        return resp.cookies

    tech1_cookies = login_user(data["tech1"].username)
    admin_cookies = login_user(data["admin"].username)
    tech2_cookies = login_user(data["tech2"].username)
    user_cookies = login_user(data["user_end"].username)
    observer_cookies = login_user(data["observer"].username)

    events_to_test = [data["ev_planned"], data["ev_done"], data["ev_unplanned"]]

    # 1. Assigned Technician (tech1) -> 200 for all events
    for ev in events_to_test:
        r = client.get(f"/technician/events/{ev.id}", cookies=tech1_cookies)
        assert r.status_code == 200, f"Expected 200 for tech1 on event {ev.id}, got {r.status_code}"
        assert f"#{ev.id}" in r.text
        assert "PC-DETAIL-TEST" in r.text

    # 2. Admin -> 200 for all events
    for ev in events_to_test:
        r = client.get(f"/technician/events/{ev.id}", cookies=admin_cookies)
        assert r.status_code == 200, f"Expected 200 for admin on event {ev.id}, got {r.status_code}"

    # 3. Unassigned Technician (tech2) -> 403
    for ev in events_to_test:
        r = client.get(f"/technician/events/{ev.id}", cookies=tech2_cookies)
        assert r.status_code == 403, f"Expected 403 for tech2 on event {ev.id}, got {r.status_code}"

    # 4. End User -> 403
    for ev in events_to_test:
        r = client.get(f"/technician/events/{ev.id}", cookies=user_cookies)
        assert r.status_code == 403, f"Expected 403 for user on event {ev.id}, got {r.status_code}"

    # 5. Observer -> 403
    for ev in events_to_test:
        r = client.get(f"/technician/events/{ev.id}", cookies=observer_cookies)
        assert r.status_code == 403, f"Expected 403 for observer on event {ev.id}, got {r.status_code}"


def test_template_compile_smoke():
    """Smoke test ensuring Jinja2 event detail template compiles without syntax errors."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader("app/templates"))
    tmpl = env.get_template("technician/event_detail.html")
    assert tmpl is not None
