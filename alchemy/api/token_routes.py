"""
alchemy.api.token_routes  v2.0
Handles ALL four exchanges: Delta, Binance, Angel Broking, Kite
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from alchemy.auth.middleware import get_current_user, CurrentUser

token_router    = APIRouter(prefix="/tokens",    tags=["tokens"])
workflow_router = APIRouter(prefix="/workflows", tags=["workflows"])

# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    exchange:     str          # delta | binance | angel | kite
    api_key:      str
    api_secret:   Optional[str]  = None
    # Angel Broking extra fields
    client_id:    Optional[str]  = None
    password:     Optional[str]  = None
    totp_secret:  Optional[str]  = None
    # Kite extra
    access_token: Optional[str]  = None
    # Flags
    paper_trading: bool = True
    testnet:       bool = True
    market_type:   str  = "futures_usdm"

class UpdateKiteTokenRequest(BaseModel):
    access_token: str

# ── Persistent storage (sqlite) ───────────────────────────────────────────────

import json, sqlite3
from pathlib import Path

_DB = Path("data/alchemy.db")

def _save_token(user_id: str, exchange: str, data: dict) -> None:
    conn = sqlite3.connect(str(_DB))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_tokens (
                user_id TEXT, exchange TEXT, data TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, exchange)
            )""")
        conn.execute(
            "INSERT OR REPLACE INTO exchange_tokens (user_id, exchange, data) VALUES (?,?,?)",
            (user_id, exchange, json.dumps(data))
        )
        conn.commit()
    finally:
        conn.close()

def _load_token(user_id: str, exchange: str) -> Optional[dict]:
    conn = sqlite3.connect(str(_DB))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_tokens (
                user_id TEXT, exchange TEXT, data TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, exchange)
            )""")
        row = conn.execute(
            "SELECT data FROM exchange_tokens WHERE user_id=? AND exchange=?",
            (user_id, exchange)
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()

def _load_all_tokens(user_id: str) -> dict:
    conn = sqlite3.connect(str(_DB))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_tokens (
                user_id TEXT, exchange TEXT, data TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, exchange)
            )""")
        rows = conn.execute(
            "SELECT exchange, data FROM exchange_tokens WHERE user_id=?",
            (user_id,)
        ).fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}
    finally:
        conn.close()

def _delete_token(user_id: str, exchange: str) -> None:
    conn = sqlite3.connect(str(_DB))
    try:
        conn.execute("DELETE FROM exchange_tokens WHERE user_id=? AND exchange=?",
                     (user_id, exchange))
        conn.commit()
    finally:
        conn.close()

# ── Helper: mask secrets ──────────────────────────────────────────────────────

def _mask(s: str) -> str:
    if not s or len(s) < 8:
        return "***"
    return s[:4] + "…" + s[-4:]

def _safe_data(data: dict) -> dict:
    safe = dict(data)
    for k in ("api_secret", "password", "totp_secret", "access_token"):
        if safe.get(k):
            safe[k] = _mask(safe[k])
    return safe

# ── Endpoints ─────────────────────────────────────────────────────────────────

@token_router.post("/register")
async def register_token(req: RegisterRequest,
                          user: CurrentUser = Depends(get_current_user)):
    if req.exchange not in ("delta","binance","angel","kite"):
        raise HTTPException(400, f"Unknown exchange: {req.exchange}")
    if not req.api_key:
        raise HTTPException(400, "api_key is required")

    data = {
        "exchange":     req.exchange,
        "api_key":      req.api_key,
        "api_secret":   req.api_secret or "",
        "client_id":    req.client_id or "",
        "password":     req.password or "",
        "totp_secret":  req.totp_secret or "",
        "access_token": req.access_token or "",
        "paper_trading":req.paper_trading,
        "testnet":      req.testnet,
        "market_type":  req.market_type,
        "status":       "paper" if req.paper_trading else "active",
    }
    _save_token(user.user_id, req.exchange, data)
    return {"ok": True, "exchange": req.exchange, "status": data["status"],
            "message": f"{req.exchange.title()} connected ({'paper' if req.paper_trading else 'live'} mode)"}


@token_router.get("/status")
async def get_all_token_status(user: CurrentUser = Depends(get_current_user)):
    all_tokens = _load_all_tokens(user.user_id)
    result = {}
    for ex, data in all_tokens.items():
        result[ex] = {
            "exchange":     ex,
            "status":       data.get("status","active"),
            "paper_trading":data.get("paper_trading", True),
            "testnet":      data.get("testnet", True),
            "api_key":      _mask(data.get("api_key","")),
            "has_secret":   bool(data.get("api_secret") or data.get("password")),
        }
    return {"tokens": result}


@token_router.get("/status/{exchange}")
async def get_token_status(exchange: str,
                             user: CurrentUser = Depends(get_current_user)):
    data = _load_token(user.user_id, exchange)
    if not data:
        return {"exchange": exchange, "status": "not_configured"}
    return {"exchange": exchange, "status": data.get("status","active"),
            "api_key": _mask(data.get("api_key",""))}


@token_router.post("/{exchange}/validate")
async def validate_token(exchange: str,
                          user: CurrentUser = Depends(get_current_user)):
    data = _load_token(user.user_id, exchange)
    if not data:
        raise HTTPException(404, "Token not registered")
    try:
        result = await _test_connection(exchange, data)
        # Update status
        data["status"] = "active" if result["valid"] else "error"
        data["error"]  = result.get("error","")
        _save_token(user.user_id, exchange, data)
        return result
    except Exception as e:
        return {"valid": False, "exchange": exchange, "error": str(e)}


@token_router.delete("/{exchange}")
async def deregister_token(exchange: str,
                             user: CurrentUser = Depends(get_current_user)):
    _delete_token(user.user_id, exchange)
    return {"ok": True, "exchange": exchange}


@token_router.put("/kite/access-token")
async def update_kite_token(req: UpdateKiteTokenRequest,
                              user: CurrentUser = Depends(get_current_user)):
    data = _load_token(user.user_id, "kite")
    if not data:
        raise HTTPException(404, "Kite token not registered")
    data["access_token"] = req.access_token
    data["status"] = "active"
    _save_token(user.user_id, "kite", data)
    return {"ok": True}


@token_router.get("/history")
async def refresh_history(user: CurrentUser = Depends(get_current_user)):
    return {"history": []}


@token_router.post("/validate-all")
async def validate_all_tokens(user: CurrentUser = Depends(get_current_user)):
    all_tokens = _load_all_tokens(user.user_id)
    results = {}
    for ex, data in all_tokens.items():
        try:
            results[ex] = await _test_connection(ex, data)
        except Exception as e:
            results[ex] = {"valid": False, "error": str(e)}
    return results


async def _test_connection(exchange: str, data: dict) -> dict:
    """
    Test exchange connectivity.
    Paper/testnet mode  → hit PUBLIC endpoints only (no auth, no signature)
    Live mode           → hit AUTHENTICATED endpoints using stored key/secret
    """
    paper = data.get("paper_trading", True)
    testnet = data.get("testnet", True)
    mode = "paper" if paper else "live"

    try:
        if exchange == "delta":
            if paper:
                # Public tickers endpoint — no auth required
                url = "https://testnet-api.delta.exchange" if testnet else "https://api.delta.exchange"
                import httpx
                r = httpx.get(f"{url}/v2/tickers", timeout=8)
                tickers = r.json().get("result") or []
                btc = next((t for t in tickers if "BTC" in t.get("symbol","") and "USDT" in t.get("symbol","")), None)
                price = btc.get("mark_price", "unknown") if btc else "API reachable"
                return {"valid": True, "exchange": "delta", "mode": mode,
                        "message": f"Delta Exchange API reachable — BTC: ${float(price):,.2f}" if price != "API reachable" else "Delta Exchange API reachable",
                        "testnet": testnet}
            else:
                from alchemy.execution.crypto.delta_gateway import DeltaGateway
                gw = DeltaGateway(api_key=data["api_key"], api_secret=data.get("api_secret",""),
                                  testnet_mode=testnet, paper_trading=False)
                bal = gw.get_wallet_balance()
                return {"valid": True, "exchange": "delta", "mode": mode,
                        "message": "Authenticated OK", "balance": bal}

        elif exchange == "binance":
            if paper:
                # Public ticker — no API key needed
                import httpx
                base = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
                r = httpx.get(f"{base}/fapi/v1/ticker/price?symbol=BTCUSDT", timeout=8)
                price = r.json().get("price", "unknown")
                return {"valid": True, "exchange": "binance", "mode": mode,
                        "message": f"Binance public API reachable — BTC price: ${float(price):,.2f}",
                        "testnet": testnet}
            else:
                # Live: authenticate and check account info
                import httpx, hmac, hashlib, time
                api_key = data.get("api_key","")
                api_secret = data.get("api_secret","")
                base = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
                ts = int(time.time() * 1000)
                qs = f"timestamp={ts}"
                sig = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
                r = httpx.get(f"{base}/fapi/v2/account?{qs}&signature={sig}",
                              headers={"X-MBX-APIKEY": api_key}, timeout=8)
                if r.status_code == 200:
                    d = r.json()
                    bal = d.get("totalWalletBalance","?")
                    return {"valid": True, "exchange": "binance", "mode": mode,
                            "message": f"Authenticated OK — Wallet balance: {bal} USDT"}
                else:
                    return {"valid": False, "exchange": "binance", "mode": mode,
                            "error": f"Binance API error {r.status_code}: {r.text[:120]}"}

        elif exchange == "angel":
            # Angel always requires TOTP — just validate credentials are saved
            required = ["api_key", "client_id", "password"]
            missing = [k for k in required if not data.get(k)]
            if missing:
                return {"valid": False, "exchange": "angel",
                        "error": f"Missing required fields: {', '.join(missing)}"}
            return {"valid": True, "exchange": "angel", "mode": mode,
                    "message": "Credentials saved. SmartAPI TOTP login happens at trading time."}

        elif exchange == "kite":
            if not data.get("api_key") or not data.get("api_secret"):
                return {"valid": False, "exchange": "kite",
                        "error": "API Key and Secret are required"}
            if not data.get("access_token"):
                return {"valid": True, "exchange": "kite", "mode": mode,
                        "message": "Credentials saved. Kite requires daily browser login for access token.",
                        "warning": "No access token yet — complete Kite OAuth login"}
            return {"valid": True, "exchange": "kite", "mode": mode,
                    "message": "Kite credentials and access token present"}

    except Exception as e:
        err = str(e)
        if "401" in err or "403" in err:
            hint = " — Check your API key/secret are correct and have Futures trading permission"
        elif "timeout" in err.lower() or "connect" in err.lower():
            hint = " — Network timeout. Check your internet connection"
        else:
            hint = ""
        return {"valid": False, "exchange": exchange, "mode": mode,
                "error": f"{err[:200]}{hint}"}

    return {"valid": False, "error": "Unknown exchange"}


# ── Gateway factory — used by crypto_routes ───────────────────────────────────

def get_live_gateway(exchange: str, user_id: str):
    """Return a live gateway instance using stored user credentials."""
    data = _load_token(user_id, exchange)
    if not data:
        return None

    if exchange == "delta":
        from alchemy.execution.crypto.delta_gateway import DeltaGateway
        return DeltaGateway(
            api_key=data["api_key"], api_secret=data["api_secret"],
            testnet_mode=data.get("testnet", True),
            paper_trading=data.get("paper_trading", True),
        )
    elif exchange == "binance":
        from alchemy.execution.crypto.binance_gateway import BinanceGateway
        return BinanceGateway(
            api_key=data["api_key"], api_secret=data["api_secret"],
            market=data.get("market_type","futures_usdm"),
            paper_trading=data.get("paper_trading", True),
            testnet=data.get("testnet", True),
        )
    return None


# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW ROUTES
# ══════════════════════════════════════════════════════════════════════════════

class BuyRequest(BaseModel):
    ticker: str; market: str = "NSE"; broker: str = "PAPER"
    quantity: float = 1; price: Optional[float] = None

class SellRequest(BaseModel):
    ticker: str; market: str = "NSE"; broker: str = "PAPER"
    quantity: float = 1; price: Optional[float] = None

@workflow_router.post("/buy")
async def execute_buy(req: BuyRequest, user: CurrentUser = Depends(get_current_user)):
    return {"ok": True, "action": "buy", "ticker": req.ticker,
            "quantity": req.quantity, "broker": req.broker, "status": "paper_simulated"}

@workflow_router.post("/sell")
async def execute_sell(req: SellRequest, user: CurrentUser = Depends(get_current_user)):
    return {"ok": True, "action": "sell", "ticker": req.ticker,
            "quantity": req.quantity, "broker": req.broker, "status": "paper_simulated"}

@workflow_router.get("/history")
async def workflow_history(user: CurrentUser = Depends(get_current_user)):
    return {"history": []}

@workflow_router.get("/states")
async def workflow_states(user: CurrentUser = Depends(get_current_user)):
    return {"states": []}

@workflow_router.get("/route-preview")
async def route_preview(ticker: str = "NIFTY50", broker: str = "PAPER",
                         user: CurrentUser = Depends(get_current_user)):
    return {"ticker": ticker, "broker": broker, "route": "paper_mode"}
