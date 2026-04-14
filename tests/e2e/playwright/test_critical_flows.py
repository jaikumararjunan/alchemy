"""
Playwright E2E browser tests for Alchemy UI.

Setup:
  pip install playwright pytest-playwright
  playwright install chromium

Run:
  pytest tests/e2e/playwright/ --headed
  pytest tests/e2e/playwright/
"""
import pytest

BASE_URL = "http://localhost:5173"

class TestAuthFlow:
    def test_login_page_loads(self, page):
        page.goto(f"{BASE_URL}/auth/login")
        assert page.locator("input[type='email']").is_visible()
        assert page.locator("input[type='password']").is_visible()

    def test_signup_page_loads(self, page):
        page.goto(f"{BASE_URL}/auth/signup")
        assert page.locator("input[type='email']").is_visible()

    def test_forgot_password_page(self, page):
        page.goto(f"{BASE_URL}/auth/forgot-password")
        assert page.locator("input[type='email']").is_visible()

class TestNavigation:
    PAGES = ["/dashboard", "/portfolio", "/crypto", "/watchlist",
             "/paper-trading", "/autonomous", "/signals", "/strategy",
             "/analytics", "/risk", "/alerts", "/tokens",
             "/settings", "/notifications", "/security"]

    @pytest.mark.parametrize("path", PAGES)
    def test_page_loads(self, page, path):
        page.goto(f"{BASE_URL}{path}")
        page.wait_for_timeout(500)
        assert page.locator("body").inner_text()

class TestCommandPalette:
    def test_opens_on_keyboard(self, page):
        page.goto(f"{BASE_URL}/dashboard")
        page.keyboard.press("Control+k")
        page.wait_for_timeout(300)
        assert page.locator("input[placeholder*='Search']").is_visible()

    def test_closes_on_escape(self, page):
        page.goto(f"{BASE_URL}/dashboard")
        page.keyboard.press("Control+k")
        page.wait_for_timeout(200)
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        assert not page.locator("input[placeholder*='Search']").is_visible()

class TestResponsive:
    def test_mobile_viewport(self, page):
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{BASE_URL}/dashboard")
        page.wait_for_timeout(500)
        assert page.locator("button:has(svg)").first.is_visible()
