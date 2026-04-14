"""
alchemy.services.weekly_review
=================================
AI-powered weekly trade review generator.

Analyzes the past week's trading activity and generates a structured
review with performance metrics, pattern identification, and
actionable improvement suggestions.

No external AI API needed — uses statistical analysis + rule-based insights.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import structlog
log = structlog.get_logger(__name__)


def generate_weekly_review(user_id: str, weeks_back: int = 1) -> dict:
    """
    Generate a weekly trade review for a user.
    Returns structured review with metrics, insights, and action items.
    """
    from alchemy.paper_trading.engine import get_paper_engine
    from alchemy.services.trade_insights import analyze_trades

    engine = get_paper_engine()
    p = engine.get_portfolio(user_id)

    # Filter trades from the target week
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7 * weeks_back)
    week_end = week_start + timedelta(days=7)

    week_trades = []
    for t in p.trade_log:
        ts = t.get("closed_at", "")
        if ts:
            try:
                trade_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if week_start <= trade_time <= week_end:
                    week_trades.append(t)
            except Exception:
                pass

    if not week_trades:
        return {
            "status": "no_trades",
            "period": f"{week_start.strftime('%b %d')} — {week_end.strftime('%b %d, %Y')}",
            "message": "No trades closed this week.",
            "sections": [],
        }

    # Analyze this week's trades
    analysis = analyze_trades(week_trades)
    summary = analysis.get("summary", {})

    # Build review sections
    sections = []

    # 1. Executive Summary
    pnl = summary.get("total_pnl", 0)
    pnl_emoji = "📈" if pnl > 0 else "📉" if pnl < 0 else "➖"
    grade = _compute_grade(summary)

    sections.append({
        "title": "Weekly Summary",
        "icon": pnl_emoji,
        "content": f"This week you closed {summary['total_trades']} trades with a net P&L of ${pnl:+,.2f}. "
                   f"Win rate: {summary['win_rate']:.0f}%. "
                   f"Profit factor: {summary['profit_factor']:.2f}. "
                   f"Overall grade: **{grade}**.",
    })

    # 2. Best and Worst
    if week_trades:
        best = max(week_trades, key=lambda t: t.get("net_pnl", 0))
        worst = min(week_trades, key=lambda t: t.get("net_pnl", 0))
        sections.append({
            "title": "Highlights",
            "icon": "⭐",
            "content": f"Best trade: {best.get('symbol', '')} ({best.get('side', '')}) → ${best.get('net_pnl', 0):+,.2f}. "
                       f"Worst trade: {worst.get('symbol', '')} ({worst.get('side', '')}) → ${worst.get('net_pnl', 0):+,.2f}.",
        })

    # 3. Pattern Analysis
    by_symbol = analysis.get("by_symbol", [])
    if by_symbol:
        best_sym = by_symbol[0] if by_symbol[0]["net_pnl"] > 0 else None
        worst_sym = by_symbol[-1] if by_symbol[-1]["net_pnl"] < 0 else None
        pattern_text = ""
        if best_sym:
            pattern_text += f"Strongest symbol: {best_sym['symbol']} ({best_sym['trades']} trades, ${best_sym['net_pnl']:+,.2f}). "
        if worst_sym:
            pattern_text += f"Weakest symbol: {worst_sym['symbol']} ({worst_sym['trades']} trades, ${worst_sym['net_pnl']:+,.2f}). "
        if pattern_text:
            sections.append({"title": "Symbol Patterns", "icon": "📊", "content": pattern_text})

    # 4. Time Analysis
    time_stats = analysis.get("time_analysis", {})
    if time_stats.get("best_hour") != "N/A":
        sections.append({
            "title": "Timing",
            "icon": "🕐",
            "content": f"Most profitable hour: {time_stats['best_hour']}. "
                       f"Least profitable: {time_stats['worst_hour']}. "
                       f"Best day: {time_stats.get('best_day', 'N/A')}.",
        })

    # 5. Improvement Suggestions
    suggestions = _generate_suggestions(summary, analysis, week_trades)
    if suggestions:
        sections.append({
            "title": "Action Items for Next Week",
            "icon": "🎯",
            "items": suggestions,
        })

    # 6. Streaks
    streaks = analysis.get("streaks", {})
    if streaks.get("max_winning_streak", 0) >= 3 or streaks.get("max_losing_streak", 0) >= 3:
        sections.append({
            "title": "Streaks",
            "icon": "🔥",
            "content": f"Max win streak: {streaks['max_winning_streak']}. "
                       f"Max loss streak: {streaks['max_losing_streak']}.",
        })

    return {
        "status": "generated",
        "period": f"{week_start.strftime('%b %d')} — {week_end.strftime('%b %d, %Y')}",
        "grade": grade,
        "summary": summary,
        "sections": sections,
        "insights": analysis.get("insights", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _compute_grade(summary: dict) -> str:
    """Compute a letter grade A-F based on trading performance."""
    score = 0
    wr = summary.get("win_rate", 0)
    pf = summary.get("profit_factor", 0)
    pnl = summary.get("total_pnl", 0)

    if wr >= 65: score += 3
    elif wr >= 55: score += 2
    elif wr >= 45: score += 1

    if pf >= 2.0: score += 3
    elif pf >= 1.5: score += 2
    elif pf >= 1.0: score += 1

    if pnl > 0: score += 2
    elif pnl == 0: score += 1

    grades = {8: "A+", 7: "A", 6: "A-", 5: "B+", 4: "B", 3: "B-", 2: "C+", 1: "C", 0: "D"}
    return grades.get(min(score, 8), "D")


def _generate_suggestions(summary: dict, analysis: dict, trades: list) -> list[str]:
    """Generate actionable improvement suggestions."""
    suggestions = []

    if summary.get("win_rate", 0) < 50:
        suggestions.append("Review entry criteria — consider waiting for stronger confirmation signals before entering")

    if summary.get("profit_factor", 0) < 1.0:
        suggestions.append("Tighten stop-losses or widen take-profits — your losses currently exceed your wins")

    avg_win = summary.get("avg_win", 0)
    avg_loss = abs(summary.get("avg_loss", 0))
    if avg_loss > 0 and avg_win / avg_loss < 1.5:
        suggestions.append(f"Improve risk:reward — avg win (${avg_win:.0f}) should be at least 1.5x avg loss (${avg_loss:.0f})")

    fee_impact = summary.get("total_fees", 0)
    if fee_impact > abs(summary.get("total_pnl", 1)) * 0.15:
        suggestions.append("Reduce trading frequency — fees are eating into your profits significantly")

    if summary.get("total_trades", 0) > 10:
        suggestions.append("Consider specializing — focus on your 2-3 best-performing symbols")

    if not suggestions:
        suggestions.append("Great week! Maintain discipline and keep journaling your trades")

    return suggestions[:5]
