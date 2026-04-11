"""
alchemy.api.features_routes — API for all 20 new features
============================================================
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from alchemy.auth.middleware import get_current_user, CurrentUser

router = APIRouter(prefix="/features", tags=["features"])


# ── Feature 1: Auto-Trade Scheduler ──────────────────────────────────────────
@router.get("/scheduler")
async def get_schedules(user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import get_scheduler
    return {"schedules": get_scheduler().get_schedules(user.user_id)}

@router.post("/scheduler")
async def add_schedule(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import get_scheduler
    s = get_scheduler().add_schedule(user.user_id, **body)
    return {"ok": True, "schedule": s.to_dict()}

@router.delete("/scheduler/{schedule_id}")
async def remove_schedule(schedule_id: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import get_scheduler
    get_scheduler().remove_schedule(user.user_id, schedule_id)
    return {"ok": True}

@router.post("/scheduler/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import get_scheduler
    result = get_scheduler().toggle_schedule(user.user_id, schedule_id)
    return {"ok": True, "schedule": result}


# ── Feature 2: Strategy Builder ──────────────────────────────────────────────
@router.get("/strategy-builder/conditions")
async def get_conditions(user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_available_conditions
    return get_available_conditions()

@router.post("/strategy-builder")
async def create_strategy(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import create_strategy
    return create_strategy(user.user_id, **body)

@router.get("/strategy-builder")
async def list_strategies(user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_strategies
    return {"strategies": get_strategies(user.user_id)}


# ── Feature 3: Telegram Bot ─────────────────────────────────────────────────
@router.get("/telegram/status")
async def telegram_status(user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_telegram_bot
    return get_telegram_bot().to_dict()

@router.post("/telegram/link")
async def telegram_link(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_telegram_bot
    return get_telegram_bot().register_chat(user.user_id, body.get("chat_id", ""))


# ── Feature 4: Multi-Account ────────────────────────────────────────────────
@router.get("/accounts")
async def get_accounts(user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_accounts, get_aggregate_portfolio
    return {
        "accounts": get_accounts(user.user_id),
        "aggregate": get_aggregate_portfolio(user.user_id),
    }

@router.post("/accounts")
async def add_account(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import add_account
    return add_account(user.user_id, **body)


# ── Feature 5: AI Signal Generator ──────────────────────────────────────────
@router.get("/signals/{symbol}")
async def get_signals(symbol: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.signals.engine import generate_signals
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"https://api.binance.com/api/v3/klines",
            params={"symbol": symbol.upper(), "interval": "1h", "limit": 100})
        candles = [{"open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                     "close": float(k[4]), "volume": float(k[5])} for k in resp.json()]
    signals = generate_signals(candles, symbol.upper())
    return {"symbol": symbol, "signals": [s.to_dict() for s in signals],
            "count": len(signals)}


# ── Feature 6: Options Chain ────────────────────────────────────────────────
@router.get("/options/{symbol}")
async def get_options_chain(symbol: str, dte: int = 30,
                             user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import generate_options_chain
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"https://api.binance.com/api/v3/ticker/price",
            params={"symbol": symbol.upper()})
        spot = float(resp.json()["price"])
    return generate_options_chain(spot, dte_days=dte)


# ── Feature 7: Tax Report ───────────────────────────────────────────────────
@router.get("/tax-report")
async def get_tax_report(fy: str = "2025-26",
                          user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import generate_tax_report
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)
    return generate_tax_report(portfolio.trade_log, fy)


# ── Feature 8: Trailing Stop-Loss ───────────────────────────────────────────
@router.post("/trailing-stop")
async def add_trailing(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import add_trailing_stop
    return add_trailing_stop(user.user_id, body["symbol"], body.get("side", "long"),
                              body.get("trail_pct", 2), body.get("trail_amount", 0),
                              body.get("price", 0))

@router.get("/trailing-stop")
async def get_trailing(user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import get_trailing_stops
    return {"stops": get_trailing_stops(user.user_id)}

@router.post("/trailing-stop/update")
async def update_trailing(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import update_trailing_stops
    events = update_trailing_stops(user.user_id, body.get("prices", {}))
    return {"events": events}


# ── Feature 9: DCA Bot ──────────────────────────────────────────────────────
@router.post("/dca")
async def create_dca(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import add_dca
    return add_dca(user.user_id, **body)

@router.get("/dca")
async def list_dca(user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import get_dcas
    return {"dca_configs": get_dcas(user.user_id)}

@router.delete("/dca/{dca_id}")
async def delete_dca(dca_id: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.scheduler.auto_trader import remove_dca
    remove_dca(user.user_id, dca_id)
    return {"ok": True}


# ── Feature 10: News Sentiment ──────────────────────────────────────────────
@router.get("/sentiment/{symbol}")
async def get_sentiment(symbol: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.signals.engine import fetch_crypto_sentiment, get_market_sentiment_summary
    articles = await fetch_crypto_sentiment(symbol.upper().replace("USDT", ""))
    summary = get_market_sentiment_summary(articles)
    return {"symbol": symbol, "summary": summary, "articles": articles[:15]}


# ── Feature 11: Correlation Matrix ───────────────────────────────────────────
@router.get("/correlations")
async def get_correlations(user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import calculate_correlation_matrix
    import httpx
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    prices = {}
    async with httpx.AsyncClient(timeout=15) as client:
        for sym in symbols:
            resp = await client.get(f"https://api.binance.com/api/v3/klines",
                params={"symbol": sym, "interval": "1d", "limit": 90})
            prices[sym] = [float(k[4]) for k in resp.json()]
    return calculate_correlation_matrix(prices)


# ── Feature 12: API Key Vault ───────────────────────────────────────────────
@router.get("/vault")
async def list_vault(user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import get_vault
    return {"keys": get_vault().list_keys(user.user_id)}

@router.post("/vault")
async def store_key(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import get_vault
    return get_vault().store(user.user_id, body["exchange"], body["api_key"], body["api_secret"])

@router.delete("/vault/{exchange}")
async def delete_key(exchange: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import get_vault
    get_vault().delete(user.user_id, exchange)
    return {"ok": True}


# ── Feature 13: Webhook Alerts ──────────────────────────────────────────────
@router.get("/webhooks")
async def list_webhooks(user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import get_webhooks
    return {"webhooks": get_webhooks(user.user_id)}

@router.post("/webhooks")
async def add_webhook(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import register_webhook
    return register_webhook(user.user_id, body["name"], body["url"], body.get("events"))

@router.post("/webhooks/test")
async def test_webhook(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import send_webhook
    result = await send_webhook(body["url"], {
        "title": "Alchemy Test Alert", "message": "Webhook is working!",
        "type": "test", "data": {"symbol": "BTCUSDT", "price": 71000},
    })
    return result


# ── Feature 14: Arbitrage Detector ──────────────────────────────────────────
@router.get("/arbitrage")
async def detect_arb(user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import detect_arbitrage
    return {"opportunities": await detect_arbitrage()}


# ── Feature 15: Risk Dashboard ──────────────────────────────────────────────
@router.get("/risk-dashboard")
async def risk_dashboard(user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import calculate_risk_metrics
    from alchemy.paper_trading.engine import get_paper_engine
    portfolio = get_paper_engine().get_portfolio(user.user_id)
    # Build equity curve from trades
    balance = portfolio.initial_balance
    curve = [balance]
    for t in portfolio.trade_log:
        balance += t.get("net_pnl", 0)
        curve.append(balance)
    if len(curve) < 10:
        return {"message": "Need at least 10 trades for risk analysis", "trades": len(portfolio.trade_log)}
    return calculate_risk_metrics(curve)


# ── Feature 16: Strategy Marketplace ────────────────────────────────────────
@router.get("/marketplace")
async def browse_market(user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import browse_marketplace
    return {"strategies": browse_marketplace()}

@router.post("/marketplace/publish")
async def publish(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import publish_strategy
    result = publish_strategy(user.user_id, body["strategy_id"], body.get("price_usd", 0))
    if not result: raise HTTPException(404, "Strategy not found")
    return result

@router.post("/marketplace/{listing_id}/subscribe")
async def subscribe(listing_id: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import subscribe_strategy
    return subscribe_strategy(user.user_id, listing_id)


# ── Feature 17: Competitions ────────────────────────────────────────────────
@router.get("/competitions")
async def list_competitions(user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_competitions
    return {"competitions": get_competitions()}

@router.post("/competitions/{comp_id}/join")
async def join_comp(comp_id: str, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import join_competition
    return join_competition(comp_id, user.user_id)

@router.post("/competitions")
async def create_comp(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import create_competition
    return create_competition(**body)


# ── Feature 18: Custom Indicators ───────────────────────────────────────────
@router.get("/indicators")
async def list_indicators(user: CurrentUser = Depends(get_current_user)):
    from alchemy.signals.engine import get_custom_indicators, BUILTIN_INDICATORS
    return {
        "builtin": list(BUILTIN_INDICATORS.keys()),
        "custom": get_custom_indicators(user.user_id),
    }

@router.post("/indicators")
async def add_indicator(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.signals.engine import add_custom_indicator
    return add_custom_indicator(user.user_id, body["name"], body["formula"], body.get("params"))


# ── Feature 19: Order Book Depth ────────────────────────────────────────────
@router.get("/orderbook/{symbol}")
async def get_orderbook(symbol: str, limit: int = 20,
                         user: CurrentUser = Depends(get_current_user)):
    from alchemy.tools.analytics import fetch_order_book
    return await fetch_order_book(symbol.upper(), limit)


# ── Feature 20: Rebalance Bot ───────────────────────────────────────────────
@router.post("/rebalance-bot/configure")
async def configure_rebalance(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_rebalance_bot
    try:
        config = get_rebalance_bot().configure(
            user.user_id, body["targets"],
            body.get("threshold_pct", 5), body.get("frequency", "weekly"),
            body.get("tax_loss_harvest", False),
        )
        return {"ok": True, "config": config}
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("/rebalance-bot/status")
async def rebalance_status(user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_rebalance_bot
    config = get_rebalance_bot().get_config(user.user_id)
    if not config: return {"configured": False}
    return {"configured": True, **config}

@router.post("/rebalance-bot/check")
async def check_rebalance_drift(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.social.features import get_rebalance_bot
    return get_rebalance_bot().check_drift(user.user_id, body.get("current_values", {}))
