"""alchemy.api.app — FastAPI v0.5 with Notifications"""
from __future__ import annotations
import json, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import structlog

from alchemy.api.crypto_routes       import router  as crypto_router
from alchemy.api.token_routes        import token_router, workflow_router
from alchemy.api.auth_routes         import router  as auth_router
from alchemy.api.admin_routes        import router  as admin_router
from alchemy.api.notification_routes import router  as notification_router
from alchemy.auth.middleware         import SecurityHeadersMiddleware, get_current_user, CurrentUser, require_permission
from alchemy.core.config import get_config
from alchemy.core.state  import TradingSignal

log = structlog.get_logger(__name__)

class CM:
    def __init__(self): self.active: list[WebSocket] = []
    async def connect(self, ws):  await ws.accept(); self.active.append(ws)
    def disconnect(self, ws):     self.active = [w for w in self.active if w is not ws]
    async def broadcast(self, event, data):
        msg = json.dumps({"event": event, **data})
        dead = []
        for ws in self.active:
            try: await ws.send_text(msg)
            except: dead.append(ws)
        for ws in dead: self.disconnect(ws)

manager = CM()

class SignalRequest(BaseModel):
    ticker: str; market: str = "NSE"; broker: str = "PAPER"
    news_headlines: list[str] = []; price_data: dict = {}

@asynccontextmanager
async def lifespan(app):
    log.info("alchemy.startup", version="0.5.0", env=get_config().env)
    try:
        from alchemy.api.database import create_tables
        await create_tables()
    except Exception as e:
        log.warning("db.tables_init_failed", error=str(e))
    try:
        from alchemy.tokens.manager import get_token_manager
        get_token_manager().start_auto_refresh()
    except Exception: pass
    # Start notification dispatcher
    try:
        from alchemy.notifications.dispatcher import get_dispatcher
        await get_dispatcher().start()
        log.info("notification.dispatcher_started")
    except Exception as e:
        log.warning("notification.dispatcher_start_failed", error=str(e))
    yield
    # Stop dispatcher on shutdown
    try:
        from alchemy.notifications.dispatcher import get_dispatcher
        await get_dispatcher().stop()
    except Exception: pass
    log.info("alchemy.shutdown")

app = FastAPI(title="Alchemy Trading Platform", version="0.5.0", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000","http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(crypto_router)
app.include_router(token_router)
app.include_router(workflow_router)
app.include_router(notification_router)

@app.get("/health")
async def health(): return {"status":"ok","version":"0.5.0","env":get_config().env}

@app.post("/signal")
async def generate_signal(req: SignalRequest,
                           user: CurrentUser = Depends(require_permission("signals:generate"))):
    if not get_config().enable_ai_agents: raise HTTPException(503,"AI agents disabled")
    try:
        from alchemy.agents.graph import run_agent
        from alchemy.notifications.models import NotificationEvent
        from alchemy.notifications.dispatcher import dispatch
        sig: TradingSignal = run_agent(ticker=req.ticker, market=req.market,
            broker=req.broker, price_data=req.price_data, news_headlines=req.news_headlines)
        # Broadcast via WebSocket + Notifications
        await manager.broadcast("signal", sig.to_dict())
        await dispatch(NotificationEvent.from_signal(sig, user_id=user.user_id))
        return sig.to_dict()
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/risk/status")
async def risk_status(user: CurrentUser = Depends(require_permission("trading:read"))):
    from alchemy.risk.manager import RiskManager; return RiskManager().status()

@app.post("/risk/emergency-stop")
async def emergency_stop(user: CurrentUser = Depends(require_permission("trading:write"))):
    from alchemy.risk.manager import RiskManager
    from alchemy.notifications.models import NotificationEvent
    from alchemy.notifications.dispatcher import dispatch
    rm = RiskManager(); rm.trigger_emergency_stop(f"Manual by {user.email}")
    status = rm.status()
    await manager.broadcast("risk_alert", status)
    await dispatch(NotificationEvent.risk_alert(status, user_id=user.user_id))
    return {"ok":True}

@app.delete("/risk/emergency-stop")
async def clear_stop(user: CurrentUser = Depends(require_permission("trading:write"))):
    from alchemy.risk.manager import RiskManager; RiskManager().reset_emergency_stop(); return {"ok":True}

@app.post("/risk/block")
async def block(body: dict, user: CurrentUser = Depends(require_permission("trading:write"))):
    from alchemy.risk.manager import RiskManager; RiskManager().block_ticker(body.get("ticker","")); return {"ok":True}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "subscribe":
                await ws.send_text(json.dumps({"event":"subscribed","symbols":msg.get("symbols",[])}))
    except WebSocketDisconnect: manager.disconnect(ws)

static_dir = os.path.join(os.path.dirname(__file__), "../../static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
