"""
FastAPI Server for Alchemy Trading Bot.
Provides REST API and WebSocket for mobile app and web dashboard.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from config import config
from src.exchange import DeltaExchangeClient
from src.intelligence import EmotionEngine, GeopoliticalAnalyzer, NewsFetcher
from src.strategy import TradingStrategy
from src.risk import RiskManager
from src.autonomous import AIOrchestrator, PortfolioManager
from src.utils.logger import get_logger

logger = get_logger("alchemy.server")

app = FastAPI(
    title="Alchemy Trading API",
    description="Autonomous crypto trading with geopolitical emotion intelligence",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────
# Global State
# ─────────────────────────────────────────────────────

class AppState:
    def __init__(self):
        self.exchange = DeltaExchangeClient(
            api_key=config.delta.api_key,
            api_secret=config.delta.api_secret,
            base_url=config.delta.base_url,
        )
        self.emotion_engine = EmotionEngine(
            api_key=config.anthropic.api_key,
            model=config.anthropic.model,
        )
        self.geo_analyzer = GeopoliticalAnalyzer()
        self.news_fetcher = NewsFetcher(
            news_api_key=config.news.news_api_key,
            rss_feeds=config.news.rss_feeds,
            keywords=config.news.geopolitical_keywords,
        )
        self.strategy = TradingStrategy(config)
        self.risk_manager = RiskManager(config)
        self.portfolio = PortfolioManager()
        self.orchestrator = AIOrchestrator(
            config=config,
            exchange=self.exchange,
            emotion_engine=self.emotion_engine,
            geo_analyzer=self.geo_analyzer,
            news_fetcher=self.news_fetcher,
            strategy=self.strategy,
            risk_manager=self.risk_manager,
            state_broadcaster=self._broadcast_state,
        )
        self.ws_clients: list[WebSocket] = []
        self.last_broadcast: dict = {}
        self.bot_running: bool = False
        self.bot_task: Optional[asyncio.Task] = None

    def _broadcast_state(self, data: dict):
        self.last_broadcast = data
        asyncio.create_task(self._ws_broadcast(data))

    async def _ws_broadcast(self, data: dict):
        disconnected = []
        for ws in self.ws_clients:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in self.ws_clients:
                self.ws_clients.remove(ws)


app_state = AppState()

# ─────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────

class BotControlRequest(BaseModel):
    action: str  # "start", "stop", "pause"
    interval_minutes: Optional[int] = None

class TradeRequest(BaseModel):
    symbol: str
    side: str
    size_usd: float
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 4.0
    leverage: int = 5

class ConfigUpdateRequest(BaseModel):
    symbol: Optional[str] = None
    dry_run: Optional[bool] = None
    interval_minutes: Optional[int] = None
    position_size_usd: Optional[float] = None
    leverage: Optional[int] = None

# ─────────────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    app_state.ws_clients.append(ws)
    logger.info(f"WebSocket client connected. Total: {len(app_state.ws_clients)}")
    try:
        # Send current state immediately on connect
        if app_state.last_broadcast:
            await ws.send_json(app_state.last_broadcast)
        while True:
            await ws.receive_text()  # Keep alive
    except WebSocketDisconnect:
        if ws in app_state.ws_clients:
            app_state.ws_clients.remove(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(app_state.ws_clients)}")

# ─────────────────────────────────────────────────────
# REST Endpoints
# ─────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("dashboard/index.html")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "bot_running": app_state.bot_running,
        "ws_clients": len(app_state.ws_clients),
        "dry_run": config.trading.dry_run,
        "symbol": config.trading.symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/api/status")
async def get_status():
    state = app_state.orchestrator.state
    return {
        "bot_running": app_state.bot_running,
        "cycle_count": state.cycle_count,
        "total_trades": state.total_trades,
        "current_mode": state.current_mode,
        "last_action": state.last_action,
        "last_action_time": state.last_action_time,
        "status_message": state.status_message,
        "dry_run": config.trading.dry_run,
        "symbol": config.trading.symbol,
        "ws_clients": len(app_state.ws_clients),
    }

@app.get("/api/portfolio")
async def get_portfolio():
    try:
        if config.trading.dry_run:
            balance = 10000.0
        else:
            bal = app_state.exchange.get_wallet_balance("USDT")
            balance = bal.get("available_balance", 0)
        stats = app_state.portfolio.get_stats(balance)
        return {
            "stats": stats,
            "equity_curve": app_state.portfolio.equity_curve,
            "trades": app_state.portfolio.trade_log,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/positions")
async def get_positions():
    try:
        if config.trading.dry_run:
            return {"positions": [], "dry_run": True}
        positions = app_state.exchange.get_positions()
        return {
            "positions": [
                {
                    "symbol": p.symbol, "side": p.side, "size": p.size,
                    "entry_price": p.entry_price,
                    "liquidation_price": p.liquidation_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl": p.realized_pnl,
                    "leverage": p.leverage,
                }
                for p in positions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/market/{symbol}")
async def get_market(symbol: str):
    try:
        if config.trading.dry_run:
            import random
            return {
                "symbol": symbol, "mark_price": 67000 + random.uniform(-1000, 1000),
                "change_24h_pct": random.uniform(-5, 5),
                "volume_24h": 28000, "dry_run": True
            }
        ticker = app_state.exchange.get_ticker(symbol)
        return {
            "symbol": ticker.symbol, "mark_price": ticker.mark_price,
            "last_price": ticker.last_price, "bid": ticker.bid, "ask": ticker.ask,
            "volume_24h": ticker.volume_24h, "change_24h_pct": ticker.change_24h_pct,
            "open_interest": ticker.open_interest,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/emotion")
async def get_emotion():
    try:
        articles = app_state.news_fetcher.fetch()
        emotion = app_state.emotion_engine.analyze(articles)
        geo_events = app_state.geo_analyzer.analyze(articles)
        geo = app_state.geo_analyzer.get_aggregate_impact(geo_events)
        return {
            "emotion": {
                "sentiment_score": emotion.sentiment_score,
                "crypto_sentiment": emotion.crypto_specific_sentiment,
                "dominant_emotion": emotion.dominant_emotion,
                "confidence": emotion.confidence,
                "geopolitical_risk": emotion.geopolitical_risk,
                "trading_bias": emotion.trading_bias,
                "key_events": emotion.key_events,
                "reasoning": emotion.reasoning,
                "emotions_breakdown": emotion.emotions,
            },
            "geopolitical": geo,
            "articles_count": len(articles),
            "top_articles": [
                {"title": a.title, "source": a.source,
                 "score": a.relevance_score, "published": a.published_at}
                for a in articles[:15]
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/news")
async def get_news(limit: int = 20):
    articles = app_state.news_fetcher.fetch()
    return {
        "articles": [
            {"title": a.title, "summary": a.summary[:200], "source": a.source,
             "url": a.url, "score": a.relevance_score, "published": a.published_at}
            for a in articles[:limit]
        ],
        "total": len(articles),
    }

@app.get("/api/decisions")
async def get_decisions(limit: int = 20):
    return {
        "decisions": app_state.orchestrator.state.decisions[:limit],
        "total_trades": app_state.orchestrator.state.total_trades,
    }

@app.post("/api/bot/control")
async def control_bot(req: BotControlRequest, background_tasks: BackgroundTasks):
    if req.action == "start":
        if app_state.bot_running:
            return {"status": "already_running"}
        if req.interval_minutes:
            config.trading.analysis_interval_minutes = req.interval_minutes
        app_state.bot_running = True
        background_tasks.add_task(_run_bot_loop)
        return {"status": "started", "interval_minutes": config.trading.analysis_interval_minutes}

    elif req.action == "stop":
        app_state.bot_running = False
        return {"status": "stopped"}

    elif req.action == "cycle":
        # Run one manual cycle
        background_tasks.add_task(_run_single_cycle)
        return {"status": "cycle_triggered"}

    raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

@app.get("/api/forecast")
async def get_forecast(symbol: str = "BTCUSD"):
    """Run MarketForecaster on recent candles and return structured forecast."""
    try:
        from src.intelligence.market_forecaster import MarketForecaster

        candles = []
        current_price = 0.0

        if config.trading.dry_run:
            import random, math
            base = 67000.0
            for i in range(100):
                trend = 15.0 * math.sin(i / 10) + i * 3
                noise = random.gauss(0, 80)
                c = base + trend + noise
                candles.append({
                    "close": c, "open": c - random.uniform(-50, 50),
                    "high": c + random.uniform(30, 120),
                    "low":  c - random.uniform(30, 120),
                    "volume": random.uniform(150, 400),
                })
            current_price = candles[-1]["close"]
        else:
            try:
                raw = app_state.exchange.get_candles(symbol, resolution="1h", count=100)
                candles = raw
                ticker = app_state.exchange.get_ticker(symbol)
                current_price = ticker.mark_price
            except Exception:
                return {"error": "Failed to fetch candle data", "symbol": symbol}

        if not candles or current_price == 0.0:
            return {"error": "No candle data available", "symbol": symbol}

        forecaster = MarketForecaster(config)
        fc = forecaster.forecast(candles, current_price)

        tc = config.trading
        leverage  = getattr(tc, "leverage", 5)
        taker_fee = getattr(tc, "taker_fee_rate", 0.0005)
        rt_fee_pct = taker_fee * 2 * leverage * 100

        return {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "candles_used": len(candles),
            "adx": fc.adx,
            "plus_di": fc.plus_di,
            "minus_di": fc.minus_di,
            "trend_direction": fc.trend_direction,
            "trend_strength": fc.trend_strength_label,
            "is_trending": fc.is_trending,
            "market_regime": fc.market_regime,
            "regime_confidence": fc.regime_confidence,
            "forecast_price_1": fc.forecast_price_1,
            "forecast_price_3": fc.forecast_price_3,
            "forecast_price_5": fc.forecast_price_5,
            "forecast_bias": fc.forecast_bias,
            "forecast_slope_pct": fc.forecast_slope_pct,
            "regression_r2": fc.regression_r2,
            "vwap": fc.vwap,
            "vwap_position": fc.vwap_position,
            "vwap_distance_pct": fc.vwap_distance_pct,
            "pivot_point": fc.pivot_point,
            "resistance_levels": fc.resistance_levels,
            "support_levels": fc.support_levels,
            "breakeven_move_pct": fc.breakeven_move_pct,
            "round_trip_fee_pct": rt_fee_pct,
            "taker_fee_pct": taker_fee * 100,
            "leverage": leverage,
            "forecast_score": fc.forecast_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Forecast error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ml/analyze")
async def ml_analyze(symbol: str = "BTCUSD"):
    """Run full ML pipeline: price prediction, anomaly detection, sentiment, signal."""
    try:
        from src.ml.model_trainer import MLEngine

        candles = []
        current_price = 0.0

        if config.trading.dry_run:
            import random, math
            base = 67000.0
            for i in range(200):
                trend = 20.0 * math.sin(i / 15) + i * 2.5
                noise = random.gauss(0, 90)
                c = base + trend + noise
                candles.append({
                    "close": c, "open": c - random.uniform(-60, 60),
                    "high": c + random.uniform(40, 130),
                    "low":  c - random.uniform(40, 130),
                    "volume": random.uniform(100, 500),
                })
            current_price = candles[-1]["close"]
        else:
            try:
                raw = app_state.exchange.get_candles(symbol, resolution="1h", count=200)
                candles = raw
                ticker = app_state.exchange.get_ticker(symbol)
                current_price = ticker.mark_price
            except Exception:
                return {"error": "Failed to fetch candle data", "symbol": symbol}

        if not candles or current_price == 0.0:
            return {"error": "No candle data available", "symbol": symbol}

        # Fetch recent headlines for sentiment
        try:
            articles = app_state.news_fetcher.fetch()
            headlines = [a.title for a in articles[:20] if a.title]
        except Exception:
            headlines = []

        ml_engine = MLEngine()
        analysis = ml_engine.analyze(candles, current_price, headlines)
        result = analysis.to_dict()
        result["symbol"] = symbol
        result["timestamp"] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as e:
        logger.error(f"ML analyze error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ml/train")
async def ml_train(background_tasks: BackgroundTasks):
    """Trigger ML model retraining in background."""
    try:
        from src.ml.model_trainer import MLEngine

        async def _do_train():
            candles = []
            if config.trading.dry_run:
                import random, math
                base = 67000.0
                for i in range(300):
                    trend = 20.0 * math.sin(i / 15) + i * 2.0
                    noise = random.gauss(0, 100)
                    c = base + trend + noise
                    candles.append({
                        "close": c, "open": c - random.uniform(-70, 70),
                        "high": c + random.uniform(50, 150),
                        "low":  c - random.uniform(50, 150),
                        "volume": random.uniform(120, 600),
                    })
            else:
                try:
                    candles = app_state.exchange.get_candles(
                        config.trading.symbol, resolution="1h", count=300
                    )
                except Exception:
                    return
            ml_engine = MLEngine()
            ml_engine.train_now(candles)

        background_tasks.add_task(_do_train)
        return {"status": "training_started", "message": "ML models training in background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ml/status")
async def ml_status():
    """Return current ML model status."""
    try:
        from src.ml.model_trainer import MLEngine
        ml_engine = MLEngine()
        return ml_engine.get_model_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SentimentRequest(BaseModel):
    headlines: list[str]


@app.post("/api/ml/sentiment")
async def ml_sentiment(req: SentimentRequest):
    """Analyze sentiment of provided headlines."""
    try:
        from src.ml.sentiment_analyzer import SentimentAnalyzer
        analyzer = SentimentAnalyzer()
        results = analyzer.analyze_batch(req.headlines)
        agg = analyzer.aggregate(results)
        return {
            "aggregate": agg,
            "individual": [r.to_dict() for r in results],
            "count": len(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trade")
async def manual_trade(req: TradeRequest):
    """Manually place a trade (bypasses autonomous AI)."""
    from src.exchange.delta_client import Order
    try:
        if config.trading.dry_run:
            return {
                "status": "dry_run_simulated",
                "symbol": req.symbol, "side": req.side,
                "size_usd": req.size_usd,
            }
        product_id = app_state.exchange.get_product_id(req.symbol)
        if not product_id:
            raise HTTPException(status_code=404, detail=f"Symbol {req.symbol} not found")
        app_state.exchange.set_leverage(product_id, req.leverage)
        contracts = max(int(req.size_usd * req.leverage), 1)
        order = Order(symbol=req.symbol, side=req.side, order_type="market", size=contracts)
        result = app_state.exchange.place_order(order, product_id)
        return {"status": "executed", "order": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    if req.symbol:
        config.trading.symbol = req.symbol
    if req.dry_run is not None:
        config.trading.dry_run = req.dry_run
    if req.interval_minutes:
        config.trading.analysis_interval_minutes = req.interval_minutes
    if req.position_size_usd:
        config.trading.position_size_usd = req.position_size_usd
    if req.leverage:
        config.trading.leverage = req.leverage
    return {
        "symbol": config.trading.symbol,
        "dry_run": config.trading.dry_run,
        "interval_minutes": config.trading.analysis_interval_minutes,
        "position_size_usd": config.trading.position_size_usd,
        "leverage": config.trading.leverage,
    }

@app.get("/api/config")
async def get_config():
    return {
        "symbol": config.trading.symbol,
        "dry_run": config.trading.dry_run,
        "interval_minutes": config.trading.analysis_interval_minutes,
        "position_size_usd": config.trading.position_size_usd,
        "leverage": config.trading.leverage,
        "risk_per_trade_pct": config.trading.risk_per_trade_pct,
        "stop_loss_pct": config.trading.stop_loss_pct,
        "take_profit_pct": config.trading.take_profit_pct,
        "bullish_threshold": config.trading.bullish_threshold,
        "bearish_threshold": config.trading.bearish_threshold,
        "max_positions": config.trading.max_open_positions,
    }

# ─────────────────────────────────────────────────────
# Background Tasks
# ─────────────────────────────────────────────────────

async def _run_bot_loop():
    logger.info("Autonomous bot loop started")
    while app_state.bot_running:
        await _run_single_cycle()
        interval = config.trading.analysis_interval_minutes * 60
        # Broadcast countdown updates every 60s
        for remaining in range(interval, 0, -60):
            if not app_state.bot_running:
                break
            await asyncio.sleep(min(60, remaining))

    logger.info("Bot loop stopped")

async def _run_single_cycle():
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, app_state.orchestrator.run_cycle
        )
        # Update portfolio
        balance = 10000.0 if config.trading.dry_run else 0
        try:
            if not config.trading.dry_run:
                bal = app_state.exchange.get_wallet_balance("USDT")
                balance = bal.get("available_balance", 0)
        except Exception:
            pass
        app_state.portfolio.update_equity(balance)

        # Broadcast updated state
        broadcast_data = {
            "type": "cycle_complete",
            "cycle_result": result,
            "portfolio": app_state.portfolio.get_stats(balance),
            "equity_curve": app_state.portfolio.equity_curve[-100:],
            "trade_log": app_state.portfolio.trade_log[:20],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await app_state._ws_broadcast(broadcast_data)

    except Exception as e:
        logger.error(f"Bot cycle error: {e}", exc_info=True)

# Serve dashboard static files
try:
    app.mount("/static", StaticFiles(directory="dashboard"), name="static")
except Exception:
    pass
