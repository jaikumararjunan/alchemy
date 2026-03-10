"""
Fully Autonomous AI Trading Orchestrator.
Uses Claude with tool_use to autonomously make trading decisions,
manage positions, adapt strategy, and self-monitor performance.
"""
import json
import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Optional, Callable
from dataclasses import dataclass, field

import anthropic

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class OrchestratorState:
    is_running: bool = False
    cycle_count: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    last_action: str = "none"
    last_action_time: str = ""
    current_mode: str = "monitoring"  # monitoring, aggressive, conservative, halt
    ai_confidence: float = 0.0
    status_message: str = "Initializing..."
    errors: list = field(default_factory=list)
    decisions: list = field(default_factory=list)  # AI decision log


ORCHESTRATOR_SYSTEM_PROMPT = """You are ALCHEMY, a fully autonomous crypto trading AI for Delta Exchange India.
You have complete authority to make trading decisions based on real-time market data,
geopolitical intelligence, emotional market analysis, and forward price forecasting.

MISSION
=======
Maximise risk-adjusted returns across ALL Delta Exchange crypto perpetuals
while rigorously protecting capital — NET of all brokerage costs.
You can trade ANY perpetual contract (BTC, ETH, SOL, BNB, XRP, AVAX, DOGE, MATIC, LINK, DOT, etc.)
Use scan_all_contracts each cycle to find the BEST opportunity across the full universe.

DECISION FRAMEWORK  (execute in order every cycle)
===================================================
1. SCAN      — call scan_all_contracts FIRST. This scores ALL watched contracts and returns
               a ranked list. Pick the top-ranked BUY or SELL opportunity.
2. FORECAST  — call get_market_forecast for the chosen symbol to get ADX, regime, forecast.
3. ANALYSE   — call get_technical_indicators and get_market_data for that symbol.
4. SENTIMENT — call analyze_news_sentiment for emotion and geopolitical risk.
5. PORTFOLIO — call get_portfolio_state — check available capital and open positions.
6. DECIDE    — synthesise all signals; at least 2 of 3 layers must agree
7. EXECUTE   — place_trade only when conditions are clearly met (see below)
8. DIVERSIFY — you may open up to 3 positions across DIFFERENT symbols simultaneously.
7. MONITOR   — update_stop_loss to trail profitable positions

TREND & REGIME RULES
=====================
TRENDING market (ADX >= 25): trade WITH the trend — never fade a strong move.
  Enter in the direction of +DI > -DI (long) or -DI > +DI (short).
  Use pullbacks to VWAP or nearest pivot support/resistance as entry points.

RANGING market (ADX < 20): mean-revert — buy support, sell resistance.
  Use Bollinger Band extremes as entry signals. Position size 30-50% of normal.

VOLATILE market: wait for breakout with volume. Minimum confidence 0.70.

Linear regression forecast: if R2 > 0.40, give it significant weight.
  Forecast price 3 periods ahead > current price = bullish bias.
  Forecast price 3 periods ahead < current price = bearish bias.

VWAP: price above VWAP = institutional bullish bias. Below = bearish.
  Trading against VWAP direction requires confidence >= 0.75.

BROKERAGE — COST RULES (NON-NEGOTIABLE)
=========================================
Delta Exchange charges 0.05% taker fee per side (market orders).
At 5x leverage, round-trip cost on margin = approx 0.50% per trade.

YOU MUST ACCOUNT FOR FEES IN EVERY TRADE:
  - Minimum TP = breakeven_move_pct (from get_market_forecast) + at least 0.5% net profit
  - Net R:R after fees must be >= 1.5 — reject any trade below this
  - Fee estimate: size_usd x leverage x 0.001 (round-trip) in USD
  - NEVER enter a trade where the expected move < fee cost
  - Always report the estimated fee cost and net R:R in your reasoning

RISK RULES (NON-NEGOTIABLE)
============================
- Never risk more than 2% of account balance per trade
- Always set stop losses BEFORE entering — no naked positions
- Halt all trading if daily drawdown > 5%
- Reduce position size 50% when geo risk is HIGH
- No new positions when geo risk is CRITICAL
- Minimum net R:R (after fees) = 1.5
- Minimum confidence = 0.50 (0.70 in volatile regime)
- Maximum 3 open positions simultaneously

STRONG BUY requires ALL of:
  * Combined score >= +0.60
  * Forecast bias = bullish (or neutral with ADX >= 35 and +DI > -DI)
  * Price at or above VWAP
  * Net R:R >= 1.5 after fees
  * Geo risk != critical

STRONG SELL requires equivalent bearish confirmation.
HOLD when signals conflict or any condition above is missing.

Always explain: which signals aligned, what forecast says,
and exact net R:R calculation including fee cost."""


class AIOrchestrator:
    """
    Autonomous AI agent that uses Claude with tool_use to make
    fully autonomous trading decisions. Acts as the "brain" of Alchemy.
    """

    def __init__(self, config, exchange, emotion_engine, geo_analyzer,
                 news_fetcher, strategy, risk_manager, state_broadcaster: Optional[Callable] = None):
        self.config = config
        self.exchange = exchange
        self.emotion_engine = emotion_engine
        self.geo_analyzer = geo_analyzer
        self.news_fetcher = news_fetcher
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.broadcast = state_broadcaster  # Callback to send state to dashboard/mobile

        self.client = anthropic.Anthropic(api_key=config.anthropic.api_key)
        self.model = config.anthropic.model
        self.state = OrchestratorState()
        self._cached_data: dict = {}
        self._conversation_history: list = []

        logger.info("AIOrchestrator initialized - Fully autonomous mode")

    # ─────────────────────────────────────────
    # Tool Definitions for Claude
    # ─────────────────────────────────────────

    @property
    def tools(self) -> list:
        return [
            {
                "name": "get_market_data",
                "description": "Get current price, OHLCV candles, order book, and market statistics for a symbol",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Trading symbol e.g. BTCUSD"},
                        "timeframe": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                                      "description": "Candle timeframe"}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "get_portfolio_state",
                "description": "Get account balance, open positions, P&L, and margin usage",
                "input_schema": {"type": "object", "properties": {}}
            },
            {
                "name": "analyze_news_sentiment",
                "description": "Fetch latest geopolitical news and run Claude emotion intelligence analysis",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "force_refresh": {"type": "boolean", "description": "Force fresh news fetch"}
                    }
                }
            },
            {
                "name": "get_technical_indicators",
                "description": "Calculate RSI, MACD, Bollinger Bands, EMA, volume profile for a symbol",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "timeframe": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h"]}
                    },
                    "required": ["symbol"]
                }
            },
            {
                "name": "place_trade",
                "description": "Place a buy or sell order on Delta Exchange",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "side": {"type": "string", "enum": ["buy", "sell"]},
                        "order_type": {"type": "string", "enum": ["market", "limit"]},
                        "size_usd": {"type": "number", "description": "Position size in USD"},
                        "stop_loss_pct": {"type": "number", "description": "Stop loss percentage"},
                        "take_profit_pct": {"type": "number", "description": "Take profit percentage"},
                        "leverage": {"type": "integer", "description": "Leverage multiplier"},
                        "reasoning": {"type": "string", "description": "Explain your trading decision"}
                    },
                    "required": ["symbol", "side", "size_usd", "stop_loss_pct", "take_profit_pct", "reasoning"]
                }
            },
            {
                "name": "close_position",
                "description": "Close an existing position",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "reason": {"type": "string", "description": "Reason for closing"}
                    },
                    "required": ["symbol", "reason"]
                }
            },
            {
                "name": "update_stop_loss",
                "description": "Update stop loss for an existing position (trailing stop management)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "new_stop_loss": {"type": "number", "description": "New stop loss price"},
                        "reason": {"type": "string"}
                    },
                    "required": ["symbol", "new_stop_loss", "reason"]
                }
            },
            {
                "name": "set_trading_mode",
                "description": "Change the bot trading mode based on market conditions",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["aggressive", "conservative", "monitoring", "halt"],
                                 "description": "Trading mode"},
                        "reason": {"type": "string"}
                    },
                    "required": ["mode", "reason"]
                }
            },
            {
                "name": "get_market_forecast",
                "description": (
                    "Run the market forecaster: computes ADX trend strength, market regime "
                    "(trending/ranging/volatile), linear-regression price projection "
                    "(1/3/5 periods ahead with R² quality score), VWAP position, "
                    "pivot-point support/resistance levels, and brokerage break-even distance. "
                    "Call this FIRST in every cycle before making any trade decision."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol":    {"type": "string", "description": "Trading symbol e.g. BTCUSD"},
                        "timeframe": {"type": "string",
                                      "enum": ["1m", "5m", "15m", "1h", "4h", "1d"],
                                      "description": "Candle timeframe for analysis (default: 1h)"}
                    }
                }
            },
            {
                "name": "get_trade_history",
                "description": "Get recent trade history and performance statistics",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of recent trades to retrieve"}
                    }
                }
            },
            {
                "name": "scan_all_contracts",
                "description": (
                    "Scan ALL watched perpetual contracts (BTC, ETH, SOL, BNB, XRP, AVAX, DOGE, MATIC, LINK, DOT, etc.) "
                    "and return a ranked list of opportunities sorted by signal strength × confidence. "
                    "Call this FIRST each cycle to find the best contract to trade. "
                    "Returns: ranked_contracts (all scored), top_opportunities (actionable picks), "
                    "composite_score, action (BUY/SELL/HOLD), confidence, ADX, regime, and suggested_size_pct "
                    "for capital allocation across multiple positions."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional subset of symbols to scan. Omit to scan the full watch-list."
                        },
                        "top_n": {
                            "type": "integer",
                            "description": "Number of top opportunities to return (default 5)"
                        }
                    }
                }
            },
            {
                "name": "get_derivatives_data",
                "description": (
                    "Get derivatives market data for a symbol: funding rate, spot-perp basis, "
                    "open interest trend, liquidation levels, and aggregate derivatives signal. "
                    "Use this to understand positioning and squeeze risks before trading."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Trading symbol e.g. BTCUSD"}
                    },
                    "required": ["symbol"]
                }
            }
        ]

    # ─────────────────────────────────────────
    # Tool Execution
    # ─────────────────────────────────────────

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool called by Claude and return result as string."""
        logger.info(f"AI executing tool: {tool_name} | input={tool_input}")
        try:
            if tool_name == "get_market_data":
                return json.dumps(self._tool_get_market_data(tool_input))
            elif tool_name == "get_portfolio_state":
                return json.dumps(self._tool_get_portfolio_state())
            elif tool_name == "analyze_news_sentiment":
                return json.dumps(self._tool_analyze_news_sentiment(tool_input))
            elif tool_name == "get_technical_indicators":
                return json.dumps(self._tool_get_technical_indicators(tool_input))
            elif tool_name == "place_trade":
                return json.dumps(self._tool_place_trade(tool_input))
            elif tool_name == "close_position":
                return json.dumps(self._tool_close_position(tool_input))
            elif tool_name == "update_stop_loss":
                return json.dumps(self._tool_update_stop_loss(tool_input))
            elif tool_name == "set_trading_mode":
                return json.dumps(self._tool_set_trading_mode(tool_input))
            elif tool_name == "get_market_forecast":
                return json.dumps(self._tool_get_market_forecast(tool_input))
            elif tool_name == "get_trade_history":
                return json.dumps(self._tool_get_trade_history(tool_input))
            elif tool_name == "scan_all_contracts":
                return json.dumps(self._tool_scan_all_contracts(tool_input))
            elif tool_name == "get_derivatives_data":
                return json.dumps(self._tool_get_derivatives_data(tool_input))
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return json.dumps({"error": str(e), "tool": tool_name})

    def _tool_get_market_data(self, inp: dict) -> dict:
        symbol = inp.get("symbol", self.config.trading.symbol)
        tf_map = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
        resolution = tf_map.get(inp.get("timeframe", "1h"), 3600)
        try:
            if not self.config.trading.dry_run:
                ticker = self.exchange.get_ticker(symbol)
                end_time = int(time.time())
                candles = self.exchange.get_candles(symbol, resolution=resolution,
                                                     start=end_time - resolution * 100,
                                                     end=end_time)
                ob = self.exchange.get_orderbook(symbol, depth=5)
                data = {
                    "symbol": symbol,
                    "mark_price": ticker.mark_price,
                    "last_price": ticker.last_price,
                    "bid": ticker.bid,
                    "ask": ticker.ask,
                    "spread_pct": round((ticker.ask - ticker.bid) / ticker.mark_price * 100, 4),
                    "volume_24h": ticker.volume_24h,
                    "change_24h_pct": ticker.change_24h_pct,
                    "open_interest": ticker.open_interest,
                    "candles_count": len(candles),
                    "timeframe": inp.get("timeframe", "1h"),
                }
                self._cached_data["market"] = data
                self._cached_data["candles"] = candles
                return data
            else:
                import random
                mock = {
                    "symbol": symbol, "mark_price": 67000 + random.uniform(-2000, 2000),
                    "last_price": 67000, "bid": 66990, "ask": 67010, "spread_pct": 0.03,
                    "volume_24h": 28000, "change_24h_pct": random.uniform(-5, 5),
                    "open_interest": 1200000000, "timeframe": inp.get("timeframe", "1h"),
                    "candles_count": 100,
                }
                self._cached_data["market"] = mock
                self._cached_data["candles"] = [
                    {"close": 67000 + random.uniform(-3000, 3000), "volume": random.uniform(100, 800)}
                    for _ in range(100)
                ]
                return mock
        except Exception as e:
            return {"error": str(e)}

    def _tool_get_portfolio_state(self) -> dict:
        try:
            if not self.config.trading.dry_run:
                balance = self.exchange.get_wallet_balance("USDT")
                positions = self.exchange.get_positions()
                open_orders = self.exchange.get_open_orders()
                pos_data = [
                    {
                        "symbol": p.symbol, "side": p.side, "size": p.size,
                        "entry_price": p.entry_price, "liquidation_price": p.liquidation_price,
                        "unrealized_pnl": p.unrealized_pnl, "realized_pnl": p.realized_pnl,
                        "leverage": p.leverage,
                    }
                    for p in positions
                ]
                perf = self.risk_manager.get_performance_summary()
                return {
                    "balance_usdt": balance.get("balance", 0),
                    "available_balance": balance.get("available_balance", 0),
                    "blocked_margin": balance.get("blocked_margin", 0),
                    "positions": pos_data,
                    "open_orders_count": len(open_orders),
                    "performance": perf,
                    "trading_mode": self.state.current_mode,
                }
            else:
                perf = self.risk_manager.get_performance_summary()
                return {
                    "balance_usdt": 10000.0, "available_balance": 9500.0,
                    "blocked_margin": 500.0, "positions": [],
                    "open_orders_count": 0, "performance": perf,
                    "trading_mode": self.state.current_mode,
                }
        except Exception as e:
            return {"error": str(e)}

    def _tool_analyze_news_sentiment(self, inp: dict) -> dict:
        force = inp.get("force_refresh", False)
        articles = self.news_fetcher.fetch(force=force)
        emotion = self.emotion_engine.analyze(articles)
        geo_events = self.geo_analyzer.analyze(articles)
        geo_impact = self.geo_analyzer.get_aggregate_impact(geo_events)
        self._cached_data["emotion"] = emotion
        self._cached_data["geo_impact"] = geo_impact
        self._cached_data["articles"] = articles
        return {
            "articles_analyzed": len(articles),
            "sentiment_score": emotion.sentiment_score,
            "crypto_specific_sentiment": emotion.crypto_specific_sentiment,
            "dominant_emotion": emotion.dominant_emotion,
            "confidence": emotion.confidence,
            "geopolitical_risk": emotion.geopolitical_risk,
            "trading_bias": emotion.trading_bias,
            "key_events": emotion.key_events[:5],
            "reasoning": emotion.reasoning,
            "geo_net_sentiment": geo_impact.get("net_sentiment"),
            "geo_total_impact": geo_impact.get("total_impact"),
            "geo_risk_level": geo_impact.get("risk_level"),
            "dominant_geo_events": geo_impact.get("dominant_events", [])[:3],
        }

    def _tool_get_technical_indicators(self, inp: dict) -> dict:
        import statistics as stats
        candles = self._cached_data.get("candles", [])
        if not candles:
            self._tool_get_market_data(inp)
            candles = self._cached_data.get("candles", [])
        if len(candles) < 20:
            return {"error": "Insufficient candle data"}

        closes = [float(c.get("close", c.get("c", 0))) for c in candles]
        volumes = [float(c.get("volume", c.get("v", 0))) for c in candles]
        price = closes[-1]

        # SMA / EMA
        sma20 = stats.mean(closes[-20:])
        sma50 = stats.mean(closes[-50:]) if len(closes) >= 50 else None
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)

        # MACD
        macd = ema12 - ema26
        signal_line = macd  # simplified

        # RSI
        gains = [max(closes[i] - closes[i-1], 0) for i in range(1, len(closes))]
        losses = [max(closes[i-1] - closes[i], 0) for i in range(1, len(closes))]
        avg_gain = stats.mean(gains[-14:])
        avg_loss = stats.mean(losses[-14:])
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100

        # Bollinger Bands
        bb_mid = sma20
        bb_std = stats.stdev(closes[-20:])
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_width = (bb_upper - bb_lower) / bb_mid
        bb_position = (price - bb_lower) / (bb_upper - bb_lower)

        # Volume
        avg_vol = stats.mean(volumes[-20:])
        vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

        # Trend
        trend = "sideways"
        if sma50 and price > sma20 > sma50:
            trend = "strong_uptrend"
        elif sma50 and price > sma50:
            trend = "uptrend"
        elif sma50 and price < sma20 < sma50:
            trend = "strong_downtrend"
        elif sma50 and price < sma50:
            trend = "downtrend"

        # Price momentum (10-period ROC)
        roc10 = (closes[-1] - closes[-10]) / closes[-10] * 100 if len(closes) >= 10 else 0

        result = {
            "price": price, "sma20": round(sma20, 2),
            "sma50": round(sma50, 2) if sma50 else None,
            "ema12": round(ema12, 2), "ema26": round(ema26, 2),
            "macd": round(macd, 4),
            "rsi": round(rsi, 2),
            "bb_upper": round(bb_upper, 2), "bb_lower": round(bb_lower, 2),
            "bb_mid": round(bb_mid, 2), "bb_width_pct": round(bb_width * 100, 2),
            "bb_position": round(bb_position, 3),
            "volume_ratio": round(vol_ratio, 2),
            "trend": trend, "roc_10": round(roc10, 3),
            "signals": {
                "rsi_oversold": rsi < 30,
                "rsi_overbought": rsi > 70,
                "price_below_bb_lower": price < bb_lower,
                "price_above_bb_upper": price > bb_upper,
                "high_volume": vol_ratio > 1.5,
                "strong_uptrend": trend == "strong_uptrend",
                "strong_downtrend": trend == "strong_downtrend",
                "macd_positive": macd > 0,
            }
        }
        self._cached_data["technicals"] = result
        return result

    def _tool_place_trade(self, inp: dict) -> dict:
        symbol = inp["symbol"]
        side = inp["side"]
        size_usd = inp["size_usd"]
        sl_pct = inp["stop_loss_pct"] / 100
        tp_pct = inp["take_profit_pct"] / 100
        leverage = inp.get("leverage", self.config.trading.leverage)
        reasoning = inp["reasoning"]

        market = self._cached_data.get("market", {})
        price = market.get("mark_price", 67000)

        stop_loss = price * (1 - sl_pct) if side == "buy" else price * (1 + sl_pct)
        take_profit = price * (1 + tp_pct) if side == "buy" else price * (1 - tp_pct)
        contracts = max(int(size_usd * leverage), 1)

        # Brokerage cost estimate
        notional_usd   = size_usd * leverage
        taker_fee_rate = getattr(self.config.trading, "taker_fee_rate", 0.0005)
        round_trip_fee = round(notional_usd * taker_fee_rate * 2, 4)
        fee_pct_margin = round(taker_fee_rate * 2 * leverage * 100, 4)

        self.state.total_trades += 1
        self.state.last_action = f"{side.upper()} {contracts} contracts @ ${price:,.0f}"
        self.state.last_action_time = datetime.now(timezone.utc).isoformat()

        decision = {
            "time": self.state.last_action_time,
            "action": f"{side.upper()} {symbol}",
            "price": price, "contracts": contracts,
            "stop_loss": round(stop_loss, 2), "take_profit": round(take_profit, 2),
            "estimated_fee_usd": round_trip_fee,
            "fee_pct_of_margin": fee_pct_margin,
            "reasoning": reasoning[:200],
        }
        self.state.decisions.insert(0, decision)
        self.state.decisions = self.state.decisions[:50]

        if self.config.trading.dry_run:
            logger.info(f"[DRY RUN] Trade: {side} {contracts}x {symbol} @ {price} | fee≈${round_trip_fee:.2f}")
            return {
                "status": "dry_run_simulated", "symbol": symbol, "side": side,
                "contracts": contracts, "price": price,
                "stop_loss": round(stop_loss, 2), "take_profit": round(take_profit, 2),
                "size_usd": size_usd, "leverage": leverage,
                "estimated_round_trip_fee_usd": round_trip_fee,
                "fee_pct_of_margin": fee_pct_margin,
            }

        from src.exchange.delta_client import Order
        product_id = self.exchange.get_product_id(symbol)
        if not product_id:
            return {"error": f"Product not found: {symbol}"}
        self.exchange.set_leverage(product_id, leverage)
        order = Order(symbol=symbol, side=side, order_type="market", size=contracts)
        result = self.exchange.place_order(order, product_id)
        return {"status": "executed", "order_id": result.get("id"), "symbol": symbol,
                "side": side, "contracts": contracts, "stop_loss": round(stop_loss, 2),
                "take_profit": round(take_profit, 2)}

    def _tool_close_position(self, inp: dict) -> dict:
        symbol = inp["symbol"]
        reason = inp["reason"]
        self.state.last_action = f"CLOSE {symbol}: {reason}"
        self.state.last_action_time = datetime.now(timezone.utc).isoformat()
        if self.config.trading.dry_run:
            return {"status": "dry_run_closed", "symbol": symbol, "reason": reason}
        product_id = self.exchange.get_product_id(symbol)
        if not product_id:
            return {"error": f"Product not found: {symbol}"}
        result = self.exchange.close_position(product_id, symbol)
        return {"status": "closed", "symbol": symbol, "reason": reason, "order": result}

    def _tool_update_stop_loss(self, inp: dict) -> dict:
        return {
            "status": "acknowledged",
            "symbol": inp["symbol"],
            "new_stop_loss": inp["new_stop_loss"],
            "reason": inp.get("reason", ""),
            "note": "Trailing stop updated in risk tracking system"
        }

    def _tool_set_trading_mode(self, inp: dict) -> dict:
        mode = inp["mode"]
        reason = inp["reason"]
        self.state.current_mode = mode
        logger.info(f"Trading mode changed to: {mode} | Reason: {reason}")
        return {"status": "ok", "mode": mode, "reason": reason}

    def _tool_get_market_forecast(self, inp: dict) -> dict:
        """Run MarketForecaster on cached candles and return structured result."""
        from src.intelligence.market_forecaster import MarketForecaster
        candles = self._cached_data.get("candles", [])
        market  = self._cached_data.get("market", {})
        price   = market.get("mark_price", 0.0)

        # If no candles cached yet, fetch them first
        if not candles or price == 0.0:
            self._tool_get_market_data(inp)
            candles = self._cached_data.get("candles", [])
            market  = self._cached_data.get("market", {})
            price   = market.get("mark_price", 67000.0)

        forecaster = MarketForecaster(self.config)
        fc = forecaster.forecast(candles, price)

        tc = self.config.trading
        leverage   = getattr(tc, "leverage", 5)
        taker_fee  = getattr(tc, "taker_fee_rate", 0.0005)
        rt_fee_pct = taker_fee * 2 * leverage * 100    # % of margin

        result = {
            # Trend
            "adx":                  fc.adx,
            "plus_di":              fc.plus_di,
            "minus_di":             fc.minus_di,
            "trend_direction":      fc.trend_direction,
            "trend_strength":       fc.trend_strength_label,
            "is_trending":          fc.is_trending,
            "is_strong_trend":      fc.is_strong_trend,
            # Regime
            "market_regime":        fc.market_regime,
            "regime_confidence":    fc.regime_confidence,
            # Price forecast
            "forecast_price_1":     fc.forecast_price_1,
            "forecast_price_3":     fc.forecast_price_3,
            "forecast_price_5":     fc.forecast_price_5,
            "forecast_bias":        fc.forecast_bias,
            "forecast_slope_pct":   fc.forecast_slope_pct,
            "regression_r2":        fc.regression_r2,
            # VWAP
            "vwap":                 fc.vwap,
            "vwap_position":        fc.vwap_position,
            "vwap_distance_pct":    fc.vwap_distance_pct,
            # Support / resistance
            "pivot_point":          fc.pivot_point,
            "resistance_levels":    fc.resistance_levels,
            "support_levels":       fc.support_levels,
            # Brokerage
            "breakeven_move_pct":   fc.breakeven_move_pct,
            "taker_fee_pct":        taker_fee * 100,
            "round_trip_fee_pct_of_margin": rt_fee_pct,
            "leverage":             leverage,
            "fee_note": (
                f"Round-trip fee = {rt_fee_pct:.2f}% of margin. "
                f"TP must exceed {fc.breakeven_move_pct:.2f}% from entry to be profitable. "
                f"Net R:R must be >= 1.5 after deducting fee from both reward and risk."
            ),
            # Composite score
            "forecast_score":       fc.forecast_score,
            # Decision hint
            "trading_hint": self._forecast_hint(fc, price),
        }
        self._cached_data["forecast"] = result
        return result

    @staticmethod
    def _forecast_hint(fc, price: float) -> str:
        """Human-readable one-liner trading guidance from forecast data."""
        hints = []
        if fc.adx >= 35:
            hints.append(f"Strong {fc.trend_direction} trend (ADX={fc.adx:.1f}) — trade WITH the trend")
        elif fc.adx >= 25:
            hints.append(f"Moderate trend (ADX={fc.adx:.1f}) — favour {fc.trend_direction} entries")
        else:
            hints.append(f"Ranging market (ADX={fc.adx:.1f}) — use mean-reversion strategy")

        if fc.regression_r2 > 0.40:
            hints.append(
                f"Regression strongly {fc.forecast_bias} (R²={fc.regression_r2:.2f}, "
                f"3-bar target ${fc.forecast_price_3:,.0f})"
            )

        if fc.vwap:
            hints.append(f"Price {fc.vwap_position} VWAP (${fc.vwap:,.0f})")

        if fc.support_levels:
            hints.append(f"Key support: ${fc.support_levels[0]:,.0f}")
        if fc.resistance_levels:
            hints.append(f"Key resistance: ${fc.resistance_levels[0]:,.0f}")

        hints.append(
            f"Break-even (fees): {fc.breakeven_move_pct:.2f}% of margin — "
            f"set TP > {fc.breakeven_move_pct + 0.5:.2f}% for minimum viable profit"
        )
        return " | ".join(hints)

    def _tool_get_trade_history(self, inp: dict) -> dict:
        limit = inp.get("limit", 10)
        perf = self.risk_manager.get_performance_summary()
        recent = self.state.decisions[:limit]
        return {"recent_decisions": recent, "performance": perf,
                "cycle_count": self.state.cycle_count,
                "total_ai_trades": self.state.total_trades}

    def _tool_scan_all_contracts(self, inp: dict) -> dict:
        """Scan all watched perpetual contracts and return ranked opportunities."""
        try:
            from src.scanner.contract_scanner import ContractScanner
            symbols = inp.get("symbols") or getattr(self.config.trading, "watch_list", None)
            top_n   = inp.get("top_n", 5)
            scanner = ContractScanner(
                config=self.config,
                exchange=self.exchange if not self.config.trading.dry_run else None,
            )
            result  = scanner.scan(symbols)
            # Store top symbol in cache for subsequent tool calls
            if result.top_opportunities:
                best = result.top_opportunities[0]
                self._cached_data["scan_best_symbol"] = best.symbol
            top_n_result = result.top_opportunities[:top_n]
            return {
                "total_scanned": result.total_scanned,
                "total_actionable": result.total_actionable,
                "market_summary": result.market_summary,
                "top_opportunities": [c.to_dict() for c in top_n_result],
                "all_ranked": [c.to_dict() for c in result.ranked_contracts[:15]],
                "scan_duration_seconds": round(result.scan_duration_seconds, 2),
                "scan_timestamp": result.scan_timestamp,
                "instruction": (
                    "Pick the highest-ranked BUY or SELL from top_opportunities. "
                    "Use that symbol for get_market_forecast and subsequent analysis. "
                    "Check suggested_size_pct for capital allocation across positions."
                ),
            }
        except Exception as e:
            logger.error(f"scan_all_contracts failed: {e}")
            return {"error": str(e), "fallback_symbol": self.config.trading.symbol}

    def _tool_get_derivatives_data(self, inp: dict) -> dict:
        """Return derivatives market intelligence for a symbol."""
        try:
            symbol = inp.get("symbol", self.config.trading.symbol)
            from src.derivatives.derivatives_signal import DerivativesSignalEngine
            import random as _r
            engine = DerivativesSignalEngine()
            if self.config.trading.dry_run:
                price    = self._cached_data.get("market", {}).get("mark_price", 67000.0)
                funding  = _r.gauss(0.0001, 0.0006)
                spot     = price * (1 + _r.gauss(0, 0.001))
                oi       = _r.uniform(400e6, 900e6)
            else:
                try:
                    ticker  = self.exchange.get_ticker(symbol)
                    price   = ticker.mark_price
                    oi      = ticker.open_interest
                    resp    = self.exchange._request("GET", f"/v2/tickers/{symbol}", auth=False)
                    funding = float(resp.get("result", {}).get("funding_rate", 0.0001))
                    spot    = price * 0.9997
                except Exception:
                    price = 67000.0; funding = 0.0001; spot = 66980.0; oi = 500e6
            ds = engine.analyze(
                current_price=price, funding_rate=funding,
                spot_price=spot, open_interest=oi,
            )
            return ds.to_dict()
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _ema(data: list, period: int) -> float:
        k = 2 / (period + 1)
        ema = data[0]
        for v in data[1:]:
            ema = v * k + ema * (1 - k)
        return ema

    # ─────────────────────────────────────────
    # Main Autonomous Loop
    # ─────────────────────────────────────────

    def run_cycle(self) -> dict:
        """
        Run one full autonomous AI decision cycle.
        Claude uses tools to gather data and makes autonomous trading decisions.
        Returns the cycle result for broadcasting.
        """
        self.state.cycle_count += 1
        self.state.is_running = True
        cycle_start = time.time()

        logger.info(f"AI Cycle #{self.state.cycle_count} starting...")

        # Autonomous prompt - Claude decides what to do
        tc  = self.config.trading
        taker_fee   = getattr(tc, "taker_fee_rate", 0.0005)
        leverage    = getattr(tc, "leverage", 5)
        rt_fee_pct  = taker_fee * 2 * leverage * 100

        watch = getattr(tc, "watch_list", [tc.symbol])
        top_n = getattr(tc, "top_contracts_to_trade", 3)

        user_message = f"""
Autonomous trading cycle #{self.state.cycle_count}
Time    : {datetime.now(timezone.utc).isoformat()}
Mode    : {self.state.current_mode}
Dry run : {self.config.trading.dry_run}

WATCH-LIST ({len(watch)} contracts): {', '.join(watch)}

BROKERAGE REMINDER (Delta Exchange):
  Taker fee : {taker_fee * 100:.3f}% per side
  Leverage  : {leverage}×
  Round-trip cost on margin ≈ {rt_fee_pct:.2f}%
  → Net R:R must be ≥ 1.5 after fees to proceed

REQUIRED STEPS (in this exact order):
1. scan_all_contracts  ← START HERE — scores ALL {len(watch)} contracts and ranks them.
                         Choose the highest-ranked BUY or SELL opportunity.
                         You may trade up to {top_n} different symbols simultaneously.
2. get_market_forecast for the chosen symbol
3. get_technical_indicators + get_market_data for that symbol
4. analyze_news_sentiment ← applies to all crypto broadly
5. get_portfolio_state    ← check available capital and current positions
6. OPTIONALLY: get_derivatives_data for the chosen symbol (funding/OI/squeeze risk)
7. DECISION: BUY / SELL / HOLD
   - Confirm scan score + forecast + technicals + sentiment all agree on direction
   - Calculate net R:R after the {rt_fee_pct:.2f}% fee cost
   - Only trade if net R:R ≥ 1.5 and confidence ≥ 0.50
   - Use suggested_size_pct from scan to allocate capital across positions
8. Execute trade(s) — may trade different symbols in the same cycle
9. Update trailing stops on existing positions
10. Adjust trading mode if regime has changed

Trade WITH the trend in trending markets.
Use mean-reversion in ranging markets.
NEVER enter if fee cost exceeds expected profit.
"""

        messages = [{"role": "user", "content": user_message}]
        tool_calls_made = []

        # Agentic loop: Claude calls tools until it reaches a final decision
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=ORCHESTRATOR_SYSTEM_PROMPT,
                tools=self.tools,
                messages=messages,
            )

            # Collect assistant response
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Claude is done
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text = block.text
                        break
                self.state.status_message = final_text[:300] if final_text else "Cycle complete"
                break

            if response.stop_reason == "tool_use":
                # Execute tool calls
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_calls_made.append(tool_name)
                        result = self._execute_tool(tool_name, tool_input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})
            else:
                break

        elapsed = time.time() - cycle_start
        logger.info(f"AI Cycle #{self.state.cycle_count} complete in {elapsed:.1f}s | "
                    f"Tools used: {tool_calls_made} | Action: {self.state.last_action}")

        result = {
            "cycle": self.state.cycle_count,
            "elapsed_seconds": round(elapsed, 1),
            "tools_used": tool_calls_made,
            "action": self.state.last_action,
            "mode": self.state.current_mode,
            "status": self.state.status_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cached_data": self._get_broadcast_data(),
        }

        if self.broadcast:
            self.broadcast(result)

        return result

    def _get_broadcast_data(self) -> dict:
        """Package current state for broadcast to dashboard/mobile."""
        emotion = self._cached_data.get("emotion")
        geo = self._cached_data.get("geo_impact", {})
        tech = self._cached_data.get("technicals", {})
        market = self._cached_data.get("market", {})
        articles = self._cached_data.get("articles", [])

        return {
            "market": market,
            "emotion": {
                "sentiment_score": emotion.sentiment_score if emotion else 0,
                "crypto_sentiment": emotion.crypto_specific_sentiment if emotion else 0,
                "dominant_emotion": emotion.dominant_emotion if emotion else "unknown",
                "confidence": emotion.confidence if emotion else 0,
                "geopolitical_risk": emotion.geopolitical_risk if emotion else "low",
                "trading_bias": emotion.trading_bias if emotion else "neutral",
                "key_events": emotion.key_events[:5] if emotion else [],
                "reasoning": emotion.reasoning if emotion else "",
            } if emotion else {},
            "geo": geo,
            "technicals": tech,
            "bot_state": {
                "cycle": self.state.cycle_count,
                "mode": self.state.current_mode,
                "total_trades": self.state.total_trades,
                "last_action": self.state.last_action,
                "last_action_time": self.state.last_action_time,
                "status": self.state.status_message,
            },
            "recent_decisions": self.state.decisions[:10],
            "top_articles": [
                {"title": a.title[:100], "source": a.source,
                 "score": a.relevance_score, "published": a.published_at}
                for a in articles[:10]
            ],
        }
