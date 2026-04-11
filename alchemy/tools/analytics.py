"""
alchemy.tools — Tax Reports, API Vault, Webhooks, Arbitrage, Correlations,
                 Risk Dashboard, Order Book
===========================================================================
Features 7, 11, 12, 13, 14, 15, 19 from the roadmap.
"""
from __future__ import annotations
import json, os, hashlib, math, time, uuid
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path
import structlog

log = structlog.get_logger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Feature 7: Tax Report Generator (Indian taxes)
# ══════════════════════════════════════════════════════════════════════════════

INDIAN_TAX_RATES = {
    "stcg_equity": 0.15,      # Short-term capital gains (equity < 1 year)
    "ltcg_equity": 0.10,      # Long-term (equity > 1 year, above 1L exemption)
    "stcg_fno": 0.30,         # F&O = business income (slab rate, simplified)
    "crypto": 0.30,           # Flat 30% on crypto gains
    "crypto_tds": 0.01,       # 1% TDS on crypto transactions > 50K
    "ltcg_exemption": 100000, # 1 Lakh exemption on LTCG
    "surcharge_threshold": 5000000,
    "cess": 0.04,             # 4% health & education cess
}

def generate_tax_report(trades: list[dict], financial_year: str = "2025-26") -> dict:
    """
    Generate Indian tax report from trade history.

    Categories:
      - Equity STCG (held < 12 months): 15%
      - Equity LTCG (held > 12 months): 10% above 1L exemption
      - F&O / Intraday: Business income (30% slab)
      - Crypto: Flat 30% (no offset of losses)
    """
    fy_start = f"20{financial_year[:2]}-04-01"
    fy_end = f"20{financial_year[3:]}-03-31"

    categories = {
        "equity_stcg": {"trades": [], "gross_pnl": 0, "fees": 0, "net_pnl": 0, "tax": 0},
        "equity_ltcg": {"trades": [], "gross_pnl": 0, "fees": 0, "net_pnl": 0, "tax": 0},
        "fno":         {"trades": [], "gross_pnl": 0, "fees": 0, "net_pnl": 0, "tax": 0},
        "crypto":      {"trades": [], "gross_pnl": 0, "fees": 0, "net_pnl": 0, "tax": 0},
    }

    for t in trades:
        pnl = t.get("net_pnl", 0)
        fee = t.get("fee", 0)
        symbol = t.get("symbol", "").upper()

        # Classify
        if any(c in symbol for c in ["USDT", "BTC", "ETH", "SOL", "BNB", "DOGE", "XRP"]):
            cat = "crypto"
        elif any(c in symbol for c in ["FUT", "OPT", "CE", "PE"]):
            cat = "fno"
        else:
            cat = "equity_stcg"  # Default to STCG

        categories[cat]["trades"].append(t)
        categories[cat]["gross_pnl"] += pnl + fee
        categories[cat]["fees"] += fee
        categories[cat]["net_pnl"] += pnl

    # Calculate taxes
    rates = INDIAN_TAX_RATES

    # Crypto: 30% flat, no loss offset
    crypto_gains = max(0, categories["crypto"]["net_pnl"])
    categories["crypto"]["tax"] = round(crypto_gains * rates["crypto"], 2)

    # Equity STCG: 15%
    stcg = categories["equity_stcg"]["net_pnl"]
    categories["equity_stcg"]["tax"] = round(max(0, stcg) * rates["stcg_equity"], 2)

    # Equity LTCG: 10% above 1L exemption
    ltcg = categories["equity_ltcg"]["net_pnl"]
    taxable_ltcg = max(0, ltcg - rates["ltcg_exemption"])
    categories["equity_ltcg"]["tax"] = round(taxable_ltcg * rates["ltcg_equity"], 2)

    # F&O: 30% (simplified)
    fno = categories["fno"]["net_pnl"]
    categories["fno"]["tax"] = round(max(0, fno) * rates["stcg_fno"], 2)

    total_tax = sum(c["tax"] for c in categories.values())
    cess = round(total_tax * rates["cess"], 2)

    return {
        "financial_year": financial_year,
        "period": {"from": fy_start, "to": fy_end},
        "categories": {k: {
            "trade_count": len(v["trades"]),
            "gross_pnl": round(v["gross_pnl"], 2),
            "fees": round(v["fees"], 2),
            "net_pnl": round(v["net_pnl"], 2),
            "tax": v["tax"],
        } for k, v in categories.items()},
        "summary": {
            "total_trades": sum(len(v["trades"]) for v in categories.values()),
            "total_gross_pnl": round(sum(v["gross_pnl"] for v in categories.values()), 2),
            "total_fees": round(sum(v["fees"] for v in categories.values()), 2),
            "total_net_pnl": round(sum(v["net_pnl"] for v in categories.values()), 2),
            "total_tax": round(total_tax, 2),
            "cess_4pct": cess,
            "total_liability": round(total_tax + cess, 2),
        },
        "disclaimer": "This is an estimate for reference only. Consult a Chartered Accountant for actual tax filing.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Feature 12: API Key Vault (Encrypted)
# ══════════════════════════════════════════════════════════════════════════════

import base64

def _derive_key(password: str) -> bytes:
    """Derive encryption key from password using SHA256."""
    return hashlib.sha256(password.encode()).digest()

def encrypt_value(value: str, password: str = "") -> str:
    """Simple XOR encryption (use AES in production with cryptography lib)."""
    if not password:
        password = os.environ.get("VAULT_MASTER_KEY", "alchemy-vault-2026")
    key = _derive_key(password)
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(value.encode()))
    return base64.b64encode(encrypted).decode()

def decrypt_value(encrypted: str, password: str = "") -> str:
    """Decrypt value."""
    if not password:
        password = os.environ.get("VAULT_MASTER_KEY", "alchemy-vault-2026")
    key = _derive_key(password)
    data = base64.b64decode(encrypted)
    decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return decrypted.decode()


class APIKeyVault:
    """Encrypted storage for exchange API keys."""

    def __init__(self, data_dir="data/vault"):
        self._dir = Path(data_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def store(self, user_id: str, exchange: str, api_key: str, api_secret: str, **extra):
        data = {
            "api_key": encrypt_value(api_key),
            "api_secret": encrypt_value(api_secret),
            "exchange": exchange,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            **{k: encrypt_value(str(v)) for k, v in extra.items()},
        }
        path = self._dir / f"{user_id}_{exchange}.json"
        with open(path, "w") as f:
            json.dump(data, f)
        log.info("vault.stored", user_id=user_id, exchange=exchange)
        return {"ok": True, "exchange": exchange}

    def retrieve(self, user_id: str, exchange: str) -> Optional[dict]:
        path = self._dir / f"{user_id}_{exchange}.json"
        if not path.exists(): return None
        with open(path) as f:
            data = json.load(f)
        return {
            "api_key": decrypt_value(data["api_key"]),
            "api_secret": decrypt_value(data["api_secret"]),
            "exchange": data["exchange"],
            "stored_at": data.get("stored_at"),
        }

    def list_keys(self, user_id: str) -> list[dict]:
        keys = []
        for p in self._dir.glob(f"{user_id}_*.json"):
            exchange = p.stem.replace(f"{user_id}_", "")
            with open(p) as f:
                data = json.load(f)
            keys.append({
                "exchange": exchange,
                "api_key_preview": decrypt_value(data["api_key"])[:6] + "***",
                "stored_at": data.get("stored_at"),
            })
        return keys

    def delete(self, user_id: str, exchange: str) -> bool:
        path = self._dir / f"{user_id}_{exchange}.json"
        if path.exists():
            path.unlink()
            return True
        return False


_vault = None
def get_vault():
    global _vault
    if not _vault: _vault = APIKeyVault()
    return _vault


# ══════════════════════════════════════════════════════════════════════════════
# Feature 13: Webhook Alerts (Discord/Slack/Custom)
# ══════════════════════════════════════════════════════════════════════════════

import asyncio

async def send_webhook(url: str, payload: dict, format_type: str = "json") -> dict:
    """Send alert to any webhook URL."""
    import httpx
    try:
        if "discord" in url.lower():
            body = _format_discord(payload)
        elif "slack" in url.lower():
            body = _format_slack(payload)
        else:
            body = payload

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=body)
            return {"ok": resp.status_code < 300, "status": resp.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _format_discord(payload: dict) -> dict:
    """Format payload for Discord webhook."""
    return {
        "embeds": [{
            "title": payload.get("title", "Alchemy Alert"),
            "description": payload.get("message", ""),
            "color": 3447003 if payload.get("type") == "buy" else 15158332,
            "fields": [
                {"name": k, "value": str(v), "inline": True}
                for k, v in payload.get("data", {}).items()
            ][:6],
            "footer": {"text": "Alchemy Trading Platform"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }


def _format_slack(payload: dict) -> dict:
    """Format payload for Slack webhook."""
    return {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text",
                "text": payload.get("title", "Alchemy Alert")}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": payload.get("message", "")}},
        ]
    }


_webhooks: dict[str, list[dict]] = {}

def register_webhook(user_id, name, url, events=None):
    hook = {"id": str(uuid.uuid4())[:8], "name": name, "url": url,
            "events": events or ["trade", "alert", "risk"], "active": True}
    _webhooks.setdefault(user_id, []).append(hook)
    return hook

def get_webhooks(user_id):
    return _webhooks.get(user_id, [])

def remove_webhook(user_id, hook_id):
    _webhooks[user_id] = [h for h in _webhooks.get(user_id, []) if h["id"] != hook_id]


# ══════════════════════════════════════════════════════════════════════════════
# Feature 14: Multi-Exchange Arbitrage Detector
# ══════════════════════════════════════════════════════════════════════════════

async def detect_arbitrage(symbols: list[str] = None) -> list[dict]:
    """
    Monitor price differences across exchanges.
    Alert when spread exceeds threshold.
    """
    import httpx
    if not symbols:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    opportunities = []

    async with httpx.AsyncClient(timeout=10) as client:
        for symbol in symbols:
            prices = {}
            # Binance
            try:
                r = await client.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
                prices["binance"] = float(r.json()["price"])
            except: pass

            # Delta Exchange (if available)
            try:
                r = await client.get(f"https://api.delta.exchange/v2/tickers/{symbol}")
                d = r.json()
                if d.get("result"):
                    prices["delta"] = float(d["result"].get("mark_price", 0))
            except: pass

            if len(prices) < 2:
                continue

            # Find spread
            exchanges = list(prices.keys())
            for i in range(len(exchanges)):
                for j in range(i + 1, len(exchanges)):
                    e1, e2 = exchanges[i], exchanges[j]
                    p1, p2 = prices[e1], prices[e2]
                    if p1 == 0 or p2 == 0: continue
                    spread_pct = abs(p1 - p2) / min(p1, p2) * 100
                    if spread_pct > 0.1:  # >0.1% spread
                        buy_exchange = e1 if p1 < p2 else e2
                        sell_exchange = e2 if p1 < p2 else e1
                        opportunities.append({
                            "symbol": symbol,
                            "buy_exchange": buy_exchange,
                            "buy_price": min(p1, p2),
                            "sell_exchange": sell_exchange,
                            "sell_price": max(p1, p2),
                            "spread_pct": round(spread_pct, 4),
                            "est_profit_per_unit": round(abs(p1 - p2), 2),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

    return sorted(opportunities, key=lambda x: -x["spread_pct"])


# ══════════════════════════════════════════════════════════════════════════════
# Feature 11: Portfolio Correlation Matrix
# ══════════════════════════════════════════════════════════════════════════════

def calculate_correlation_matrix(price_series: dict[str, list[float]]) -> dict:
    """
    Calculate correlation matrix between assets.

    Args:
        price_series: {symbol: [price1, price2, ...]}

    Returns:
        Correlation matrix + diversification suggestions.
    """
    symbols = list(price_series.keys())
    n = len(symbols)
    if n < 2:
        return {"error": "Need at least 2 assets"}

    # Calculate returns
    returns = {}
    for sym, prices in price_series.items():
        if len(prices) < 2: continue
        rets = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        returns[sym] = rets

    # Build correlation matrix
    matrix = {}
    for i, s1 in enumerate(symbols):
        row = {}
        for j, s2 in enumerate(symbols):
            if s1 not in returns or s2 not in returns: continue
            r1, r2 = returns[s1], returns[s2]
            min_len = min(len(r1), len(r2))
            if min_len < 5: continue
            r1, r2 = r1[:min_len], r2[:min_len]
            corr = _pearson(r1, r2)
            row[s2] = round(corr, 4)
        matrix[s1] = row

    # Find high correlations (diversification warnings)
    warnings = []
    for i, s1 in enumerate(symbols):
        for j, s2 in enumerate(symbols):
            if j <= i: continue
            corr = matrix.get(s1, {}).get(s2, 0)
            if abs(corr) > 0.8:
                warnings.append({
                    "pair": f"{s1}/{s2}",
                    "correlation": corr,
                    "warning": f"High {'positive' if corr > 0 else 'negative'} correlation — "
                               f"consider {'diversifying' if corr > 0 else 'checking hedge'}",
                })

    return {
        "symbols": symbols,
        "matrix": matrix,
        "warnings": warnings,
        "diversification_score": round(1 - _avg_abs_correlation(matrix, symbols), 2),
    }


def _pearson(x, y):
    n = len(x)
    if n == 0: return 0
    mx, my = sum(x)/n, sum(y)/n
    sx = math.sqrt(sum((xi-mx)**2 for xi in x)/n)
    sy = math.sqrt(sum((yi-my)**2 for yi in y)/n)
    if sx == 0 or sy == 0: return 0
    return sum((xi-mx)*(yi-my) for xi, yi in zip(x, y)) / (n * sx * sy)


def _avg_abs_correlation(matrix, symbols):
    total, count = 0, 0
    for i, s1 in enumerate(symbols):
        for j, s2 in enumerate(symbols):
            if j <= i: continue
            total += abs(matrix.get(s1, {}).get(s2, 0))
            count += 1
    return total / count if count > 0 else 0


# ══════════════════════════════════════════════════════════════════════════════
# Feature 15: Risk-Adjusted Performance Dashboard
# ══════════════════════════════════════════════════════════════════════════════

def calculate_risk_metrics(equity_curve: list[float], risk_free_rate: float = 0.05) -> dict:
    """
    Calculate comprehensive risk-adjusted performance metrics.

    Returns: Sharpe, Sortino, Calmar, VaR, CVaR, rolling metrics.
    """
    if len(equity_curve) < 10:
        return {"error": "Need at least 10 data points"}

    returns = [(equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
               for i in range(1, len(equity_curve))]

    n = len(returns)
    mean_ret = sum(returns) / n
    daily_rf = risk_free_rate / 252

    # Std dev
    std = math.sqrt(sum((r - mean_ret)**2 for r in returns) / (n-1))

    # Downside deviation (for Sortino)
    down_rets = [min(0, r - daily_rf) for r in returns]
    downside_std = math.sqrt(sum(r**2 for r in down_rets) / n)

    # Sharpe ratio (annualized)
    sharpe = ((mean_ret - daily_rf) / std * math.sqrt(252)) if std > 0 else 0

    # Sortino ratio
    sortino = ((mean_ret - daily_rf) / downside_std * math.sqrt(252)) if downside_std > 0 else 0

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0
    for val in equity_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak
        if dd > max_dd: max_dd = dd

    # Calmar ratio (annualized return / max drawdown)
    total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
    periods = len(equity_curve)
    ann_return = (1 + total_return) ** (252 / periods) - 1 if periods > 0 else 0
    calmar = ann_return / max_dd if max_dd > 0 else 0

    # VaR and CVaR (95%)
    sorted_returns = sorted(returns)
    var_idx = int(n * 0.05)
    var_95 = sorted_returns[var_idx] if var_idx < n else 0
    cvar_95 = sum(sorted_returns[:var_idx+1]) / (var_idx+1) if var_idx > 0 else var_95

    # Win/loss stats
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]

    return {
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(ann_return * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "calmar_ratio": round(calmar, 3),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "volatility_ann_pct": round(std * math.sqrt(252) * 100, 2),
        "var_95_pct": round(var_95 * 100, 3),
        "cvar_95_pct": round(cvar_95 * 100, 3),
        "win_rate_pct": round(len(wins) / n * 100, 1) if n > 0 else 0,
        "avg_win_pct": round(sum(wins) / len(wins) * 100, 3) if wins else 0,
        "avg_loss_pct": round(sum(losses) / len(losses) * 100, 3) if losses else 0,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 2) if losses and sum(losses) != 0 else 0,
        "best_day_pct": round(max(returns) * 100, 3),
        "worst_day_pct": round(min(returns) * 100, 3),
        "data_points": n,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Feature 19: Order Book Depth
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_order_book(symbol: str = "BTCUSDT", limit: int = 20) -> dict:
    """Fetch order book depth from Binance."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.binance.com/api/v3/depth",
                params={"symbol": symbol, "limit": limit}
            )
            data = resp.json()

        bids = [{"price": float(b[0]), "qty": float(b[1]),
                 "total": float(b[0]) * float(b[1])} for b in data.get("bids", [])]
        asks = [{"price": float(a[0]), "qty": float(a[1]),
                 "total": float(a[0]) * float(a[1])} for a in data.get("asks", [])]

        bid_wall = max(bids, key=lambda x: x["qty"]) if bids else {}
        ask_wall = max(asks, key=lambda x: x["qty"]) if asks else {}

        spread = asks[0]["price"] - bids[0]["price"] if bids and asks else 0
        spread_pct = (spread / bids[0]["price"] * 100) if bids and bids[0]["price"] > 0 else 0

        return {
            "symbol": symbol,
            "bids": bids, "asks": asks,
            "bid_wall": bid_wall, "ask_wall": ask_wall,
            "spread": round(spread, 2),
            "spread_pct": round(spread_pct, 4),
            "total_bid_volume": round(sum(b["qty"] for b in bids), 4),
            "total_ask_volume": round(sum(a["qty"] for a in asks), 4),
            "imbalance": round(
                (sum(b["qty"] for b in bids) - sum(a["qty"] for a in asks)) /
                max(1, sum(b["qty"] for b in bids) + sum(a["qty"] for a in asks)) * 100, 2
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}
