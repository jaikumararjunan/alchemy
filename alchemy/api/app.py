"""
alchemy.api.app  v0.6.0
=======================
FastAPI application — properly structured so StaticFiles NEVER
catches WebSocket connections.

Architecture:
  - All API routes registered first
  - WebSocket routes registered before any Mount
  - Static assets served at /assets  (NOT at /)
  - SPA catch-all via /{full_path:path} GET route  (returns index.html)
  - This guarantees WS connections always hit the @app.websocket handler
"""
from __future__ import annotations

import json
import os
import pathlib
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from alchemy.auth.middleware import (
    SecurityHeadersMiddleware, get_current_user, CurrentUser,
)
from alchemy.api.metrics     import router as metrics_router, MetricsMiddleware
from alchemy.api.audit_routes  import router as audit_router
from alchemy.core.config import get_config

log = structlog.get_logger(__name__)


# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active = [w for w in self.active if w is not ws]

    async def broadcast(self, event: str, data: dict):
        msg = json.dumps({"event": event, **data})
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ── Startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("alchemy.startup", version="0.7.0")

    # 1. Database tables + admin seed
    try:
        from alchemy.api.database import create_tables, get_session_factory
        from alchemy.auth.service import AuthService
        from alchemy.auth.security import hash_password
        from alchemy.users.models import User, UserStatus
        from sqlalchemy import select

        await create_tables()
        log.info("db.tables_ready")

        admin_email = os.environ.get("ADMIN_EMAIL", "admin@alchemy.in")
        admin_pwd   = os.environ.get("ADMIN_PASSWORD", "Alchemy#Admin!2024")

        # Ensure admin password meets policy — append special chars if needed
        import re as _re
        if not _re.search(r"[!@#$%^&*]", admin_pwd):
            admin_pwd = admin_pwd + "#Alchemy1"
        if not _re.search(r"[A-Z]", admin_pwd):
            admin_pwd = "A" + admin_pwd
        if not _re.search(r"\d", admin_pwd):
            admin_pwd = admin_pwd + "1"

        async with get_session_factory()() as db:
            row = await db.execute(select(User).where(User.email == admin_email))
            existing = row.scalar_one_or_none()
            if existing:
                # Ensure admin is active with correct role/subscription
                changed = False
                if existing.status != UserStatus.ACTIVE.value:
                    existing.status = UserStatus.ACTIVE.value; changed = True
                if not existing.email_verified:
                    existing.email_verified = True; changed = True
                if existing.role != "super_admin":
                    existing.role = "super_admin"; changed = True
                if getattr(existing, "subscription", "free") != "enterprise":
                    existing.subscription = "enterprise"; changed = True
                if changed:
                    await db.commit()
                log.info("db.admin_exists", email=admin_email)
            else:
                try:
                    svc = AuthService()
                    user = await svc.signup(db, email=admin_email, username="admin",
                        full_name="Super Admin", password=admin_pwd)
                    user.role = "super_admin"
                    user.status = UserStatus.ACTIVE.value
                    user.email_verified = True
                    user.subscription = "enterprise"
                    await db.commit()
                    log.info("db.admin_created", email=admin_email, pwd_hint=admin_pwd[:4]+"***")
                except Exception as seed_err:
                    await db.rollback()
                    log.info("db.admin_seed_skipped", reason=str(seed_err)[:60])
    except Exception as e:
        log.warning("db.init_failed", error=str(e))

    # 2. Token auto-refresh
    try:
        from alchemy.tokens.manager import get_token_manager
        get_token_manager().start_auto_refresh()
    except Exception:
        pass

    # 3. Notification dispatcher
    try:
        from alchemy.notifications.dispatcher import get_dispatcher
        await get_dispatcher().start()
    except Exception as e:
        log.warning("notification.start_failed", error=str(e))

    # 4. Crash recovery — reconcile local state with exchanges
    try:
        from alchemy.risk.reconciler import reconcile_all_exchanges
        report = await reconcile_all_exchanges(auto_fix=False)
        if not report.clean:
            log.warning("reconciler.discrepancies_found",
                        count=len(report.discrepancies))
        else:
            log.info("reconciler.clean_startup")
    except Exception as e:
        log.warning("reconciler.startup_failed", error=str(e))

    yield  # ← app runs here

    # Shutdown
    try:
        from alchemy.notifications.dispatcher import get_dispatcher
        await get_dispatcher().stop()
    except Exception:
        pass
    log.info("alchemy.shutdown")


# ── App creation ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Alchemy Trading Platform",
    version="0.7.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware (order matters: added last = runs first)
app.add_middleware(MetricsMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────

from alchemy.api.auth_routes         import router as auth_router
from alchemy.api.admin_routes        import router as admin_router
from alchemy.api.crypto_routes       import router as crypto_router
from alchemy.api.token_routes        import token_router, workflow_router
from alchemy.api.notification_routes import router as notification_router
from alchemy.api.intelligence_routes import router as intelligence_router
from alchemy.api.otp_routes         import router as otp_router
from alchemy.api.autonomous_routes  import router as autonomous_router
from fastapi import APIRouter

# /api/* prefix  (what the built React frontend calls)
api = APIRouter(prefix="/api")
api.include_router(auth_router)
api.include_router(admin_router)
api.include_router(crypto_router)
api.include_router(token_router)
api.include_router(workflow_router)
api.include_router(notification_router)
api.include_router(intelligence_router)
api.include_router(otp_router)
api.include_router(autonomous_router)
app.include_router(metrics_router)
api.include_router(audit_router)
app.include_router(api)

# bare prefix  (Swagger UI + backward compat)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(crypto_router)
app.include_router(token_router)
app.include_router(workflow_router)
app.include_router(notification_router)
app.include_router(intelligence_router)
app.include_router(autonomous_router)


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.get("/health",      tags=["core"])
@app.get("/api/health",  tags=["core"])
async def health():
    return {"status": "ok", "version": "0.7.0", "env": get_config().env}


@app.get("/risk/status",      tags=["risk"])
@app.get("/api/risk/status",  tags=["risk"])
async def risk_status(user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.manager import RiskManager
    return RiskManager().status()


@app.post("/risk/emergency-stop",     tags=["risk"])
@app.post("/api/risk/emergency-stop", tags=["risk"])
async def emergency_stop(user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.kill_switch import activate_kill_switch
    result = await activate_kill_switch(
        triggered_by=user.email,
        reason="Manual kill switch via API",
        close_positions=True,
    )
    await manager.broadcast("risk_alert", result.to_dict())
    return result.to_dict()


@app.delete("/risk/emergency-stop",     tags=["risk"])
@app.delete("/api/risk/emergency-stop", tags=["risk"])
async def clear_stop(user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.manager import RiskManager
    RiskManager().reset_emergency_stop()
    return {"ok": True}


@app.post("/risk/block",     tags=["risk"])
@app.post("/api/risk/block", tags=["risk"])
async def block(body: dict, user: CurrentUser = Depends(get_current_user)):
    from alchemy.risk.manager import RiskManager
    RiskManager().block_ticker(body.get("ticker", ""))
    return {"ok": True}


@app.post("/signal",     tags=["signal"])
@app.post("/api/signal", tags=["signal"])
async def generate_signal(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    if not get_config().enable_ai_agents:
        raise HTTPException(503, "AI agents disabled — set ENABLE_AI_AGENTS=true")
    try:
        from alchemy.agents.graph import run_agent
        from alchemy.core.state import TradingSignal
        sig: TradingSignal = run_agent(
            ticker=body.get("ticker", ""),
            market=body.get("market", "NSE"),
            broker=body.get("broker", "PAPER"),
            price_data=body.get("price_data", {}),
            news_headlines=body.get("news_headlines", []),
        )
        await manager.broadcast("signal", sig.to_dict())
        return sig.to_dict()
    except Exception as e:
        raise HTTPException(500, str(e))


# ── WebSocket  ────────────────────────────────────────────────────────────────
# CRITICAL: Register BEFORE any app.mount() calls.
# StaticFiles mounted at "/" cannot handle WebSocket scope type.
# By registering here (before mounts), Starlette's router will match
# these WebSocket routes first and never reach the StaticFiles mount.

async def _ws_handler(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg  = json.loads(data)
            if msg.get("type") == "subscribe":
                await ws.send_text(json.dumps({
                    "event": "subscribed",
                    "symbols": msg.get("symbols", []),
                }))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await _ws_handler(ws)


@app.websocket("/api/ws")
async def ws_endpoint_api(ws: WebSocket):
    await _ws_handler(ws)


# ── Static file serving ───────────────────────────────────────────────────────
# Serve React SPA WITHOUT mounting at "/" (which would break WebSocket).
#
# Strategy:
#   /assets/*  → StaticFiles (JS bundles, CSS, images)
#   /           → index.html  (SPA entry point)
#   /{any}     → index.html  (SPA client-side routing)

def _find_frontend_dist() -> pathlib.Path | None:
    base = pathlib.Path(__file__).parent.parent.parent
    for candidate in [base / "static", base / "frontend" / "dist"]:
        if candidate.is_dir() and (candidate / "index.html").exists():
            return candidate
    return None


_dist = _find_frontend_dist()

if _dist:
    # Serve /assets/... as static files — this is HTTP only, no WS conflict
    _assets_dir = _dist / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")
        log.info("static.assets_mounted", path=str(_assets_dir))

    # SPA: serve index.html for ALL unmatched GET routes.
    # FastAPI already routes /api/* before reaching this catch-all,
    # so any path that lands here is a client-side React route → serve index.html.
    @app.get("/",                 include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = ""):
        index = _dist / "index.html"
        if not index.exists():
            return JSONResponse({"detail": "Frontend not built — run: cd frontend && npm run build"}, status_code=503)
        return FileResponse(str(index))

    log.info("static.spa_ready", dist=str(_dist))

else:
    # No build — helpful landing page
    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return JSONResponse({
            "message": "Alchemy API running. Frontend not built.",
            "fix": "cd frontend && npm install && npm run build",
            "docs": "http://localhost:8000/docs",
        })
