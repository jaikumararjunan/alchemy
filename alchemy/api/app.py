"""alchemy.api.app — v0.5.1 — all systems integrated"""
from __future__ import annotations
import json, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import structlog

from alchemy.api.crypto_routes       import router as crypto_router
from alchemy.api.token_routes        import token_router, workflow_router
from alchemy.api.auth_routes         import router as auth_router
from alchemy.api.admin_routes        import router as admin_router
from alchemy.api.notification_routes import router as notification_router
from alchemy.api.intelligence_routes import router as intelligence_router
from alchemy.auth.middleware         import SecurityHeadersMiddleware, get_current_user, CurrentUser, require_permission
from alchemy.core.config import get_config

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
    log.info("alchemy.startup", version="0.5.1")
    # DB tables + seed admin
    try:
        from alchemy.api.database import create_tables
        from alchemy.users.models import User, UserStatus
        from alchemy.auth.service import AuthService
        from alchemy.auth.security import hash_password
        from sqlalchemy import select

        await create_tables()
        log.info("db.tables_ready")

        admin_email = os.environ.get("ADMIN_EMAIL", "admin@alchemy.in")
        admin_pwd   = os.environ.get("ADMIN_PASSWORD", "Alchemy#Admin!2024")

        from alchemy.api.database import get_session_factory
        async with get_session_factory()() as db:
            result  = await db.execute(select(User).where(User.email == admin_email))
            existing = result.scalar_one_or_none()
            if existing:
                # Ensure admin is active with correct role
                if existing.status != UserStatus.ACTIVE.value:
                    existing.status = UserStatus.ACTIVE.value
                    existing.email_verified = True
                    await db.commit()
                log.info("db.admin_exists", email=admin_email)
            else:
                svc = AuthService()
                user = await svc.signup(db, email=admin_email, username="superadmin",
                    full_name="Super Admin", password=admin_pwd, role="super_admin")
                user.status = UserStatus.ACTIVE.value
                user.email_verified = True
                await db.commit()
                log.info("db.admin_created", email=admin_email)
    except Exception as e:
        log.warning("db.init_failed", error=str(e), hint="Run: python scripts/create_admin.py")
    # Token auto-refresh
    try:
        from alchemy.tokens.manager import get_token_manager
        get_token_manager().start_auto_refresh()
    except Exception: pass
    # Notification dispatcher
    try:
        from alchemy.notifications.dispatcher import get_dispatcher
        await get_dispatcher().start()
    except Exception as e:
        log.warning("notification.start_failed", error=str(e))
    yield
    try:
        from alchemy.notifications.dispatcher import get_dispatcher
        await get_dispatcher().stop()
    except Exception: pass
    log.info("alchemy.shutdown")

app = FastAPI(title="Alchemy Trading Platform", version="0.5.1", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000","http://localhost:5173","http://localhost:8000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

from fastapi import APIRouter

# Mount all routers under /api so the built React frontend works without Vite proxy
# Routes are available at BOTH /auth/... AND /api/auth/...  (backward compat)
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(crypto_router)
api_router.include_router(token_router)
api_router.include_router(workflow_router)
api_router.include_router(notification_router)
api_router.include_router(intelligence_router)
app.include_router(api_router)

# Also keep bare routes for API clients and Swagger UI
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(crypto_router)
app.include_router(token_router)
app.include_router(workflow_router)
app.include_router(notification_router)
app.include_router(intelligence_router)

@app.get("/health")
async def health():
    return {"status":"ok","version":"0.5.1","env":get_config().env}

@app.post("/signal")
async def generate_signal(req: SignalRequest, user: CurrentUser = Depends(get_current_user)):
    if not get_config().enable_ai_agents: raise HTTPException(503,"AI agents disabled")
    try:
        from alchemy.agents.graph import run_agent
        from alchemy.core.state import TradingSignal
        sig: TradingSignal = run_agent(ticker=req.ticker, market=req.market,
            broker=req.broker, price_data=req.price_data, news_headlines=req.news_headlines)
        await manager.broadcast("signal", sig.to_dict())
        return sig.to_dict()
    except Exception as e: raise HTTPException(500, str(e))

@app.get("/risk/status")
async def risk_status(user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.manager import RiskManager; return RiskManager().status()

@app.post("/risk/emergency-stop")
async def emergency_stop(user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.manager import RiskManager
    rm=RiskManager(); rm.trigger_emergency_stop(f"Manual by {user.email}")
    await manager.broadcast("risk_alert", rm.status()); return {"ok":True}

@app.delete("/risk/emergency-stop")
async def clear_stop(user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.manager import RiskManager; RiskManager().reset_emergency_stop(); return {"ok":True}

@app.post("/risk/block")
async def block(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.manager import RiskManager; RiskManager().block_ticker(body.get("ticker","")); return {"ok":True}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg  = json.loads(data)
            if msg.get("type")=="subscribe":
                await ws.send_text(json.dumps({"event":"subscribed","symbols":msg.get("symbols",[])}))
    except WebSocketDisconnect: manager.disconnect(ws)

# Serve React frontend — try multiple locations
import pathlib
_base = pathlib.Path(__file__).parent.parent.parent
_static_mounted = False
for _candidate in [_base / "static", _base / "frontend" / "dist"]:
    if _candidate.is_dir() and (_candidate / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(_candidate), html=True), name="static")
        log.info("static.mounted", path=str(_candidate))
        _static_mounted = True
        break

# If no built frontend, add helpful root redirect
if not _static_mounted:
    from fastapi.responses import HTMLResponse
    @app.get("/", include_in_schema=False)
    async def root():
        return HTMLResponse("""<!DOCTYPE html>
<html><head><title>Alchemy API</title>
<style>body{font-family:monospace;background:#0f172a;color:#e2e8f0;padding:40px;max-width:600px;margin:auto}
h1{color:#60a5fa}a{color:#34d399}code{background:#1e293b;padding:2px 6px;border-radius:4px}
.box{background:#1e293b;border:1px solid #334155;border-radius:8px;padding:20px;margin:16px 0}
</style></head><body>
<h1>🔮 Alchemy Trading Platform</h1>
<p>API is running. React frontend not built yet.</p>
<div class="box">
<b>Option 1 — Run frontend dev server (recommended):</b><br><br>
<code>cd frontend</code><br>
<code>npm install</code><br>
<code>npm run dev</code><br><br>
Then open: <a href="http://localhost:3000">http://localhost:3000</a>
</div>
<div class="box">
<b>Option 2 — Build frontend once:</b><br><br>
<code>cd frontend && npm install && npm run build</code><br>
<code>cd .. && uvicorn alchemy.api.app:app --reload --port 8000</code><br><br>
Then open: <a href="http://localhost:8000">http://localhost:8000</a>
</div>
<div class="box">
<b>API endpoints available now:</b><br><br>
<a href="/docs">📖 Swagger UI (/docs)</a><br>
<a href="/redoc">📚 ReDoc (/redoc)</a><br>
<a href="/health">💚 Health (/health)</a>
</div>
</body></html>""")
