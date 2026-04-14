"""
Playwright E2E test configuration.
These tests require: pip install playwright pytest-playwright && playwright install chromium
Skip if playwright not installed.
"""
import pytest

try:
    import playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def pytest_collection_modifyitems(items):
    if not PLAYWRIGHT_AVAILABLE:
        skip = pytest.mark.skip(reason="playwright not installed")
        for item in items:
            if "playwright" in str(item.fspath):
                item.add_marker(skip)
