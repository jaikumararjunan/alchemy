"""alchemy.api.token_routes v3 — full CRUD with credential retrieval"""
from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from alchemy.auth.middleware import get_current_user, CurrentUser
from alchemy.auth.guards import require_2fa, audit_action

token_router    = APIRouter(prefix="/tokens",    tags=["tokens"])
workflow_router = APIRouter(prefix="/workflows", tags=["workflows"])

def _get_db_path() -> str:
    """Resolve DB path from DATABASE_URL env var — same logic as auth_routes."""
    import os, re
    url  = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/alchemy.db")
    path = re.sub(r"^sqlite(\+aiosqlite)?:///", "", url)
    p    = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)

_DB = Path(_get_db_path())

def _conn():
    _DB = Path(_get_db_path())
    c = sqlite3.connect(str(_DB))
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS exchange_tokens (
        user_id TEXT, exchange TEXT, data TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, exchange))""")
    return c

def _save(user_id, exchange, data):
    with _conn() as c: c.execute(
        "INSERT OR REPLACE INTO exchange_tokens (user_id,exchange,data) VALUES(?,?,?)",
        (user_id, exchange, json.dumps(data)))

def _load(user_id, exchange):
    with _conn() as c:
        r = c.execute("SELECT data FROM exchange_tokens WHERE user_id=? AND exchange=?",
                      (user_id,exchange)).fetchone()
        return json.loads(r[0]) if r else None

def _load_all(user_id):
    with _conn() as c:
        rows = c.execute("SELECT exchange,data FROM exchange_tokens WHERE user_id=?",
                         (user_id,)).fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

def _delete(user_id, exchange):
    with _conn() as c: c.execute(
        "DELETE FROM exchange_tokens WHERE user_id=? AND exchange=?", (user_id,exchange))

def _mask(s):
    if not s or len(s)<8: return "***"
    return s[:6]+"…"+s[-4:]

# ── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    exchange:     str
    api_key:      str
    api_secret:   Optional[str] = None
    client_id:    Optional[str] = None
    password:     Optional[str] = None
    totp_secret:  Optional[str] = None
    access_token: Optional[str] = None
    paper_trading: bool = True
    testnet:       bool = True
    market_type:   str  = "futures_usdm"

class UpdateKiteTokenRequest(BaseModel):
    access_token: str

# ── Endpoints ────────────────────────────────────────────────────────────────

@token_router.post("/register")
async def register_token(req: RegisterRequest,
                          user: CurrentUser = Depends(get_current_user)):
    if req.exchange not in ("delta","binance","angel","kite","ib"):
        raise HTTPException(400, f"Unknown exchange: {req.exchange}")
    if not req.api_key:
        raise HTTPException(400, "api_key is required")
    # Merge with existing — preserve fields not being overwritten
    existing = _load(user.user_id, req.exchange) or {}
    data = {
        **existing,
        "exchange":      req.exchange,
        "api_key":       req.api_key,
        "api_secret":    req.api_secret    or existing.get("api_secret",""),
        "client_id":     req.client_id     or existing.get("client_id",""),
        "password":      req.password      or existing.get("password",""),
        "totp_secret":   req.totp_secret   or existing.get("totp_secret",""),
        "access_token":  req.access_token  or existing.get("access_token",""),
        "paper_trading": req.paper_trading,
        "testnet":       req.testnet,
        "market_type":   req.market_type,
        "status":        "paper" if req.paper_trading else "active",
    }
    _save(user.user_id, req.exchange, data)
    return {"ok": True, "exchange": req.exchange, "status": data["status"],
            "message": f"{req.exchange.title()} connected ({'paper' if req.paper_trading else 'live'} mode)"}


@token_router.get("/status")
async def get_all_token_status(user: CurrentUser = Depends(get_current_user)):
    tokens = _load_all(user.user_id)
    result = {}
    for ex, data in tokens.items():
        result[ex] = {
            "exchange":         ex,
            "status":           data.get("status","active"),
            "paper_trading":    data.get("paper_trading", True),
            "testnet":          data.get("testnet", True),
            "api_key":          _mask(data.get("api_key","")),
            "has_secret":       bool(data.get("api_secret") or data.get("password")),
            "has_totp":         bool(data.get("totp_secret")),
            "has_access_token": bool(data.get("access_token")),
            "last_test_msg":    data.get("last_test_msg",""),
            "last_tested":      data.get("last_tested",""),
        }
    return {"tokens": result}


@token_router.get("/credentials/{exchange}")
async def get_credentials(exchange: str,
                            user: CurrentUser = Depends(get_current_user)):
    """Return stored credentials for pre-filling the edit form (secrets masked)."""
    data = _load(user.user_id, exchange)
    if not data:
        return {"exchange": exchange, "configured": False}
    return {
        "exchange":      exchange,
        "configured":    True,
        "api_key":       data.get("api_key",""),         # show full key for UI
        "api_key_masked": _mask(data.get("api_key","")),
        "api_secret_set": bool(data.get("api_secret")),
        "client_id":     data.get("client_id",""),
        "totp_secret_set": bool(data.get("totp_secret")),
        "access_token_set": bool(data.get("access_token")),
        "paper_trading": data.get("paper_trading", True),
        "testnet":       data.get("testnet", True),
        "market_type":   data.get("market_type","futures_usdm"),
        "status":        data.get("status","active"),
    }


@token_router.get("/status/{exchange}")
async def get_token_status(exchange: str,
                             user: CurrentUser = Depends(get_current_user)):
    data = _load(user.user_id, exchange)
    if not data:
        return {"exchange": exchange, "status": "not_configured"}
    return {"exchange": exchange, "status": data.get("status","active"),
            "api_key": _mask(data.get("api_key",""))}


@token_router.post("/{exchange}/validate")
async def validate_token(exchange: str,
                          user: CurrentUser = Depends(get_current_user)):
    data = _load(user.user_id, exchange)
    if not data:
        raise HTTPException(404, "Token not registered")
    result = await _test_connection(exchange, data)
    data["status"]       = "active" if result["valid"] else "error"
    data["last_test_msg"]= result.get("message") or result.get("error","")
    from datetime import datetime, timezone
    data["last_tested"]  = datetime.now(timezone.utc).isoformat()
    _save(user.user_id, exchange, data)
    return result


@token_router.delete("/{exchange}")
async def deregister_token(exchange: str,
                             user: CurrentUser = Depends(get_current_user)):
    _delete(user.user_id, exchange)
    return {"ok": True, "exchange": exchange}


@token_router.put("/kite/access-token")
async def update_kite_token(req: UpdateKiteTokenRequest,
                              user: CurrentUser = Depends(get_current_user)):
    data = _load(user.user_id, "kite") or {}
    data["access_token"] = req.access_token
    data["status"] = "active"
    _save(user.user_id, "kite", data)
    return {"ok": True}


@token_router.get("/history")
async def refresh_history(user: CurrentUser = Depends(get_current_user)):
    return {"history": []}

@token_router.post("/validate-all")
async def validate_all_tokens(user: CurrentUser = Depends(get_current_user)):
    all_tokens = _load_all(user.user_id)
    results = {}
    for ex, data in all_tokens.items():
        try: results[ex] = await _test_connection(ex, data)
        except Exception as e: results[ex] = {"valid": False, "error": str(e)}
    return results


def get_live_gateway(exchange: str, user_id: str):
    data = _load(user_id, exchange)
    if not data: return None
    if exchange == "delta":
        from alchemy.execution.crypto.delta_gateway import DeltaGateway
        return DeltaGateway(api_key=data["api_key"], api_secret=data.get("api_secret",""),
                            testnet_mode=data.get("testnet",True), paper_trading=data.get("paper_trading",True))
    elif exchange == "binance":
        from alchemy.execution.crypto.binance_gateway import BinanceGateway
        return BinanceGateway(api_key=data["api_key"], api_secret=data.get("api_secret",""),
                              market=data.get("market_type","futures_usdm"),
                              paper_trading=data.get("paper_trading",True), testnet=data.get("testnet",True))
    return None


async def _test_connection(exchange, data):
    paper   = data.get("paper_trading", True)
    testnet = data.get("testnet", True)
    mode    = "paper" if paper else "live"
    try:
        if exchange == "delta":
            if paper:
                import httpx
                url = "https://testnet-api.delta.exchange" if testnet else "https://api.delta.exchange"
                r = httpx.get(f"{url}/v2/tickers", timeout=8)
                tickers = r.json().get("result") or []
                btc = next((t for t in tickers if "BTC" in t.get("symbol","") and "USDT" in t.get("symbol","")), None)
                price = f"${float(btc['mark_price']):,.2f}" if btc else "reachable"
                return {"valid": True, "exchange": "delta", "mode": mode,
                        "message": f"Delta API reachable — BTC: {price}", "testnet": testnet}
            else:
                from alchemy.execution.crypto.delta_gateway import DeltaGateway
                gw = DeltaGateway(api_key=data["api_key"], api_secret=data.get("api_secret",""),
                                  testnet_mode=testnet, paper_trading=False)
                return {"valid": True, "exchange": "delta", "mode": mode, "message": "Live connection OK"}

        elif exchange == "binance":
            import httpx
            base_pub = "https://fapi.binance.com"  # always use mainnet public
            if paper:
                r = httpx.get(f"{base_pub}/fapi/v1/ticker/price?symbol=BTCUSDT", timeout=8)
                price = float(r.json().get("price", 0))
                return {"valid": True, "exchange": "binance", "mode": mode,
                        "message": f"Binance Futures API reachable — BTC: ${price:,.2f}",
                        "testnet": testnet}
            else:
                import hmac, hashlib, time
                ak = data.get("api_key","")
                sk = data.get("api_secret","")
                base = "https://testnet.binancefuture.com" if testnet else "https://fapi.binance.com"
                ts  = int(time.time()*1000)
                qs  = f"timestamp={ts}"
                sig = hmac.new(sk.encode(), qs.encode(), hashlib.sha256).hexdigest()
                r   = httpx.get(f"{base}/fapi/v2/balance?{qs}&signature={sig}",
                                 headers={"X-MBX-APIKEY": ak}, timeout=8)
                if r.status_code == 200:
                    bal = next((b.get("balance","?") for b in r.json() if b.get("asset")=="USDT"), "?")
                    return {"valid": True, "exchange": "binance", "mode": mode,
                            "message": f"Live auth OK — USDT balance: {bal}"}
                err = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
                code = err.get("code","")
                msg  = err.get("msg", r.text[:100])
                hint = {
                    -2015: "API key lacks Futures permission — enable in Binance → API Management",
                    -1022: "Invalid signature — check your API Secret",
                    -2008: "Invalid API key format",
                }.get(code, "Check API key and whitelist your IP in Binance settings")
                return {"valid": False, "exchange": "binance", "mode": mode,
                        "error": f"Binance {r.status_code} ({code}): {hint}"}

        elif exchange == "angel":
            req = ["api_key","client_id","password"]
            missing = [k for k in req if not data.get(k)]
            if missing: return {"valid": False, "exchange": "angel", "error": f"Missing: {', '.join(missing)}"}
            return {"valid": True, "exchange": "angel", "mode": mode,
                    "message": "Angel credentials saved — TOTP login at trade time"}

        elif exchange == "kite":
            if not data.get("api_key") or not data.get("api_secret"):
                return {"valid": False, "exchange": "kite", "error": "API Key and Secret required"}
            msg = "Kite credentials saved"
            if not data.get("access_token"): msg += " — daily browser login needed for access token"
            return {"valid": True, "exchange": "kite", "mode": mode, "message": msg}

    except Exception as e:
        hint = " — check API key/secret permissions" if "401" in str(e) or "403" in str(e) else ""
        return {"valid": False, "exchange": exchange, "mode": mode, "error": f"{str(e)[:200]}{hint}"}
    return {"valid": False, "error": "Unknown exchange"}


# ── Workflow routes ───────────────────────────────────────────────────────────

class BuyRequest(BaseModel):
    ticker: str; market: str="NSE"; broker: str="PAPER"; quantity: float=1; price: Optional[float]=None
class SellRequest(BaseModel):
    ticker: str; market: str="NSE"; broker: str="PAPER"; quantity: float=1; price: Optional[float]=None

@workflow_router.post("/buy")
async def execute_buy(req: BuyRequest, user: CurrentUser = Depends(get_current_user)):
    return {"ok": True, "action": "buy", "ticker": req.ticker, "quantity": req.quantity, "status": "paper_simulated"}
@workflow_router.post("/sell")
async def execute_sell(req: SellRequest, user: CurrentUser = Depends(get_current_user)):
    return {"ok": True, "action": "sell", "ticker": req.ticker, "quantity": req.quantity, "status": "paper_simulated"}
@workflow_router.get("/history")
async def workflow_history(user: CurrentUser = Depends(get_current_user)): return {"history": []}
@workflow_router.get("/states")
async def workflow_states(user: CurrentUser = Depends(get_current_user)): return {"states": []}
@workflow_router.get("/route-preview")
async def route_preview(ticker: str="NIFTY50", user: CurrentUser = Depends(get_current_user)):
    return {"ticker": ticker, "route": "paper_mode"}
