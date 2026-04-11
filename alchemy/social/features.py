"""
alchemy.social — Strategy Marketplace, Competitions, Strategy Builder
alchemy.integrations — Telegram Bot, Multi-Account, Options, Rebalance Bot
===========================================================================
Features 2, 3, 4, 6, 16, 17, 20 from the roadmap.
"""
from __future__ import annotations
import json, os, uuid, time, math, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import structlog

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Feature 2: Strategy Builder (No-Code)
# ══════════════════════════════════════════════════════════════════════════════

class StrategyCondition:
    """A single condition in a no-code strategy."""
    def __init__(self, indicator, operator, value, timeframe="1h"):
        self.indicator = indicator  # "rsi", "sma_cross", "price", "volume"
        self.operator = operator    # ">", "<", "crosses_above", "crosses_below"
        self.value = value          # Number or indicator name
        self.timeframe = timeframe

    def to_dict(self):
        return self.__dict__

class StrategyRule:
    """A rule: IF conditions THEN action."""
    def __init__(self, name, conditions, action, params=None):
        self.name = name
        self.conditions = conditions  # list[StrategyCondition]
        self.action = action          # "buy", "sell", "close"
        self.params = params or {}    # position_size_pct, etc.

    def to_dict(self):
        return {
            "name": self.name,
            "conditions": [c.to_dict() for c in self.conditions],
            "action": self.action,
            "params": self.params,
        }

class CustomStrategy:
    """User-built no-code strategy."""
    def __init__(self, **kw):
        self.id = kw.get("id", str(uuid.uuid4())[:8])
        self.user_id = kw.get("user_id", "")
        self.name = kw.get("name", "My Strategy")
        self.description = kw.get("description", "")
        self.symbol = kw.get("symbol", "BTCUSDT")
        self.rules = kw.get("rules", [])       # list[StrategyRule]
        self.active = kw.get("active", False)
        self.backtest_results = kw.get("backtest_results")
        self.created_at = kw.get("created_at", datetime.now(timezone.utc).isoformat())
        self.published = kw.get("published", False)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "symbol": self.symbol, "active": self.active, "published": self.published,
            "rules": [r.to_dict() if isinstance(r, StrategyRule) else r for r in self.rules],
            "backtest_results": self.backtest_results,
            "created_at": self.created_at,
        }

# Strategy storage
_strategies: dict[str, list[CustomStrategy]] = {}

def create_strategy(user_id, name, description, symbol, rules):
    s = CustomStrategy(user_id=user_id, name=name, description=description,
                        symbol=symbol, rules=rules)
    _strategies.setdefault(user_id, []).append(s)
    return s.to_dict()

def get_strategies(user_id):
    return [s.to_dict() for s in _strategies.get(user_id, [])]

def get_available_conditions():
    return {
        "indicators": [
            {"id": "rsi", "name": "RSI", "params": ["period"], "type": "oscillator"},
            {"id": "sma", "name": "Simple Moving Average", "params": ["period"], "type": "overlay"},
            {"id": "ema", "name": "Exponential Moving Average", "params": ["period"], "type": "overlay"},
            {"id": "bb_upper", "name": "Bollinger Upper Band", "params": ["period", "std"], "type": "overlay"},
            {"id": "bb_lower", "name": "Bollinger Lower Band", "params": ["period", "std"], "type": "overlay"},
            {"id": "macd", "name": "MACD Line", "params": ["fast", "slow", "signal"], "type": "oscillator"},
            {"id": "volume", "name": "Volume", "params": ["period"], "type": "volume"},
            {"id": "price", "name": "Price", "params": [], "type": "price"},
            {"id": "atr", "name": "ATR (Volatility)", "params": ["period"], "type": "volatility"},
        ],
        "operators": [">", "<", ">=", "<=", "==", "crosses_above", "crosses_below"],
        "actions": ["buy", "sell", "close_long", "close_short"],
        "example": {
            "name": "RSI Bounce",
            "rules": [
                {"conditions": [{"indicator": "rsi", "operator": "<", "value": 30}], "action": "buy"},
                {"conditions": [{"indicator": "rsi", "operator": ">", "value": 70}], "action": "sell"},
            ]
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# Feature 16: Strategy Marketplace
# ══════════════════════════════════════════════════════════════════════════════

_marketplace: list[dict] = []

def publish_strategy(user_id, strategy_id, price_usd=0):
    for s in _strategies.get(user_id, []):
        if s.id == strategy_id:
            s.published = True
            listing = {
                "id": str(uuid.uuid4())[:8],
                "strategy_id": strategy_id,
                "author_id": user_id[:6] + "***",
                "name": s.name,
                "description": s.description,
                "symbol": s.symbol,
                "backtest_return": s.backtest_results.get("total_return_pct", 0) if s.backtest_results else None,
                "price_usd": price_usd,
                "subscribers": 0,
                "rating": 0,
                "published_at": datetime.now(timezone.utc).isoformat(),
            }
            _marketplace.append(listing)
            return listing
    return None

def browse_marketplace(sort_by="rating"):
    return sorted(_marketplace, key=lambda x: -x.get(sort_by, 0))

def subscribe_strategy(user_id, listing_id):
    for m in _marketplace:
        if m["id"] == listing_id:
            m["subscribers"] += 1
            return {"ok": True, "strategy": m["name"], "message": "Subscribed!"}
    return {"ok": False, "message": "Strategy not found"}


# ══════════════════════════════════════════════════════════════════════════════
# Feature 17: Paper Trading Competitions
# ══════════════════════════════════════════════════════════════════════════════

class Competition:
    def __init__(self, **kw):
        self.id = kw.get("id", str(uuid.uuid4())[:8])
        self.name = kw.get("name", "Weekly Challenge")
        self.description = kw.get("description", "")
        self.start_date = kw.get("start_date", datetime.now(timezone.utc).isoformat())
        self.end_date = kw.get("end_date", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
        self.initial_balance = kw.get("initial_balance", 100000)
        self.allowed_symbols = kw.get("allowed_symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        self.max_leverage = kw.get("max_leverage", 5)
        self.participants: dict[str, dict] = kw.get("participants", {})
        self.status = kw.get("status", "active")  # active, ended, upcoming
        self.prizes = kw.get("prizes", ["1st: Badge + Featured", "2nd: Badge", "3rd: Badge"])

    @property
    def leaderboard(self):
        board = []
        for uid, data in self.participants.items():
            board.append({
                "user_id": uid[:6] + "***",
                "portfolio_value": data.get("portfolio_value", self.initial_balance),
                "return_pct": round(
                    (data.get("portfolio_value", self.initial_balance) - self.initial_balance)
                    / self.initial_balance * 100, 2),
                "trades": data.get("trade_count", 0),
                "joined_at": data.get("joined_at"),
            })
        return sorted(board, key=lambda x: -x["return_pct"])

    def join(self, user_id):
        if user_id in self.participants:
            return {"ok": False, "message": "Already joined"}
        self.participants[user_id] = {
            "portfolio_value": self.initial_balance,
            "trade_count": 0,
            "joined_at": datetime.now(timezone.utc).isoformat(),
        }
        return {"ok": True, "message": f"Joined '{self.name}'!"}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "start_date": self.start_date, "end_date": self.end_date,
            "initial_balance": self.initial_balance,
            "allowed_symbols": self.allowed_symbols,
            "max_leverage": self.max_leverage,
            "participant_count": len(self.participants),
            "status": self.status, "prizes": self.prizes,
            "leaderboard": self.leaderboard[:10],
        }


_competitions: list[Competition] = [
    Competition(
        name="Weekly Crypto Challenge",
        description="Trade BTC, ETH, and SOL for 7 days. Highest return wins!",
        initial_balance=100000,
    ),
]

def get_competitions():
    return [c.to_dict() for c in _competitions]

def join_competition(comp_id, user_id):
    for c in _competitions:
        if c.id == comp_id:
            return c.join(user_id)
    return {"ok": False, "message": "Competition not found"}

def create_competition(**kw):
    c = Competition(**kw)
    _competitions.append(c)
    return c.to_dict()


# ══════════════════════════════════════════════════════════════════════════════
# Feature 3: Telegram Bot Integration
# ══════════════════════════════════════════════════════════════════════════════

class TelegramBot:
    """
    Telegram bot for trading commands.

    Commands:
      /portfolio — Show portfolio summary
      /buy 0.1 btc — Place paper buy order
      /sell 0.1 eth — Place paper sell order
      /price btc — Get current price
      /killswitch — Emergency stop
      /alerts — View active alerts
      /help — Show commands
    """

    def __init__(self, token: str = ""):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_ids: dict[str, str] = {}  # user_id → chat_id
        self.enabled = bool(self.token)

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML"):
        if not self.enabled: return {"ok": False, "error": "Bot not configured"}
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
                )
                return resp.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def send_trade_alert(self, user_id: str, trade: dict):
        chat_id = self.chat_ids.get(user_id)
        if not chat_id: return
        emoji = "🟢" if trade.get("side") == "BUY" else "🔴"
        text = (
            f"{emoji} <b>{trade.get('side', '')} {trade.get('symbol', '')}</b>\n"
            f"Price: ${trade.get('price', 0):,.2f}\n"
            f"Qty: {trade.get('quantity', 0)}\n"
            f"Mode: {trade.get('mode', 'paper')}\n"
            f"Strategy: {trade.get('strategy', 'manual')}"
        )
        await self.send_message(chat_id, text)

    def register_chat(self, user_id: str, chat_id: str):
        self.chat_ids[user_id] = chat_id
        return {"ok": True, "message": f"Telegram linked to user {user_id[:6]}***"}

    def parse_command(self, text: str) -> dict:
        """Parse a Telegram command."""
        parts = text.strip().split()
        cmd = parts[0].lower().lstrip("/")

        if cmd == "portfolio":
            return {"action": "portfolio"}
        elif cmd in ("buy", "sell") and len(parts) >= 3:
            qty = float(parts[1])
            symbol = parts[2].upper() + "USDT" if "USDT" not in parts[2].upper() else parts[2].upper()
            return {"action": "trade", "side": cmd.upper(), "quantity": qty, "symbol": symbol}
        elif cmd == "price" and len(parts) >= 2:
            symbol = parts[1].upper() + "USDT" if "USDT" not in parts[1].upper() else parts[1].upper()
            return {"action": "price", "symbol": symbol}
        elif cmd == "killswitch":
            return {"action": "killswitch"}
        elif cmd == "alerts":
            return {"action": "alerts"}
        elif cmd == "help":
            return {"action": "help"}
        return {"action": "unknown", "text": text}

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "linked_users": len(self.chat_ids),
            "commands": ["/portfolio", "/buy", "/sell", "/price", "/killswitch", "/alerts", "/help"],
        }


_telegram_bot = None
def get_telegram_bot():
    global _telegram_bot
    if not _telegram_bot: _telegram_bot = TelegramBot()
    return _telegram_bot


# ══════════════════════════════════════════════════════════════════════════════
# Feature 4: Multi-Account Management
# ══════════════════════════════════════════════════════════════════════════════

class ExchangeAccount:
    def __init__(self, **kw):
        self.id = kw.get("id", str(uuid.uuid4())[:8])
        self.user_id = kw.get("user_id", "")
        self.exchange = kw.get("exchange", "binance")
        self.label = kw.get("label", "Main Account")
        self.api_key_preview = kw.get("api_key_preview", "")
        self.mode = kw.get("mode", "paper")    # paper, live
        self.balance = kw.get("balance", 0)
        self.pnl = kw.get("pnl", 0)
        self.trade_count = kw.get("trade_count", 0)
        self.active = kw.get("active", True)
        self.created_at = kw.get("created_at", datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return self.__dict__


_accounts: dict[str, list[ExchangeAccount]] = {}

def add_account(user_id, exchange, label, api_key_preview="", mode="paper"):
    acc = ExchangeAccount(user_id=user_id, exchange=exchange, label=label,
                           api_key_preview=api_key_preview, mode=mode)
    _accounts.setdefault(user_id, []).append(acc)
    return acc.to_dict()

def get_accounts(user_id):
    return [a.to_dict() for a in _accounts.get(user_id, [])]

def get_aggregate_portfolio(user_id):
    accounts = _accounts.get(user_id, [])
    return {
        "total_balance": sum(a.balance for a in accounts),
        "total_pnl": sum(a.pnl for a in accounts),
        "account_count": len(accounts),
        "accounts": [a.to_dict() for a in accounts],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Feature 6: Options Chain (Simplified)
# ══════════════════════════════════════════════════════════════════════════════

def calculate_greeks(spot, strike, dte_days, volatility=0.5, rate=0.05, option_type="call"):
    """Calculate option Greeks using simplified Black-Scholes."""
    from math import log, sqrt, exp
    try:
        T = max(dte_days / 365, 0.001)
        d1 = (log(spot/strike) + (rate + volatility**2/2)*T) / (volatility*sqrt(T))
        d2 = d1 - volatility*sqrt(T)

        # Approximate normal CDF
        def ncdf(x):
            t = 1/(1+0.2316419*abs(x))
            d = 0.3989422804 * exp(-x*x/2)
            p = d*t*(0.3193815 + t*(-0.3565638 + t*(1.781478 + t*(-1.821256 + t*1.330274))))
            return 1-p if x > 0 else p

        nd1 = ncdf(d1)
        nd2 = ncdf(d2)
        npd1 = 0.3989422804 * exp(-d1*d1/2)

        if option_type == "call":
            delta = nd1
            price = spot * nd1 - strike * exp(-rate*T) * nd2
        else:
            delta = nd1 - 1
            price = strike * exp(-rate*T) * ncdf(-d2) - spot * ncdf(-d1)

        gamma = npd1 / (spot * volatility * sqrt(T))
        theta = -(spot * npd1 * volatility) / (2*sqrt(T)) / 365
        vega = spot * npd1 * sqrt(T) / 100

        return {
            "price": round(price, 2),
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "theta": round(theta, 4),
            "vega": round(vega, 4),
            "iv": round(volatility * 100, 1),
        }
    except:
        return {"price": 0, "delta": 0, "gamma": 0, "theta": 0, "vega": 0, "iv": 0}


def generate_options_chain(spot_price, strikes=None, dte_days=30, volatility=0.5):
    """Generate options chain with Greeks for multiple strikes."""
    if not strikes:
        step = spot_price * 0.02  # 2% steps
        strikes = [round(spot_price + step * i, 0) for i in range(-5, 6)]

    chain = []
    for strike in strikes:
        call = calculate_greeks(spot_price, strike, dte_days, volatility, option_type="call")
        put = calculate_greeks(spot_price, strike, dte_days, volatility, option_type="put")
        moneyness = "ITM" if (spot_price > strike) else "OTM" if (spot_price < strike) else "ATM"
        chain.append({
            "strike": strike,
            "moneyness": moneyness,
            "call": call,
            "put": put,
        })

    return {
        "spot_price": spot_price,
        "dte_days": dte_days,
        "implied_volatility": round(volatility * 100, 1),
        "chain": chain,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Feature 20: Portfolio Rebalancing Bot
# ══════════════════════════════════════════════════════════════════════════════

class RebalanceBot:
    """
    Automated portfolio rebalancer.

    Monitors target allocations and rebalances when drift exceeds threshold.
    Supports: daily, weekly, monthly frequency + threshold-based triggers.
    """
    def __init__(self):
        self._configs: dict[str, dict] = {}  # user_id → config

    def configure(self, user_id, target_allocations, threshold_pct=5,
                  frequency="weekly", tax_loss_harvest=False):
        """
        Configure rebalancing.

        target_allocations: {symbol: pct} e.g., {"BTCUSDT": 40, "ETHUSDT": 30, "SOLUSDT": 20, "CASH": 10}
        """
        total = sum(target_allocations.values())
        if abs(total - 100) > 0.1:
            raise ValueError(f"Allocations must sum to 100%, got {total}%")

        self._configs[user_id] = {
            "targets": target_allocations,
            "threshold_pct": threshold_pct,
            "frequency": frequency,
            "tax_loss_harvest": tax_loss_harvest,
            "last_rebalance": None,
            "rebalance_count": 0,
            "configured_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._configs[user_id]

    def check_drift(self, user_id, current_values: dict) -> dict:
        """
        Check portfolio drift from target allocations.

        current_values: {symbol: current_usd_value}
        """
        config = self._configs.get(user_id)
        if not config:
            return {"needs_rebalance": False, "message": "Not configured"}

        total = sum(current_values.values())
        if total == 0:
            return {"needs_rebalance": False, "message": "Empty portfolio"}

        drifts = []
        trades_needed = []
        for symbol, target_pct in config["targets"].items():
            current = current_values.get(symbol, 0)
            current_pct = (current / total) * 100
            drift = current_pct - target_pct

            if abs(drift) > config["threshold_pct"]:
                target_value = total * target_pct / 100
                adjustment = target_value - current
                trades_needed.append({
                    "symbol": symbol,
                    "action": "buy" if adjustment > 0 else "sell",
                    "amount_usd": round(abs(adjustment), 2),
                    "current_pct": round(current_pct, 1),
                    "target_pct": target_pct,
                    "drift_pct": round(drift, 1),
                })

            drifts.append({
                "symbol": symbol, "target_pct": target_pct,
                "current_pct": round(current_pct, 1),
                "drift_pct": round(drift, 1),
            })

        return {
            "needs_rebalance": len(trades_needed) > 0,
            "total_value": round(total, 2),
            "drifts": drifts,
            "trades_needed": trades_needed,
            "threshold_pct": config["threshold_pct"],
        }

    def get_config(self, user_id):
        return self._configs.get(user_id)

    def record_rebalance(self, user_id):
        if user_id in self._configs:
            self._configs[user_id]["last_rebalance"] = datetime.now(timezone.utc).isoformat()
            self._configs[user_id]["rebalance_count"] += 1


_rebalance_bot = None
def get_rebalance_bot():
    global _rebalance_bot
    if not _rebalance_bot: _rebalance_bot = RebalanceBot()
    return _rebalance_bot
