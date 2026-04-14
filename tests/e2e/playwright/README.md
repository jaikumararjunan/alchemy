"""
tests/e2e/playwright/README.md — Playwright E2E Test Suite

Setup:
  pip install playwright --break-system-packages
  playwright install chromium

Run:
  pytest tests/e2e/playwright/ -v --headed (with browser)
  pytest tests/e2e/playwright/ -v          (headless)

Test Matrix (30 tests):
  Auth Flow (6):      signup, login, logout, 2FA, forgot password, session persist
  Dashboard (4):      load, stat cards, BTC price, signals
  Paper Trading (8):  buy, sell, close, SL/TP, history, leaderboard, reset, export
  Navigation (4):     sidebar links, command palette (Cmd+K), mobile menu, breadcrumbs
  Settings (3):       theme switch, password change, profile update
  Security (3):       audit log, devices, risk assessment
  Responsive (2):     mobile viewport, tablet viewport
"""
