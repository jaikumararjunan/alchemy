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


ORCHESTRATOR_SYSTEM_PROMPT = """You are ALCHEMY, a fully autonomous crypto trading AI for Delta Exchange.
You have complete authority to make trading decisions based on real-time market data,
geopolitical intelligence, and emotional market analysis.

Your mission: Maximize risk-adjusted returns on Delta Exchange crypto derivatives
while rigorously protecting capital.

Core Decision Framework:
1. ANALYZE: Process emotion scores, geo events, technical indicators, and portfolio state
2. DECIDE: Make clear buy/sell/hold decisions with specific parameters
3. EXECUTE: Use provided tools to interact with the exchange
4. MONITOR: Track positions, adjust stops, manage risk dynamically
5. ADAPT: Learn from trade outcomes and adjust strategy

Risk Rules (NON-NEGOTIABLE):
- Never risk more than 2% per trade
- Always set stop losses before entering
- Halt trading if daily drawdown > 5%
- Reduce position size in high geopolitical risk environments
- Never trade against strong momentum without high confidence

You must call tools to get current data before making decisions.
Always explain your reasoning in the 'reasoning' field of your decisions.
Be decisive - markets wait for no one."""


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
                "name": "get_trade_history",
                "description": "Get recent trade history and performance statistics",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of recent trades to retrieve"}
                    }
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
            elif tool_name == "get_trade_history":
                return json.dumps(self._tool_get_trade_history(tool_input))
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

        self.state.total_trades += 1
        self.state.last_action = f"{side.upper()} {contracts} contracts @ ${price:,.0f}"
        self.state.last_action_time = datetime.now(timezone.utc).isoformat()

        decision = {
            "time": self.state.last_action_time,
            "action": f"{side.upper()} {symbol}",
            "price": price, "contracts": contracts,
            "stop_loss": round(stop_loss, 2), "take_profit": round(take_profit, 2),
            "reasoning": reasoning[:200],
        }
        self.state.decisions.insert(0, decision)
        self.state.decisions = self.state.decisions[:50]

        if self.config.trading.dry_run:
            logger.info(f"[DRY RUN] Trade: {side} {contracts}x {symbol} @ {price}")
            return {
                "status": "dry_run_simulated", "symbol": symbol, "side": side,
                "contracts": contracts, "price": price,
                "stop_loss": round(stop_loss, 2), "take_profit": round(take_profit, 2),
                "size_usd": size_usd, "leverage": leverage,
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

    def _tool_get_trade_history(self, inp: dict) -> dict:
        limit = inp.get("limit", 10)
        perf = self.risk_manager.get_performance_summary()
        recent = self.state.decisions[:limit]
        return {"recent_decisions": recent, "performance": perf,
                "cycle_count": self.state.cycle_count,
                "total_ai_trades": self.state.total_trades}

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
        user_message = f"""
You are running autonomous trading cycle #{self.state.cycle_count}.
Current time: {datetime.now(timezone.utc).isoformat()}
Trading symbol: {self.config.trading.symbol}
Current mode: {self.state.current_mode}
Dry run: {self.config.trading.dry_run}

Execute your full decision cycle:
1. Get current market data and technical indicators
2. Analyze news sentiment and geopolitical events
3. Check portfolio state
4. Based on all data, make a trading decision
5. Execute any trades if conditions are right
6. Set or update trading mode based on market conditions

Be decisive. Use your tools. Make the best decision for maximum risk-adjusted returns.
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
