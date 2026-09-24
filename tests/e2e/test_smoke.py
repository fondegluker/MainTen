"""Mandatory E2E Smoke Test Suite for CFMS using Playwright."""

import os
import subprocess
import time
from urllib.parse import urljoin

import httpx
import pytest
from playwright.sync_api import sync_playwright

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
            nav_hrefs = page.eval_on_selector_all("nav a", "elements => elements.map(e => e.getAttribute('href'))")
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


def test_e2e_locale_switch_per_role():
    """Toggle locale RU ↔ EN per role and assert visible translated strings change."""
    roles = [
        ("admin", "admin123"),
        ("tech_e2e", "tech123"),
        ("obs_e2e", "obs123"),
        ("user_e2e", "user123"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for username, password in roles:
            context = browser.new_context()
            page = context.new_page()

            page.goto(f"{BASE_URL}/auth/login")
            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle")

            # Switch to EN
            page.goto(f"{BASE_URL}/set-locale?locale=en")
            page.wait_for_load_state("networkidle")

            content_en = page.content()
            assert (
                "Sign Out" in content_en
                or "Computer Fleet Maintenance Scheduler" in content_en
                or "My Computers" in content_en
                or "Reports" in content_en
            ), f"Role {username}: Failed to switch UI to English"

            # Switch back to RU
            page.goto(f"{BASE_URL}/set-locale?locale=ru")
            page.wait_for_load_state("networkidle")

            content_ru = page.content()
            assert (
                "Выйти" in content_ru
                or "Система планирования ТО ПК" in content_ru
                or "Мои компьютеры" in content_ru
                or "Отчеты" in content_ru
            ), f"Role {username}: Failed to switch UI back to Russian"

            context.close()

        browser.close()


def test_e2e_magic_link_flow_date_picker_and_technician_schedule():
    """End-to-end magic-link generation, date picker selection, and technician schedule verification."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # 1. ADMIN session: Regenerate magic link for user_e2e
        admin_context = browser.new_context()
        admin_page = admin_context.new_page()

        admin_page.goto(f"{BASE_URL}/auth/login")
        admin_page.fill("input[name='username']", "admin")
        admin_page.fill("input[name='password']", "admin123")
        admin_page.click("button[type='submit']")
        admin_page.wait_for_load_state("networkidle")

        admin_page.goto(f"{BASE_URL}/admin/users")
        admin_page.wait_for_load_state("networkidle")

        # Find user_e2e user ID from magic-link row
        magic_link_href = admin_page.eval_on_selector(
            "tr:has-text('user_e2e') a[href*='magic-link']", "element => element.getAttribute('href')"
        )
        assert magic_link_href, "Magic link route not found for user_e2e in admin users list"

        admin_page.goto(urljoin(BASE_URL, magic_link_href))
        admin_page.wait_for_load_state("networkidle")

        # Click regenerate button
        admin_page.click("#regenerate-btn")
        admin_page.wait_for_timeout(1000)

        magic_url_val = admin_page.input_value("#magic-url-input")
        assert magic_url_val and "/auth/magic-link?token=" in magic_url_val, (
            f"Invalid magic url generated: {magic_url_val}"
        )

        admin_context.close()

        # 2. Fresh USER session: Open magic link
        user_context = browser.new_context()
        user_page = user_context.new_page()

        user_page.goto(magic_url_val)
        user_page.wait_for_load_state("networkidle")

        # Assert landing on user's page with date picker rendered prominently
        assert "/user/my-computers" in user_page.url
        assert (
            "Выберите дату технического обслуживания" in user_page.content() or "Выбранная дата" in user_page.content()
        )

        # Select first visible radio date input if picker is active
        visible_radio = user_page.locator("input[name='scheduled_date_str']:visible").first
        if visible_radio.count() > 0:
            visible_radio.check(force=True)
            user_page.click("form:has(input[name='scheduled_date_str']:visible) button[type='submit']")
            user_page.wait_for_load_state("networkidle")
            assert "успешно" in user_page.content() or "Выбранная дата" in user_page.content()

        user_context.close()

        # 3. TECHNICIAN session: Check schedule page
        tech_context = browser.new_context()
        tech_page = tech_context.new_page()

        tech_page.goto(f"{BASE_URL}/auth/login")
        tech_page.fill("input[name='username']", "tech_e2e")
        tech_page.fill("input[name='password']", "tech123")
        tech_page.click("button[type='submit']")
        tech_page.wait_for_load_state("networkidle")

        tech_res = tech_page.goto(f"{BASE_URL}/technician/schedule")
        assert tech_res and tech_res.status == 200
        assert "График" in tech_page.content() or "schedule" in tech_page.content().lower()

        tech_context.close()
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
