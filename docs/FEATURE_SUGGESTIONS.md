# Alchemy AI Trading Platform — Feature Suggestions

**Version:** v0.9.0 → v1.0.0+ Roadmap  
**Date:** April 2026  
**Platform Stats:** 119 Python files | 24,796 lines | 210 API routes | 33 Frontend files | 182 commits

---

## Current State Summary

| Area | Status | Rating |
|------|--------|--------|
| Paper Trading (LONG + SHORT) | ✅ Working | 8/10 |
| Autonomous Trading Engine | ✅ Working (skip duplicates, paper bridge) | 7/10 |
| Live Trading (Binance/Delta) | ✅ Fixed (was broken — `_load_token` bug) | 6/10 |
| Portfolio Dashboard | ✅ Live prices every 5s, 6 summary cards | 8/10 |
| SL/TP Triggers | ✅ Working (checked on price update) | 7/10 |
| Capital Allocation | ✅ Shows position breakdown | 7/10 |
| Backtesting | ✅ Working (SMA, RSI, MACD, Bollinger) | 6/10 |
| Mobile App (APK) | ✅ WebView wrapper | 4/10 |
| Auth (JWT + 2FA) | ✅ Working | 8/10 |
| Risk Management | ✅ Kill switch, rate limiter, dedup | 7/10 |

---

## Copilot PR Review (PRs #103, #104, #105)

### PR #103 — Security + Mobile
- ✅ X-Forwarded-For fix (rightmost public IP)
- ✅ Various security hardening
- ⚠️ No functional conflicts with our changes

### PR #104 — Watchlist, Price Alerts, CVaR
- ✅ `watchlist_routes.py` — 222 lines, user watchlists with notes
- ✅ `alert_routes.py` — 278 lines, price alert triggers
- ✅ `cvar.py` — CVaR (Conditional Value at Risk) + Kelly criterion
- ⚠️ Alert routes mounted but no frontend pages yet
- **Suggestion:** Build frontend pages for Watchlist and Alerts

### PR #105 — Trade Logic Tests + Architecture Docs
- ✅ 56 unit tests in `tests/unit/test_trade_logic.py`
- ✅ API Gateway architecture doc
- ✅ Microservices evolution roadmap
- ✅ CHANGELOG with versioned entries
- ⚠️ Strategy engine changes may conflict with autonomous engine
- **Suggestion:** Run full test suite before production deployment

---

## WEB APPLICATION — Feature Suggestions

### 🔴 MUST HAVE (Critical for Production)

#### 1. SSL/HTTPS via Certbot
- **Why:** Currently "Not Secure" in browser; no data encryption
- **Effort:** 2 hours
- **How:** DNS → Cloudflare, then `certbot --nginx -d akilamirthya.in`

#### 2. Persistent Portfolio (SQLite/PostgreSQL)
- **Why:** Paper portfolio resets on container restart (in-memory only)
- **Effort:** 4 hours
- **How:** Save portfolios to `/data/paper_portfolios.json` on every trade, load on startup

#### 3. Trade Confirmation Modal
- **Why:** Accidental clicks can open positions; no confirmation before execution
- **Effort:** 2 hours
- **How:** Modal with order summary (symbol, side, qty, price, cost) + Confirm/Cancel buttons

#### 4. WebSocket Real-Time Prices
- **Why:** Currently polling Binance every 5s from browser (CSP issues, high latency)
- **Effort:** 6 hours
- **How:** Backend WebSocket stream → Binance WS → push to frontend via existing WS manager

#### 5. Position Close Confirmation
- **Why:** No warning before closing a position; could accidentally close profitable trade
- **Effort:** 1 hour
- **How:** Confirmation modal showing P&L before close

#### 6. Error Toast Improvement
- **Why:** Some errors show `[object Object]` instead of readable messages
- **Effort:** 1 hour
- **How:** Centralized error handler: `detail?.message || detail || "Unknown error"`

#### 7. Portfolio Persistence Across Restarts
- **Why:** Docker restart = all paper positions lost
- **Effort:** 3 hours
- **How:** Auto-save to `/data/paper_portfolios.json` every 30s + load on startup

#### 8. Exchange API Key Validation
- **Why:** Users can save invalid keys; errors only appear when trading
- **Effort:** 2 hours
- **How:** Test connection on save → show balance/error immediately

---

### 🟡 SHOULD HAVE (High Value)

#### 9. Equity Curve Chart
- **Why:** No visual history of portfolio performance over time
- **Effort:** 6 hours
- **How:** Store daily snapshot `{date, portfolio_value, cash, positions}` → Recharts line chart in dashboard

#### 10. Watchlist Page (Frontend)
- **Why:** Backend exists (PR #104) but no UI
- **Effort:** 4 hours
- **How:** React page with watchlist CRUD, live prices, quick-trade buttons

#### 11. Price Alerts Page (Frontend)
- **Why:** Backend exists (PR #104) but no UI
- **Effort:** 4 hours
- **How:** Alert creation form (symbol, price, direction), active alerts list, triggered alerts history

#### 12. Multi-Timeframe Chart
- **Why:** Currently only shows 1 timeframe at a time
- **Effort:** 6 hours
- **How:** Side-by-side or stacked charts: 1m, 15m, 1h, 4h on one screen

#### 13. Trade Journal
- **Why:** No way to annotate trades with notes, screenshots, lessons
- **Effort:** 8 hours
- **How:** Attach notes to closed trades, tag strategies, filter by win/loss

#### 14. Email Notifications on SL/TP
- **Why:** SL/TP triggers silently; user may not be watching dashboard
- **Effort:** 3 hours
- **How:** SMTP config already exists → trigger email on `_execute_stop()`

#### 15. Strategy Performance Comparison
- **Why:** No way to compare which strategy performs best
- **Effort:** 4 hours
- **How:** Group trades by strategy → show win rate, avg return, Sharpe per strategy

#### 16. Dark/Light Theme Toggle
- **Why:** Dark-only design; some users prefer light mode
- **Effort:** 4 hours
- **How:** Tailwind class-based dark mode toggle, persist in localStorage

#### 17. Position Sizing Calculator
- **Why:** Manual quantity calculation is error-prone
- **Effort:** 2 hours
- **How:** Input risk % → auto-calculate qty based on SL distance and account size

#### 18. Duplicate Trade Prevention (Live)
- **Why:** Could accidentally open same position twice on live exchange
- **Effort:** 2 hours
- **How:** Check exchange positions before placing order; warn if position exists

---

### 🟢 BETTER TO HAVE (Nice Additions)

#### 19. AI Trade Recommendations
- **Why:** Autonomous engine generates signals but doesn't explain reasoning to user
- **Effort:** 8 hours
- **How:** Display AI reasoning panel: "BTC SHORT because RSI=29 (oversold bounce expected), near lower BB, ATR stop=217"

#### 20. Portfolio Heatmap
- **Why:** No visual overview of which positions are winning/losing
- **Effort:** 4 hours
- **How:** Color-coded grid: green=profit, red=loss, size=allocation %

#### 21. Correlation Matrix Dashboard
- **Why:** Backend exists but no visualization
- **Effort:** 3 hours
- **How:** D3.js heatmap showing correlation between held positions

#### 22. Tax Report Export
- **Why:** Indian tax (STCG/LTCG/Crypto 30%) calculation exists but no export
- **Effort:** 4 hours
- **How:** PDF/CSV export with: trade date, buy/sell, P&L, holding period, tax category

#### 23. Social Copy Trading
- **Why:** Leaderboard exists but no way to follow/copy top traders
- **Effort:** 12 hours
- **How:** "Follow" button on leaderboard → auto-mirror trades with configurable allocation

#### 24. Strategy Marketplace
- **Why:** Backend scaffolding exists but no marketplace UI
- **Effort:** 10 hours
- **How:** Publish/subscribe to strategies, backtest before subscribing, revenue share

#### 25. Advanced Order Types
- **Why:** Only market orders currently; no OCO, bracket, trailing stop
- **Effort:** 8 hours
- **How:** OCO (One-Cancels-Other), bracket orders (entry + SL + TP as atomic unit)

#### 26. Multi-Account Support
- **Why:** Can only connect one API key per exchange
- **Effort:** 6 hours
- **How:** Multiple API keys per exchange, select account when trading

#### 27. Webhook Integration
- **Why:** No way to receive signals from TradingView or external systems
- **Effort:** 4 hours
- **How:** `/api/webhook/{token}` endpoint → parse TradingView JSON → execute trade

#### 28. Replay Mode
- **Why:** No way to practice on historical data with manual decisions
- **Effort:** 10 hours
- **How:** Load historical candles, step through one bar at a time, manual buy/sell decisions

---

## MOBILE APPLICATION — Feature Suggestions

### 🔴 MUST HAVE

#### M1. Push Notifications (Trade Fills, SL/TP, Signals)
- **Why:** Users miss trades when app is in background
- **Effort:** 6 hours
- **How:** Expo Notifications → backend sends push on trade event via FCM

#### M2. Biometric Auth (Fingerprint/Face)
- **Why:** PIN-only login; no biometric security for trading app
- **Effort:** 3 hours
- **How:** `expo-local-authentication` → lock trade execution behind biometric

#### M3. Portfolio Summary Widget
- **Why:** Must open app to see portfolio value
- **Effort:** 4 hours
- **How:** React Native home screen widget showing portfolio value + day P&L

#### M4. Real-Time Price Ticker Bar
- **Why:** No persistent price display
- **Effort:** 2 hours
- **How:** Scrolling ticker at top of app: BTC $73,034 ▼0.3% | ETH $2,259 ▲0.1%

#### M5. Swipe to Close Position
- **Why:** Closing requires navigating to positions → tap Close → confirm
- **Effort:** 2 hours
- **How:** Swipe left on position row → reveal Close button

#### M6. Offline Mode with Cached Data
- **Why:** App crashes or shows blank when network is down
- **Effort:** 4 hours
- **How:** AsyncStorage cache of last portfolio state; show stale data with "Offline" badge

---

### 🟡 SHOULD HAVE

#### M7. Native Charts (Interactive)
- **Why:** WebView charts are laggy; pinch-to-zoom doesn't work natively
- **Effort:** 8 hours
- **How:** `react-native-charts-wrapper` or `victory-native` for native candlestick charts

#### M8. Quick Trade from Notification
- **Why:** See signal notification → open app → navigate → trade (too slow)
- **Effort:** 4 hours
- **How:** Actionable notification: "BTC SHORT signal 62%" → [Execute] [Dismiss]

#### M9. Voice Trading Commands
- **Why:** Hands-free trading while multitasking
- **Effort:** 6 hours
- **How:** "Buy 0.1 Bitcoin at market" → speech-to-text → parse → confirm → execute

#### M10. Shake to Emergency Stop
- **Why:** Panic button on mobile; need instant kill switch
- **Effort:** 2 hours
- **How:** Accelerometer shake → confirmation alert → kill switch API call

#### M11. QR Code API Key Import
- **Why:** Typing API keys on mobile is painful and error-prone
- **Effort:** 3 hours
- **How:** Generate QR on exchange website → scan in app → auto-populate key fields

#### M12. Price Alerts with Sound
- **Why:** Visual alerts only; missed when phone is in pocket
- **Effort:** 2 hours
- **How:** Custom alert sound when price target hits

---

### 🟢 BETTER TO HAVE

#### M13. Apple Watch / WearOS Companion
- **Why:** Glanceable portfolio on wrist
- **Effort:** 12 hours
- **How:** Simple companion showing: portfolio value, top 3 positions, P&L

#### M14. Dark/Light/AMOLED Themes
- **Why:** AMOLED screens save battery with true black
- **Effort:** 3 hours
- **How:** Three theme options: Light, Dark (current), AMOLED Black (#000)

#### M15. Haptic Feedback on Trade
- **Why:** No tactile confirmation of trade execution
- **Effort:** 1 hour
- **How:** Strong vibration on fill, light vibration on button press

#### M16. Multi-Language (Hindi/Tamil/English)
- **Why:** India-first platform; not all users comfortable with English
- **Effort:** 6 hours
- **How:** i18n framework with language JSON files; language selector in settings

#### M17. Social Feed
- **Why:** Isolated trading experience; no community
- **Effort:** 8 hours
- **How:** Feed of trades from followed users; comment/like; strategy discussions

#### M18. AR Portfolio Visualization
- **Why:** Unique differentiator; immersive data experience
- **Effort:** 15 hours
- **How:** ARKit/ARCore → 3D portfolio globe; position sizes as floating bubbles

---

## Implementation Priority Matrix

```
                    HIGH IMPACT
                        │
         M1,1,2,7       │  9,10,11,14
     (Must Have)         │  (Should Have)
                         │
LOW EFFORT ──────────────┼─────────────── HIGH EFFORT
                         │
         5,6,8           │  23,24,28
     (Quick Wins)        │  (Future Vision)
                         │
                    LOW IMPACT
```

## Recommended Sprint Plan

### Sprint 1 (Week 1-2): Production Ready
- [x] Fix live trading (`_load_token` → `_load`)
- [x] Fix SHORT P&L calculations
- [x] Fix portfolio value for shorts
- [x] Skip duplicate positions
- [ ] #1 SSL/HTTPS
- [ ] #7 Portfolio persistence
- [ ] #3 Trade confirmation modal
- [ ] #M1 Push notifications

### Sprint 2 (Week 3-4): Dashboard Enhancement
- [ ] #9 Equity curve chart
- [ ] #4 WebSocket real-time prices
- [ ] #10 Watchlist page
- [ ] #11 Price alerts page
- [ ] #14 Email on SL/TP
- [ ] #M5 Swipe to close

### Sprint 3 (Week 5-6): Trading Intelligence
- [ ] #19 AI trade recommendations panel
- [ ] #15 Strategy performance comparison
- [ ] #17 Position sizing calculator
- [ ] #27 Webhook integration (TradingView)
- [ ] #M7 Native charts
- [ ] #M9 Voice trading

### Sprint 4 (Week 7-8): Scale & Social
- [ ] #23 Social copy trading
- [ ] #24 Strategy marketplace
- [ ] #22 Tax report export
- [ ] #M3 Portfolio widget
- [ ] #M16 Multi-language

---

## Technical Debt to Address

| Item | Priority | Effort |
|------|----------|--------|
| SQLite → PostgreSQL migration | High | 8h |
| In-memory portfolio → persistent storage | Critical | 3h |
| Test coverage (currently 17 test files) → 80%+ | High | 12h |
| Docker health checks + auto-restart | Medium | 2h |
| API rate limiting per user | Medium | 3h |
| Logging → structured JSON (ELK/Loki ready) | Medium | 4h |
| CI/CD pipeline (GitHub Actions → VPS deploy) | Medium | 4h |
| Secrets management (Vault/SOPS) | High | 4h |

---

*Generated by Alchemy AI Trading Platform — v0.9.0*  
*119 Python files | 210 API routes | 182 commits*
