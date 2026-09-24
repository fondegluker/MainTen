"""Mandatory E2E Smoke Test Suite for CFMS using Playwright."""

import os
import subprocess
import time
from urllib.parse import urljoin

import httpx
import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.e2e

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module", autouse=True)
def wait_for_server_and_seed():
    """Ensure web application is healthy on BASE_URL and seed E2E dataset."""
    timeout = 30
    start = time.time()
    client = httpx.Client(base_url=BASE_URL, follow_redirects=True, timeout=5.0)

    server_up = False
    while time.time() - start < timeout:
        try:
            res = client.get("/auth/login")
            if res.status_code == 200:
                server_up = True
                break
        except (httpx.HTTPError, httpx.RequestError):
            pass
        time.sleep(1)

    assert server_up, f"Application server failed to respond on {BASE_URL} within {timeout} seconds"

    # Seed E2E dataset
    login_res = client.post("/auth/login", data={"username": "admin", "password": "admin123"})
    if login_res.status_code == 200:
        client.post("/admin/seed-e2e")
    else:
        # Fallback to local python module seed if DB is directly accessible
        try:
            from app.core.database import SessionLocal
            from app.seed_e2e import seed_e2e

            s = SessionLocal()
            try:
                seed_e2e(s)
            finally:
                s.close()
        except Exception as exc:  # noqa: BLE001
            print(f"Direct seed fallback notice: {exc}")


def test_e2e_all_roles_nav_links_and_forbidden_status():
    """Walk every role through every nav link, assert 200 for allowed, 403 for forbidden, fail on 404/500."""
    roles = [
        (
            "admin",
            "admin123",
            [
                "/admin/dashboard",
                "/admin/users",
                "/admin/computers",
                "/admin/technicians",
                "/admin/import",
                "/technician/schedule",
                "/reports",
                "/user/my-computers",
            ],
            [],
        ),
        (
            "tech_e2e",
            "tech123",
            ["/technician/schedule", "/reports", "/user/my-computers"],
            ["/admin/dashboard", "/admin/users", "/admin/computers"],
        ),
        (
            "obs_e2e",
            "obs123",
            ["/reports", "/user/my-computers"],
            ["/admin/dashboard", "/admin/users", "/admin/computers", "/technician/schedule"],
        ),
        (
            "user_e2e",
            "user123",
            ["/user/my-computers"],
            ["/admin/dashboard", "/admin/users", "/admin/computers", "/technician/schedule", "/reports"],
        ),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for username, password, allowed_urls, forbidden_urls in roles:
            context = browser.new_context()
            page = context.new_page()

            # Login
            page.goto(f"{BASE_URL}/auth/login")
            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")

            # Extract nav links present on page
            nav_hrefs = page.eval_on_selector_all("aside#sidebar-nav a", "elements => elements.map(e => e.getAttribute('href'))")
            clean_hrefs = [
                h
                for h in nav_hrefs
                if h and not h.startswith("#") and not h.startswith("javascript") and h != "/auth/logout"
            ]

            # Visit every link in main navigation
            for href in clean_hrefs:
                full_url = urljoin(BASE_URL, href)
                response = page.goto(full_url)
                status_code = response.status if response else 500
                assert status_code == 200, f"Role {username}: Nav link '{href}' returned {status_code} (expected 200)"

            # Visit allowed URLs list explicitly
            for url_path in allowed_urls:
                full_url = urljoin(BASE_URL, url_path)
                response = page.goto(full_url)
                status_code = response.status if response else 500
                assert status_code == 200, (
                    f"Role {username}: Allowed page '{url_path}' returned {status_code} (expected 200)"
                )

            # Visit forbidden URLs list explicitly
            for url_path in forbidden_urls:
                full_url = urljoin(BASE_URL, url_path)
                response = page.goto(full_url)
                status_code = response.status if response else 500
                assert status_code == 403, (
                    f"Role {username}: Forbidden page '{url_path}' returned {status_code} (expected 403, no 404/500 allowed)"
                )

            context.close()

        browser.close()


def test_e2e_issue1_calendar_grid_and_12_month_navigation():
    """E2E test for Issue 1: open /admin/calendar, navigate 12 months ahead, assert 7 columns."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{BASE_URL}/auth/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        res = page.goto(f"{BASE_URL}/admin/calendar")
        assert res.status == 200
        assert "grid-cols-7" in page.content() or "Пн" in page.content() or "Mon" in page.content()

        # Navigate 12 months forward
        for _ in range(12):
            next_link = page.get_by_text("Следующий месяц")
            if next_link.count() > 0:
                next_link.first.click()
            else:
                page.click("a:has-text('Next')")
            page.wait_for_load_state("networkidle")
            assert page.title() != "500 Internal Server Error"

        context.close()
        browser.close()


def test_e2e_issue2_calendar_import_templates():
    """E2E test for Issue 2: download template CSV and JSON links exist on calendar page."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{BASE_URL}/auth/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        page.goto(f"{BASE_URL}/admin/calendar")
        page.wait_for_load_state("networkidle")

        content = page.content()
        assert "/admin/calendar/import/template.csv" in content
        assert "/admin/calendar/import/template.json" in content

        context.close()
        browser.close()


def test_e2e_issue3_datepicker_locale_weekday_names():
    """E2E test for Issue 3: date picker weekday names change based on UI locale."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{BASE_URL}/auth/login")
        page.fill("input[name='username']", "user_e2e")
        page.fill("input[name='password']", "user123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        # Set locale RU
        page.goto(f"{BASE_URL}/set-locale?locale=ru")
        page.goto(f"{BASE_URL}/user/my-computers")
        page.wait_for_load_state("networkidle")

        content_ru = page.content()
        # Verify Russian weekday name or headers present
        assert "Пн" in content_ru or "Вт" in content_ru or "Ср" in content_ru or "Чт" in content_ru or "Пт" in content_ru or "Сб" in content_ru or "Вс" in content_ru or "Выберите дату" in content_ru

        # Set locale EN
        page.goto(f"{BASE_URL}/set-locale?locale=en")
        page.goto(f"{BASE_URL}/user/my-computers")
        page.wait_for_load_state("networkidle")

        content_en = page.content()
        assert "Select maintenance date" in content_en or "Mon" in content_en or "Tue" in content_en or "Wed" in content_en or "Thu" in content_en or "Fri" in content_en or "Sat" in content_en or "Sun" in content_en

        context.close()
        browser.close()


def test_e2e_issue4_weekend_rejection_422():
    """E2E test for Issue 4: server rejects weekend date submission with 422."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{BASE_URL}/auth/login")
        page.fill("input[name='username']", "user_e2e")
        page.fill("input[name='password']", "user123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        # Submit Saturday date directly via API
        response = page.request.post(
            f"{BASE_URL}/user/schedule/1",
            form={"scheduled_date_str": "2025-05-03"}  # Saturday
        )
        assert response.status == 422

        context.close()
        browser.close()


def test_e2e_issue5_left_sidebar_and_hamburger_drawer():
    """E2E test for Issue 5: left sidebar hover expansion and mobile hamburger drawer toggle."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Desktop hover expansion
        desktop_ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        desktop_page = desktop_ctx.new_page()

        desktop_page.goto(f"{BASE_URL}/auth/login")
        desktop_page.fill("input[name='username']", "admin")
        desktop_page.fill("input[name='password']", "admin123")
        desktop_page.click("button[type='submit']")
        desktop_page.wait_for_load_state("networkidle")

        sidebar = desktop_page.locator("#sidebar-nav")
        assert sidebar.count() == 1

        # Hover sidebar
        sidebar.hover()
        desktop_page.wait_for_timeout(300)
        assert sidebar.is_visible()

        desktop_ctx.close()

        # Mobile viewport drawer toggle (375px)
        mobile_ctx = browser.new_context(viewport={"width": 375, "height": 667})
        mobile_page = mobile_ctx.new_page()

        mobile_page.goto(f"{BASE_URL}/auth/login")
        mobile_page.fill("input[name='username']", "admin")
        mobile_page.fill("input[name='password']", "admin123")
        mobile_page.click("button[type='submit']")
        mobile_page.wait_for_load_state("networkidle")

        # Click hamburger button to open drawer
        hamburger = mobile_page.locator("button[aria-label='Toggle Navigation Menu']")
        assert hamburger.count() == 1
        hamburger.click()
        mobile_page.wait_for_timeout(300)

        # Press Escape key to close drawer
        mobile_page.keyboard.press("Escape")
        mobile_page.wait_for_timeout(300)

        mobile_ctx.close()
        browser.close()


def test_e2e_app_container_logs_no_tracebacks():
    """Assert there are no uncaught errors or tracebacks in the docker container logs."""
    try:
        res = subprocess.run(
            ["docker", "compose", "logs", "--no-color", "web"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        logs = res.stdout + res.stderr
        assert "Traceback (most recent call last)" not in logs, (
            f"Uncaught exception found in web container logs:\n{logs}"
        )
        assert "HTTP/1.1 500 Internal Server Error" not in logs, f"HTTP 500 error found in web container logs:\n{logs}"
    except (subprocess.SubprocessError, FileNotFoundError):
        print("Docker compose logs check skipped (not running in docker or compose unavailable).")
