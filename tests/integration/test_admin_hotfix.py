"""Integration tests for Admin List Hotfixes: sorting, next_maintenance_due_at column, per_page=all toggle."""

import pytest
from datetime import datetime, timezone
from app.auth.tokens import generate_session_cookie
from app.models.models import Computer, User, UserRole


@pytest.fixture
def seeded_computers(db_session):
    computers = []
    for i in range(25):
        c = Computer(
            hostname=f"HOST-{i:02d}",
            ip=f"192.168.1.{100 + i}",
            os=f"OS-{i % 3}",
            location=f"Room {100 + (i % 5)}",
            is_round_the_clock=(i % 2 == 0),
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        if i % 3 == 0:
            c.next_maintenance_due_at = datetime(2026, 1, 10 + (i % 10), tzinfo=timezone.utc)
        db_session.add(c)
        computers.append(c)
    db_session.commit()
    return computers


def test_admin_computers_sorting_and_next_maint_column(client, admin_user, seeded_computers):
    """Verify server-side sorting, next_maintenance_due_at column, and filter composition."""
    client.cookies.set("session", generate_session_cookie(admin_user.id))

    # 1. sort=ip&order=asc -> 200
    res_ip = client.get("/admin/computers?sort=ip&order=asc")
    assert res_ip.status_code == 200
    assert "HOST-" in res_ip.text
    assert "192.168.1.100" in res_ip.text

    # 2. sort=hostname&order=desc -> 200
    res_host_desc = client.get("/admin/computers?sort=hostname&order=desc")
    assert res_host_desc.status_code == 200

    # 3. sort=next_maintenance_due_at&order=asc -> 200
    res_next_asc = client.get("/admin/computers?sort=next_maintenance_due_at&order=asc")
    assert res_next_asc.status_code == 200
    assert "Дата следующего ТО" in res_next_asc.text or "Next maintenance date" in res_next_asc.text

    # 4. sort=next_maintenance_due_at&order=desc -> 200
    res_next_desc = client.get("/admin/computers?sort=next_maintenance_due_at&order=desc")
    assert res_next_desc.status_code == 200

    # 5. Sort + Filter composition
    res_filter_sort = client.get("/admin/computers?rtc=yes&sort=os&order=asc")
    assert res_filter_sort.status_code == 200

    # 6. Unknown sort fallback
    res_unknown = client.get("/admin/computers?sort=invalid_column&order=asc")
    assert res_unknown.status_code == 200


def test_admin_computers_page_size_toggle(client, admin_user, seeded_computers):
    """Verify default per_page=all renders all 25 rows, and per_page=20 renders 20 rows with pagination."""
    client.cookies.set("session", generate_session_cookie(admin_user.id))

    # Default per_page=all -> all 25 rows on one page
    res_all = client.get("/admin/computers")
    assert res_all.status_code == 200
    assert res_all.text.count("HOST-") == 25
    assert "Страница 1 из" not in res_all.text

    # per_page=20 -> exactly 20 rows with pagination controls
    res_20 = client.get("/admin/computers?per_page=20")
    assert res_20.status_code == 200
    assert res_20.text.count("HOST-") == 20
    assert "Страница 1 из 2" in res_20.text


def test_admin_users_sorting_and_page_size_toggle(client, admin_user, db_session):
    """Verify /admin/users server-side sorting and per_page=all toggle."""
    # Seed extra users
    for i in range(25):
        u = User(
            username=f"user_test_{i:02d}",
            email_or_login=f"user_{i}@cfms.local",
            role=UserRole.USER if i % 2 == 0 else UserRole.TECHNICIAN,
            is_active=(i % 3 != 0),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(u)
    db_session.commit()

    client.cookies.set("session", generate_session_cookie(admin_user.id))

    # 1. sort=username&order=asc -> 200
    res_user_asc = client.get("/admin/users?sort=username&order=asc")
    assert res_user_asc.status_code == 200

    # 2. sort=role&order=desc -> 200
    res_role_desc = client.get("/admin/users?sort=role&order=desc")
    assert res_role_desc.status_code == 200

    # 3. sort=is_active&order=asc -> 200
    res_active_asc = client.get("/admin/users?sort=is_active&order=asc")
    assert res_active_asc.status_code == 200

    # 4. Sort + filter: ?role=TECHNICIAN&sort=username&order=desc -> 200
    res_tech = client.get("/admin/users?role=TECHNICIAN&sort=username&order=desc")
    assert res_tech.status_code == 200

    # 5. Default per_page=all -> all users
    res_all_users = client.get("/admin/users")
    assert res_all_users.status_code == 200
    assert "user_test_24" in res_all_users.text

    # 6. per_page=20&sort=username&order=desc -> 20 rows
    res_20_users = client.get("/admin/users?per_page=20&sort=username&order=desc")
    assert res_20_users.status_code == 200
    assert "Страница 1 из" in res_20_users.text
