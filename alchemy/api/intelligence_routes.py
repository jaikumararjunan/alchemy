"""
alchemy.api.intelligence_routes
================================
REST API for the intelligence, strategy, EI, and analytics systems.
"""
from __future__ import annotations
import re
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from alchemy.auth.middleware import CurrentUser, get_current_user

# Allowlist of hostnames accepted for video transcript requests
_ALLOWED_VIDEO_HOSTS = re.compile(
    r"^(www\.)?(youtube\.com|youtu\.be|m\.youtube\.com)$", re.IGNORECASE
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])

# ── Market Intelligence ──────────────────────────────────────────────────────

@router.get("/signals")
async def get_signals(
    limit:    int  = Query(50, ge=1, le=200),
    geo_only: bool = False,
    user: CurrentUser = Depends(get_current_user),
):
    """Get latest market intelligence signals."""
    try:
        from alchemy.intelligence.crawlers.market_crawler import get_orchestrator
        return {"signals": get_orchestrator().get_latest_signals(limit, geo_only)}
    except Exception as e:
        return {"signals": [], "error": str(e)}


@router.get("/market-view")
async def market_view(user: CurrentUser = Depends(get_current_user)):
    """Synthesised market view from all recent signals."""
    try:
        from alchemy.intelligence.crawlers.market_crawler import get_orchestrator
        return get_orchestrator().synthesise_market_view()
    except Exception as e:
        return {"market_bias": "neutral", "error": str(e)}


@router.post("/crawl-now")
async def trigger_crawl(
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Trigger an immediate news crawl."""
    async def _crawl():
        from alchemy.intelligence.crawlers.market_crawler import get_orchestrator
        orch = get_orchestrator()
        articles = await orch.news_crawler.crawl_all()
        signals  = await orch._process_articles(articles)
        await orch._store_signals(signals)

    background_tasks.add_task(_crawl)
    return {"ok": True, "message": "Crawl triggered in background"}


@router.post("/video")
async def process_video(
    body: dict,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Submit a YouTube URL for analysis."""
    url = body.get("url","")
    if not url: raise HTTPException(400, "url required")

    # Validate URL to prevent SSRF — only YouTube links are accepted
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not _ALLOWED_VIDEO_HOSTS.match(parsed.netloc or ""):
            raise HTTPException(400, "Only YouTube URLs are accepted (youtube.com / youtu.be)")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Invalid URL format")

    async def _process(video_url: str):
        from alchemy.intelligence.crawlers.market_crawler import get_orchestrator
        orch = get_orchestrator()
        transcript = await orch.video_crawler.get_transcript(video_url)
        if transcript:
            title  = body.get("title","Market Video")
            result = await orch.video_crawler.summarise_with_llm(title, transcript)
            from alchemy.analytics_db.store import get_analytics_db
            import hashlib
            vid_id = hashlib.md5(video_url.encode()).hexdigest()[:12]
            get_analytics_db().save_video_summary(vid_id, {**result, "url": video_url, "title": title})

    background_tasks.add_task(_process, url)
    return {"ok": True, "message": f"Video {url[:50]} queued for processing"}


@router.get("/video-summaries")
async def get_video_summaries(
    limit: int = Query(10),
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics_db.store import get_analytics_db
    db = get_analytics_db()
    with db._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM video_summaries ORDER BY processed_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"summaries": [dict(r) for r in rows]}


# ── Emotional Intelligence ───────────────────────────────────────────────────

@router.get("/emotional-state")
async def emotional_state(user: CurrentUser = Depends(get_current_user)):
    """Current market emotional intelligence reading."""
    try:
        from alchemy.intelligence.emotion.ei_engine import get_ei_engine
        state = get_ei_engine().current_state()
        guidance = get_ei_engine().get_strategy_guidance()
        return {"state": state, "guidance": guidance}
    except Exception as e:
        return {"state": None, "error": str(e)}


@router.post("/emotional-state/compute")
async def compute_ei(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    """Compute emotional state from supplied price data."""
    closes  = body.get("closes", [])
    volumes = body.get("volumes", [])
    news_score   = body.get("news_score", 50.0)
    social_score = body.get("social_score", 50.0)

    from alchemy.intelligence.emotion.ei_engine import get_ei_engine
    from alchemy.analytics_db.store import get_analytics_db

    ei  = get_ei_engine()
    state = ei.compute_from_price_data(closes, volumes, news_score, social_score)
    # Persist
    get_analytics_db().save_ei_state(user.user_id, state.to_dict())
    guidance = ei.get_strategy_guidance()
    return {"state": state.to_dict(), "guidance": guidance}


@router.get("/emotional-history")
async def emotional_history(
    limit: int = Query(30),
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics_db.store import get_analytics_db
    return {"history": get_analytics_db().get_ei_history(user.user_id, limit)}


# ── Strategy Engine ──────────────────────────────────────────────────────────

@router.post("/strategies/generate")
async def generate_trade_ideas(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate trade ideas from price data + intelligence context."""
    from alchemy.trading.strategies.engine import get_strategy_orchestrator
    from alchemy.intelligence.crawlers.market_crawler import get_orchestrator
    from alchemy.intelligence.emotion.ei_engine import get_ei_engine

    symbols    = body.get("symbols", ["NIFTY50","RELIANCE","HDFC","BTCUSD"])
    price_data = body.get("price_data", {})  # {symbol: {closes:[],highs:[],lows:[],volumes:[]}}

    # Get market context
    orch          = get_orchestrator()
    market_view   = orch.synthesise_market_view()
    market_bias   = market_view.get("market_bias","neutral")
    signals       = orch.get_latest_signals(20)

    # Get EI score
    ei_engine     = get_ei_engine()
    ei_state      = ei_engine.current_state()
    ei_score      = (ei_state.get("fear_greed_index",50)/100) if ei_state else 0.5

    # Generate ideas
    orchestrator  = get_strategy_orchestrator()
    ideas         = await orchestrator.generate_ideas(
        symbols=symbols, price_data=price_data,
        market_bias=market_bias, emotional_score=ei_score,
        intelligence_signals=signals,
    )

    return {
        "ideas": [
            {
                "id":               idea.id,
                "strategy":         idea.strategy.value,
                "symbol":           idea.symbol,
                "direction":        idea.direction.value,
                "entry_price":      idea.entry_price,
                "stop_loss":        idea.stop_loss,
                "take_profit_1":    idea.take_profit_1,
                "take_profit_2":    idea.take_profit_2,
                "take_profit_3":    idea.take_profit_3,
                "position_size_pct":idea.position_size_pct,
                "timeframe":        idea.timeframe,
                "confidence":       round(idea.confidence,2),
                "risk_reward":      idea.risk_reward,
                "reasoning":        idea.reasoning,
                "emotional_score":  idea.emotional_score,
            }
            for idea in ideas
        ],
        "market_bias": market_bias,
        "fear_greed":  round(ei_score*100,1),
        "signal_count":len(signals),
    }


# ── Analytics ────────────────────────────────────────────────────────────────

@router.get("/analytics/trades")
async def user_trades(
    limit:    int            = Query(100),
    symbol:   Optional[str]  = None,
    strategy: Optional[str]  = None,
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics_db.store import get_analytics_db
    return {"trades": get_analytics_db().get_user_trades(user.user_id, limit, symbol, strategy)}


@router.get("/analytics/pnl-summary")
async def pnl_summary(
    days: int = Query(30),
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics_db.store import get_analytics_db
    return get_analytics_db().get_user_pnl_summary(user.user_id, days)


@router.get("/analytics/strategy-performance")
async def strategy_performance(
    months: int = Query(3),
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics_db.store import get_analytics_db
    return {"performance": get_analytics_db().get_strategy_performance(user.user_id, months)}


@router.post("/analytics/record-trade")
async def record_trade(
    body: dict,
    user: CurrentUser = Depends(get_current_user),
):
    from alchemy.analytics_db.store import get_analytics_db
    from alchemy.intelligence.emotion.ei_engine import get_ei_engine

    body["user_id"] = user.user_id

    # Link current EI state
    ei = get_ei_engine().current_state()
    if ei:
        body["fear_greed_index"]  = ei.get("fear_greed_index", 50)
        body["emotional_regime"]  = ei.get("regime","neutral")

    trade_id = get_analytics_db().record_trade(body)

    # Record outcome in EI engine for vector DB learning
    if body.get("closed_at") and body.get("pnl") is not None:
        get_ei_engine().record_trade_outcome(
            trade_id=trade_id, user_id=user.user_id,
            strategy=body.get("strategy",""), symbol=body.get("symbol",""),
            direction=body.get("direction",""), pnl=body.get("pnl",0),
            pnl_pct=body.get("pnl_pct",0),
        )
    return {"trade_id": trade_id, "ok": True}


@router.get("/analytics/similar-states")
async def similar_emotional_states(
    user: CurrentUser = Depends(get_current_user),
):
    """Find historical trades in similar emotional states using vector DB."""
    from alchemy.intelligence.emotion.ei_engine import get_ei_engine
    ei = get_ei_engine()
    state = ei._history[-1] if ei._history else None
    if not state:
        return {"similar": [], "guidance": {}}
    similar  = ei.vector_store.find_similar(state, n_results=5)
    guidance = ei.get_strategy_guidance()
    return {"similar": similar, "guidance": guidance, "current_regime": state.regime}
