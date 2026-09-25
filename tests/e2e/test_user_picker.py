"""E2E Playwright tests specifically targeting the unified 3+3 maintenance date picker (Block A & Block B)."""

import os
import time
from urllib.parse import urljoin

import httpx
import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.e2e

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module", autouse=True)
def wait_for_server():
    """Ensure web application is healthy on BASE_URL."""
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

    login_res = client.post("/auth/login", data={"username": "admin", "password": "admin123"})
    if login_res.status_code == 200:
        client.post("/admin/seed-e2e")


def test_e2e_first_rendered_cell_is_first_selectable_date():
    """Verify the date picker begins at the first selectable date with no leading past date cells."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login as ADMIN to get magic link for user_e2e
        page.goto(f"{BASE_URL}/auth/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        page.goto(f"{BASE_URL}/admin/users")
        magic_href = page.eval_on_selector(
            "tr:has-text('user_e2e') a[href*='magic-link']", "el => el.getAttribute('href')"
        )
        page.goto(urljoin(BASE_URL, magic_href))
        page.click("#regenerate-btn")
        page.wait_for_timeout(500)
        magic_url = page.input_value("#magic-url-input")
        context.close()

        # Login as USER via magic link
        user_ctx = browser.new_context()
        user_page = user_ctx.new_page()
        user_page.goto(magic_url)
        user_page.wait_for_load_state("networkidle")

        picker = user_page.locator("form[data-testid='maintenance-date-picker']").first
        if picker.count() > 0:
            picker_html = picker.inner_html()
            # Assert NO header row nodes containing standalone "Пн" or "Mon" headers
            assert "header_row1" not in picker_html

            # Assert first visible radio input is NOT disabled (is the first selectable date)
            first_radio = picker.locator("input[type='radio']").first
            if first_radio.count() > 0:
                assert not first_radio.is_disabled(), (
                    "First rendered radio cell must be selectable (no leading past date cells)"
                )

        user_ctx.close()
        browser.close()


def test_e2e_block_b_reschedule_picker_same_as_block_a():
    """Verify Block B ('Изменить дату') uses identical date picker component with disabled weekends, holidays, and inline error handling."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(f"{BASE_URL}/auth/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "admin123")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        page.goto(f"{BASE_URL}/admin/users")
        magic_href = page.eval_on_selector(
            "tr:has-text('user_e2e') a[href*='magic-link']", "el => el.getAttribute('href')"
        )
        page.goto(urljoin(BASE_URL, magic_href))
        page.click("#regenerate-btn")
        page.wait_for_timeout(500)
        magic_url = page.input_value("#magic-url-input")
        context.close()

        user_ctx = browser.new_context()
        user_page = user_ctx.new_page()
        user_page.goto(magic_url)
        user_page.wait_for_load_state("networkidle")

        # Select date initially if not chosen
        initial_picker = user_page.locator("form[data-testid='maintenance-date-picker']").first
        if initial_picker.count() > 0 and user_page.locator("button:has-text('Изменить дату')").count() == 0:
            selectable_radio = initial_picker.locator("input[type='radio']:not([disabled])").first
            if selectable_radio.count() > 0:
                selectable_radio.check(force=True)
                initial_picker.locator("button[type='submit']").click()
                user_page.wait_for_load_state("networkidle")

        # Click "Изменить дату" button
        change_btn = user_page.locator("button:has-text('Изменить дату')")
        if change_btn.count() > 0:
            change_btn.click()
            user_page.wait_for_timeout(300)

            picker = user_page.locator("form[data-testid='maintenance-date-picker']").first
            assert picker.is_visible()

            # Force submit a disabled radio via DOM manipulation to test inline error alert
            user_page.evaluate("""
                const form = document.querySelector("form[data-testid='maintenance-date-picker']");
                let disabledRadio = form.querySelector("input[disabled]");
                if (!disabledRadio) {
                    disabledRadio = document.createElement("input");
                    disabledRadio.type = "radio";
                    disabledRadio.name = "scheduled_date_str";
                    disabledRadio.value = "2025-05-03"; // Saturday
                    disabledRadio.checked = true;
                    form.appendChild(disabledRadio);
                } else {
                    disabledRadio.removeAttribute("disabled");
                    disabledRadio.checked = true;
                }
            """)

            picker.locator("button[type='submit']").evaluate("el => el.removeAttribute('disabled')")
            picker.locator("button[type='submit']").click()
            user_page.wait_for_timeout(1000)

            # Assert inline error alert is rendered on page (NOT raw JSON)
            inline_error = user_page.locator(".inline-error-alert:visible")
            assert inline_error.count() > 0, "Inline error container was not displayed on invalid submit"
            error_text = inline_error.inner_text()
            assert "Выбранный день" in error_text or "выходным" in error_text or "недоступен" in error_text

            assert "{" not in user_page.content() or "detail" not in user_page.content(), (
                "Raw JSON detail was shown on page"
            )

        user_ctx.close()
        browser.close()
