"""alchemy.api.app — FastAPI v0.3 + Token + Workflow routers"""
from __future__ import annotations
import json, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import structlog

from alchemy.api.crypto_routes  import router  as crypto_router
from alchemy.api.token_routes   import token_router, workflow_router
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
    log.info("alchemy.startup", version="0.3.0", env=get_config().env)
    # Start token auto-refresh background task
    from alchemy.tokens.manager import get_token_manager
    get_token_manager().start_auto_refresh()
    yield
    log.info("alchemy.shutdown")

app = FastAPI(title="Alchemy Trading Platform", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000","http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(crypto_router)
app.include_router(token_router)
app.include_router(workflow_router)

@app.get("/health")
async def health():
    return {"status":"ok","version":"0.3.0","env":get_config().env}

@app.post("/signal")
async def generate_signal(req: SignalRequest):
    if not get_config().enable_ai_agents: raise HTTPException(503,"AI agents disabled")
    try:
        from alchemy.agents.graph import run_agent
        sig: TradingSignal = run_agent(ticker=req.ticker, market=req.market,
            broker=req.broker, price_data=req.price_data, news_headlines=req.news_headlines)
        await manager.broadcast("signal", sig.to_dict())
        return sig.to_dict()
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/risk/status")
async def risk_status():
    from alchemy.risk.manager import RiskManager; return RiskManager().status()

@app.post("/risk/emergency-stop")
async def emergency_stop():
    from alchemy.risk.manager import RiskManager
    rm = RiskManager(); rm.trigger_emergency_stop("Manual via API")
    await manager.broadcast("risk_alert", rm.status()); return {"ok":True}

@app.delete("/risk/emergency-stop")
async def clear_stop():
    from alchemy.risk.manager import RiskManager; RiskManager().reset_emergency_stop(); return {"ok":True}

@app.post("/risk/block")
async def block(body: dict):
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
