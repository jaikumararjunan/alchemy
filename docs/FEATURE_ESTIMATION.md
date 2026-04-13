# Alchemy Trading Platform — 46 Feature Estimation & Delivery Plan

**Date:** April 2026 | **Current Version:** v0.9.0 | **Target:** v1.0.0  
**Platform:** 121 Python files | 25,200+ lines | 210 API routes | 34 Frontend files | 190+ commits

---

## Delivery Summary

| Category | Features | Hours | Status |
|----------|----------|-------|--------|
| Web — Must Have | 8 | 14h | **7 Done ✅** |
| Web — Should Have | 10 | 37h | 0 Done |
| Web — Better to Have | 10 | 69h | 0 Done |
| Mobile — Must Have | 6 | 21h | 0 Done |
| Mobile — Should Have | 6 | 25h | 0 Done |
| Mobile — Better to Have | 6 | 45h | 0 Done |
| **TOTAL** | **46** | **~211h** | **7 Done** |

**At 6 productive hours/day = ~35 working days for all 46 features**

---

## WEB APPLICATION — MUST HAVE (14 hours total)

| # | Feature | Hours | Status | Details |
|---|---------|-------|--------|---------|
| W1 | SSL/HTTPS via Certbot | 2h | ✅ Done | `deploy/nginx.conf` + `deploy/setup-ssl.sh`. Run on VPS after DNS resolves. TLS 1.2/1.3, HSTS, rate limiting (30r/s API, 5r/m login). Auto-renewal cron. |
| W2 | Portfolio Persistence | 1h | ✅ Done | Saves to `/data/paper_trading/` Docker volume. Loads on startup. Survives container restarts. |
| W3 | Trade Confirmation Modal | 2h | ✅ Done | Modal showing symbol, side, qty, price, total value, SL/TP. Cancel/Confirm buttons. Color-coded by side. |
| W4 | WebSocket Real-Time Prices | 4h | ✅ Done | `alchemy/services/price_stream.py` — Binance WS combined stream for 7 symbols. Pushes `price_update` to all clients via existing WS manager. Frontend uses store prices with polling fallback. |
| W5 | Position Close Confirmation | 1h | ✅ Done | Modal showing entry/current price, P&L, return %. "Keep Open" / "Close Position" buttons. |
| W6 | Error Toast Improvement | 1h | ✅ Done | `frontend/src/utils/errorHandler.js` — centralized `getErrorMessage()`. Handles all API error formats. Status-based fallbacks. |
| W7 | Exchange API Key Validation | 2h | ✅ Done | `register_token` now tests connection on save. Returns validation result immediately. |
| W8 | Equity Curve Chart | 4h | ✅ Done | Snapshots every 5 min to `/data/equity_curves/`. `GET /api/paper/equity-curve?days=30`. Recharts AreaChart with green/red gradient. |

---

## WEB APPLICATION — SHOULD HAVE (37 hours total)

| # | Feature | Hours | Complexity | Implementation Approach |
|---|---------|-------|------------|------------------------|
| W9 | Watchlist Page (Frontend) | 4h | Medium | React page consuming existing `GET/POST /api/watchlist/` endpoints (PR #104). Live prices via WS store. Quick-trade buttons per symbol. Star/unstar. |
| W10 | Price Alerts Page (Frontend) | 4h | Medium | React page consuming existing `GET/POST /api/alerts/` endpoints (PR #104). Create alert form (symbol, target price, above/below). Active/triggered tabs. |
| W11 | Multi-Timeframe Chart | 6h | High | 2x2 grid of lightweight-charts: 1m, 15m, 1h, 4h. Shared symbol selector. Synced crosshair. |
| W12 | Trade Journal | 8h | High | New `trade_journal` SQLite table. CRUD API. React page with: notes per trade, tags (strategy, emotion), screenshots, filter by win/loss/strategy. |
| W13 | Email Notifications on SL/TP | 3h | Low | Hook into `_execute_stop()` → call existing SMTP dispatcher. Template: "SL/TP triggered: {symbol} closed at {price}, P&L: {pnl}". |
| W14 | Strategy Performance Comparison | 4h | Medium | Group `trade_log` by strategy field. Calculate per-strategy: win rate, avg return, Sharpe, total P&L. Recharts bar chart comparison. |
| W15 | Dark/Light Theme Toggle | 4h | Medium | Tailwind `dark:` class-based. Theme toggle in settings. Persist in localStorage. Update all 33 JSX files with dark: variants. |
| W16 | Position Sizing Calculator | 2h | Low | Input: account size, risk %, entry price, SL price. Output: qty, position size $, max loss $. React component in Quick Trade sidebar. |
| W17 | Duplicate Trade Prevention (Live) | 2h | Low | Before live order: check exchange positions via API. If position exists for symbol → warning modal: "You already have X open. Add to position?" |

---

## WEB APPLICATION — BETTER TO HAVE (69 hours total)

| # | Feature | Hours | Complexity | Implementation Approach |
|---|---------|-------|------------|------------------------|
| W18 | AI Trade Recommendations Panel | 8h | High | Display autonomous engine reasoning: RSI value, BB position, SMA cross, confidence %. Sidebar panel on Auto Trade page. "Why this trade?" explainer. |
| W19 | Portfolio Heatmap | 4h | Medium | D3.js treemap: position size = box area, P&L = color (green/red gradient). Interactive: hover shows details. |
| W20 | Correlation Matrix Dashboard | 3h | Medium | Existing `correlation_matrix` backend. D3 heatmap visualization. Select symbols, timeframe. Color scale -1 to +1. |
| W21 | Tax Report Export (India) | 4h | Medium | Existing STCG/LTCG/Crypto 30% calculator. Generate PDF/CSV: trade date, buy/sell, holding period, P&L, tax category, total liability. |
| W22 | Social Copy Trading | 12h | Very High | Follow/unfollow on leaderboard. Auto-mirror trades with configurable % allocation. WebSocket broadcast of trades. Privacy controls. |
| W23 | Strategy Marketplace | 10h | Very High | Publish strategies with backtest results. Subscribe/unsubscribe. Revenue share model. Rating system. |
| W24 | Advanced Order Types | 8h | High | OCO (One-Cancels-Other): place SL + TP simultaneously. Bracket orders: entry + SL + TP atomic. Trailing stop: dynamic SL following price. |
| W25 | Multi-Account Support | 6h | High | Multiple API keys per exchange in token store. Account selector dropdown. Separate portfolio tracking per account. |
| W26 | Webhook Integration | 4h | Medium | `POST /api/webhook/{token}` → parse TradingView JSON alert → map to trade → execute. User generates webhook URL in settings. |
| W27 | Replay Mode | 10h | Very High | Load historical candles. Step forward one bar at a time. Manual buy/sell decisions. Score vs buy-and-hold. Save replay sessions. |

---

## MOBILE APPLICATION — MUST HAVE (21 hours total)

| # | Feature | Hours | Complexity | Implementation Approach |
|---|---------|-------|------------|------------------------|
| M1 | Push Notifications | 6h | High | Expo Notifications + FCM. Backend: store device tokens, send push on trade fill/SL/TP trigger/signal. Categories: trades, alerts, signals. |
| M2 | Biometric Auth | 3h | Medium | `expo-local-authentication` → fingerprint/face before trade execution. Toggle in settings. Fall back to PIN. |
| M3 | Portfolio Summary Widget | 4h | High | React Native home screen widget (Android only initially). Shows: portfolio value, day P&L, top position. Updates every 15 min. |
| M4 | Real-Time Price Ticker Bar | 2h | Low | Horizontal scrolling FlatList at top of app. `BTC $73,034 ▼0.3% | ETH $2,259 ▲0.1%`. WebSocket or 5s polling. |
| M5 | Swipe to Close Position | 2h | Low | `react-native-gesture-handler` Swipeable on position rows. Swipe left reveals red "Close" button. Haptic feedback on swipe. |
| M6 | Offline Mode with Cached Data | 4h | Medium | AsyncStorage cache of last portfolio, positions, prices. Show stale data with "Last updated: 5 min ago" badge. Queue orders for when online. |

---

## MOBILE APPLICATION — SHOULD HAVE (25 hours total)

| # | Feature | Hours | Complexity | Implementation Approach |
|---|---------|-------|------------|------------------------|
| M7 | Native Charts (Interactive) | 8h | High | `react-native-wagmi-charts` or `victory-native`. Candlestick with pinch-to-zoom, pan, crosshair. 1m/5m/1h/4h selector. |
| M8 | Quick Trade from Notification | 4h | Medium | Actionable push notification: "BTC SHORT signal 62%" → [Execute] [Dismiss]. Deep link to trade screen with pre-filled data. |
| M9 | Voice Trading Commands | 6h | High | `expo-speech` + `@react-native-voice/voice`. Parse: "Buy 0.1 Bitcoin at market" → confirm modal → execute. Supported commands: buy, sell, close, status. |
| M10 | Shake to Emergency Stop | 2h | Low | `expo-sensors` accelerometer. 3 shakes in 2 seconds → confirm alert → `POST /api/risk/emergency-stop`. Kill switch activated. |
| M11 | QR Code API Key Import | 3h | Medium | `expo-barcode-scanner`. Generate QR on web settings page encoding `{exchange, api_key, api_secret}`. Scan in app → auto-populate token form. |
| M12 | Price Alerts with Sound | 2h | Low | `expo-av` custom alert sound. Local notification when price crosses target. Background check via `expo-task-manager` every 60s. |

---

## MOBILE APPLICATION — BETTER TO HAVE (45 hours total)

| # | Feature | Hours | Complexity | Implementation Approach |
|---|---------|-------|------------|------------------------|
| M13 | Apple Watch / WearOS Companion | 12h | Very High | WatchOS: SwiftUI widget. WearOS: Jetpack Compose tile. Shows portfolio value, top 3 positions, P&L. Complication for watch face. |
| M14 | Dark/Light/AMOLED Themes | 3h | Low | Three theme objects. AMOLED = pure #000000 backgrounds. Theme selector in settings. Persist with AsyncStorage. |
| M15 | Haptic Feedback on Trade | 1h | Very Low | `expo-haptics` → strong impact on trade fill, light impact on button press, warning notification on SL/TP trigger. |
| M16 | Multi-Language (Hindi/Tamil/English) | 6h | Medium | `i18n-js` or `react-i18next`. Translation JSON files for 3 languages. Language selector in settings. RTL support not needed. |
| M17 | Social Feed | 8h | High | Feed of trades from followed users. Like/comment. Strategy discussions. `expo-image` for screenshots. Infinite scroll with pagination. |
| M18 | AR Portfolio Visualization | 15h | Very High | `viro-react` or `expo-three`. 3D scene: floating bubbles per position (size = allocation, color = P&L). Tap bubble for details. Novelty feature. |

---

## Sprint Delivery Schedule

### Sprint 1: DONE ✅ (Week 1)
- [x] W1: SSL/HTTPS config + setup script
- [x] W2: Portfolio persistence (Docker volume)
- [x] W3: Trade confirmation modal
- [x] W4: WebSocket real-time prices (backend + frontend)
- [x] W5: Position close confirmation modal
- [x] W6: Centralized error handler
- [x] W7: Exchange API key validation on save
- [x] W8: Equity curve chart (backend + frontend)

### Sprint 2: High-Value Web (Week 2-3, ~25h)
- [ ] W9: Watchlist page (4h)
- [ ] W10: Price alerts page (4h)
- [ ] W13: Email on SL/TP (3h)
- [ ] W14: Strategy comparison (4h)
- [ ] W16: Position sizing calculator (2h)
- [ ] W17: Duplicate trade prevention (2h)
- [ ] W12: Trade journal (8h)

### Sprint 3: Mobile Core (Week 3-4, ~21h)
- [ ] M1: Push notifications (6h)
- [ ] M2: Biometric auth (3h)
- [ ] M4: Price ticker bar (2h)
- [ ] M5: Swipe to close (2h)
- [ ] M6: Offline mode (4h)
- [ ] M3: Portfolio widget (4h)

### Sprint 4: Advanced Web (Week 5-6, ~23h)
- [ ] W11: Multi-timeframe chart (6h)
- [ ] W15: Dark/light theme (4h)
- [ ] W18: AI trade recommendations (8h)
- [ ] W21: Tax report export (4h)

### Sprint 5: Mobile Enhanced (Week 6-7, ~25h)
- [ ] M7: Native charts (8h)
- [ ] M8: Quick trade from notification (4h)
- [ ] M9: Voice trading (6h)
- [ ] M10: Shake to stop (2h)
- [ ] M11: QR key import (3h)
- [ ] M12: Price alerts sound (2h)

### Sprint 6: Platform & Social (Week 8-10, ~58h)
- [ ] W22: Social copy trading (12h)
- [ ] W23: Strategy marketplace (10h)
- [ ] W24: Advanced orders (8h)
- [ ] W26: Webhook integration (4h)
- [ ] W27: Replay mode (10h)
- [ ] M16: Multi-language (6h)
- [ ] M17: Social feed (8h)

### Sprint 7: Polish (Week 10-12, ~37h)
- [ ] W19: Portfolio heatmap (4h)
- [ ] W20: Correlation matrix (3h)
- [ ] W25: Multi-account (6h)
- [ ] M13: Watch companion (12h)
- [ ] M14: AMOLED themes (3h)
- [ ] M15: Haptic feedback (1h)
- [ ] M18: AR visualization (15h, optional stretch goal)

---

## Technical Debt (parallel with features)

| Item | Hours | Sprint |
|------|-------|--------|
| SQLite → PostgreSQL | 8h | Sprint 2 |
| Test coverage → 80%+ | 12h | Sprint 2-3 |
| CI/CD (GitHub Actions → VPS) | 4h | Sprint 2 |
| Docker health checks | 2h | Sprint 2 |
| API rate limiting per user | 3h | Sprint 3 |
| Structured logging (ELK ready) | 4h | Sprint 4 |
| Secrets management | 4h | Sprint 3 |
| **Total tech debt** | **37h** | |

---

## Grand Total

| Category | Hours |
|----------|-------|
| 46 Features | 211h |
| Technical Debt | 37h |
| **TOTAL** | **~248h** |
| **At 6h/day** | **~41 working days** |
| **At 8h/day** | **~31 working days** |

---

*Alchemy AI Trading Platform v0.9.0 → v1.0.0 Roadmap*  
*121 Python files | 210 API routes | 190+ commits*
