"""
alchemy.services.trade_insights
==================================
AI-powered trade journal analysis.

Analyzes trade history to identify:
  - Win/loss patterns by time, strategy, symbol
  - Emotional trading indicators (revenge trades, FOMO)
  - Position sizing discipline
  - Risk/reward adherence
  - Streak analysis
  - Weekly/monthly performance reviews
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
log = structlog.get_logger(__name__)


def analyze_trades(trade_log: list[dict], config: dict = None) -> dict:
    """
    Comprehensive trade analysis without external AI.
    Pure statistical analysis of trade history.
    """
    if not trade_log:
        return {"status": "no_trades", "message": "No trades to analyze", "insights": []}

    # Basic stats
    total = len(trade_log)
    wins = [t for t in trade_log if t.get("net_pnl", 0) > 0]
    losses = [t for t in trade_log if t.get("net_pnl", 0) <= 0]
    win_rate = len(wins) / total * 100
    total_pnl = sum(t.get("net_pnl", 0) for t in trade_log)
    total_fees = sum(t.get("fee", 0) for t in trade_log)
    avg_win = sum(t.get("net_pnl", 0) for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.get("net_pnl", 0) for t in losses) / len(losses) if losses else 0
    profit_factor = abs(sum(t.get("net_pnl", 0) for t in wins)) / abs(sum(t.get("net_pnl", 0) for t in losses)) if losses and sum(t.get("net_pnl", 0) for t in losses) != 0 else float('inf')

    # Largest win/loss
    largest_win = max((t.get("net_pnl", 0) for t in trade_log), default=0)
    largest_loss = min((t.get("net_pnl", 0) for t in trade_log), default=0)

    # Streak analysis
    streaks = _analyze_streaks(trade_log)

    # Per-symbol breakdown
    symbol_stats = _per_symbol(trade_log)

    # Per-strategy breakdown
    strategy_stats = _per_strategy(trade_log)

    # Time analysis
    time_stats = _time_analysis(trade_log)

    # Generate insights
    insights = []

    # Win rate insight
    if win_rate >= 60:
        insights.append({"type": "positive", "icon": "🎯", "title": "Strong Win Rate",
            "message": f"Your win rate of {win_rate:.0f}% is above the 55% threshold for profitable trading."})
    elif win_rate < 40:
        insights.append({"type": "warning", "icon": "⚠️", "title": "Low Win Rate",
            "message": f"Win rate of {win_rate:.0f}% is below average. Consider tightening entry criteria or reviewing your strategy."})

    # Profit factor
    if profit_factor > 2.0:
        insights.append({"type": "positive", "icon": "💪", "title": "Excellent Profit Factor",
            "message": f"Profit factor of {profit_factor:.2f} means your wins significantly outsize your losses."})
    elif profit_factor < 1.0:
        insights.append({"type": "danger", "icon": "🚨", "title": "Negative Profit Factor",
            "message": f"Profit factor of {profit_factor:.2f} means losses exceed wins. Review position sizing and stop-loss placement."})

    # Risk/reward
    if avg_win > 0 and avg_loss < 0:
        rr = abs(avg_win / avg_loss)
        if rr >= 2.0:
            insights.append({"type": "positive", "icon": "⚖️", "title": "Good Risk:Reward",
                "message": f"Average win (${avg_win:.2f}) is {rr:.1f}x your average loss (${avg_loss:.2f})."})
        elif rr < 1.0:
            insights.append({"type": "warning", "icon": "⚖️", "title": "Poor Risk:Reward",
                "message": f"Average loss (${abs(avg_loss):.2f}) exceeds average win (${avg_win:.2f}). Widen take-profits or tighten stop-losses."})

    # Streak warnings
    if streaks["max_losing_streak"] >= 5:
        insights.append({"type": "warning", "icon": "📉", "title": "Extended Losing Streak",
            "message": f"Longest losing streak: {streaks['max_losing_streak']} trades. Consider pausing after 3 consecutive losses."})

    # Fee impact
    fee_pct = (total_fees / abs(total_pnl) * 100) if total_pnl != 0 else 0
    if fee_pct > 20:
        insights.append({"type": "warning", "icon": "💸", "title": "High Fee Impact",
            "message": f"Fees consumed {fee_pct:.0f}% of your gross P&L (${total_fees:.2f}). Consider fewer, larger trades."})

    # Best/worst symbol
    if symbol_stats:
        best = max(symbol_stats, key=lambda s: s["net_pnl"])
        worst = min(symbol_stats, key=lambda s: s["net_pnl"])
        if best["net_pnl"] > 0:
            insights.append({"type": "info", "icon": "⭐", "title": f"Best Performer: {best['symbol']}",
                "message": f"{best['trades']} trades, ${best['net_pnl']:.2f} profit, {best['win_rate']:.0f}% win rate."})
        if worst["net_pnl"] < 0:
            insights.append({"type": "info", "icon": "📊", "title": f"Needs Work: {worst['symbol']}",
                "message": f"{worst['trades']} trades, ${worst['net_pnl']:.2f} loss. Consider avoiding or adjusting strategy."})

    # Revenge trading detection
    revenge = _detect_revenge_trades(trade_log)
    if revenge > 0:
        insights.append({"type": "danger", "icon": "😤", "title": "Possible Revenge Trading",
            "message": f"Detected {revenge} cases where a trade was placed within 5 minutes of a loss. Take breaks after losses."})

    return {
        "status": "analyzed",
        "summary": {
            "total_trades": total,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "total_fees": round(total_fees, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "largest_win": round(largest_win, 2),
            "largest_loss": round(largest_loss, 2),
            "profit_factor": round(min(profit_factor, 99.99), 2),
        },
        "streaks": streaks,
        "by_symbol": symbol_stats,
        "by_strategy": strategy_stats,
        "time_analysis": time_stats,
        "insights": insights,
        "insight_count": len(insights),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _analyze_streaks(trades: list[dict]) -> dict:
    """Calculate win/loss streaks."""
    max_win = max_loss = current_win = current_loss = 0
    for t in trades:
        if t.get("net_pnl", 0) > 0:
            current_win += 1
            current_loss = 0
            max_win = max(max_win, current_win)
        else:
            current_loss += 1
            current_win = 0
            max_loss = max(max_loss, current_loss)
    return {
        "max_winning_streak": max_win,
        "max_losing_streak": max_loss,
        "current_winning_streak": current_win,
        "current_losing_streak": current_loss,
    }


def _per_symbol(trades: list[dict]) -> list[dict]:
    """Breakdown by trading symbol."""
    symbols = {}
    for t in trades:
        sym = t.get("symbol", "UNKNOWN")
        if sym not in symbols:
            symbols[sym] = {"symbol": sym, "trades": 0, "wins": 0, "net_pnl": 0, "fees": 0}
        symbols[sym]["trades"] += 1
        symbols[sym]["net_pnl"] += t.get("net_pnl", 0)
        symbols[sym]["fees"] += t.get("fee", 0)
        if t.get("net_pnl", 0) > 0:
            symbols[sym]["wins"] += 1

    result = []
    for s in symbols.values():
        s["win_rate"] = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] else 0
        s["net_pnl"] = round(s["net_pnl"], 2)
        s["fees"] = round(s["fees"], 2)
        result.append(s)
    return sorted(result, key=lambda x: x["net_pnl"], reverse=True)


def _per_strategy(trades: list[dict]) -> list[dict]:
    """Breakdown by strategy."""
    strategies = {}
    for t in trades:
        strat = t.get("strategy", "manual") or "manual"
        if strat not in strategies:
            strategies[strat] = {"strategy": strat, "trades": 0, "wins": 0, "net_pnl": 0}
        strategies[strat]["trades"] += 1
        strategies[strat]["net_pnl"] += t.get("net_pnl", 0)
        if t.get("net_pnl", 0) > 0:
            strategies[strat]["wins"] += 1

    result = []
    for s in strategies.values():
        s["win_rate"] = round(s["wins"] / s["trades"] * 100, 1) if s["trades"] else 0
        s["net_pnl"] = round(s["net_pnl"], 2)
        result.append(s)
    return sorted(result, key=lambda x: x["net_pnl"], reverse=True)


def _time_analysis(trades: list[dict]) -> dict:
    """Analyze trading patterns by time."""
    hours = {}
    days = {}
    for t in trades:
        ts = t.get("closed_at", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            h = dt.hour
            d = dt.strftime("%A")
            hours[h] = hours.get(h, 0) + t.get("net_pnl", 0)
            days[d] = days.get(d, 0) + t.get("net_pnl", 0)
        except Exception:
            pass

    best_hour = max(hours, key=hours.get) if hours else None
    worst_hour = min(hours, key=hours.get) if hours else None
    best_day = max(days, key=days.get) if days else None

    return {
        "best_hour": f"{best_hour}:00 UTC" if best_hour is not None else "N/A",
        "worst_hour": f"{worst_hour}:00 UTC" if worst_hour is not None else "N/A",
        "best_day": best_day or "N/A",
        "pnl_by_hour": {str(k): round(v, 2) for k, v in sorted(hours.items())},
        "pnl_by_day": {k: round(v, 2) for k, v in days.items()},
    }


def _detect_revenge_trades(trades: list[dict]) -> int:
    """Detect potential revenge trading (rapid entry after a loss)."""
    count = 0
    for i in range(1, len(trades)):
        prev = trades[i-1]
        curr = trades[i]
        if prev.get("net_pnl", 0) < 0:
            try:
                t1 = datetime.fromisoformat(prev.get("closed_at", "").replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(curr.get("closed_at", "").replace("Z", "+00:00"))
                if (t2 - t1).total_seconds() < 300:  # Within 5 minutes
                    count += 1
            except Exception:
                pass
    return count
