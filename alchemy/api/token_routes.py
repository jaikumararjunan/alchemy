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
    """Test live connection to exchange using stored credentials."""
    import asyncio

    if data.get("paper_trading"):
        return {"valid": True, "exchange": exchange,
                "message": "Paper mode — no live connection needed",
                "mode": "paper"}

    try:
        if exchange == "delta":
            from alchemy.execution.crypto.delta_gateway import DeltaGateway
            gw = DeltaGateway(api_key=data["api_key"], api_secret=data["api_secret"],
                              testnet_mode=data.get("testnet",True), paper_trading=False)
            ticker = gw.get_ticker("BTCUSD")
            return {"valid": True, "exchange": "delta",
                    "btc_price": ticker.get("mark_price"), "mode": "live"}

        elif exchange == "binance":
            from alchemy.execution.crypto.binance_gateway import BinanceGateway
            gw = BinanceGateway(api_key=data["api_key"], api_secret=data["api_secret"],
                                market=data.get("market_type","futures_usdm"),
                                paper_trading=False, testnet=data.get("testnet",True))
            bal = gw.get_balance()
            return {"valid": True, "exchange": "binance", "balance": bal, "mode": "live"}

        elif exchange == "angel":
            return {"valid": True, "exchange": "angel",
                    "message": "Angel credentials saved — login via TOTP on next session",
                    "mode": "live"}

        elif exchange == "kite":
            if not data.get("access_token"):
                return {"valid": False, "exchange": "kite",
                        "error": "No access token — please complete daily Kite login",
                        "mode": "live"}
            return {"valid": True, "exchange": "kite", "mode": "live"}

    except Exception as e:
        return {"valid": False, "exchange": exchange, "error": str(e)}

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
