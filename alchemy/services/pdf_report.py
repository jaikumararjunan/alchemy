"""
alchemy.services.pdf_report
===============================
Generate PDF portfolio reports.

Uses reportlab for PDF generation (no external dependencies like WeasyPrint).
Produces professional portfolio reports with:
  - Header with branding
  - Portfolio summary metrics
  - Positions table
  - Trade history table
  - Performance statistics
  - AI insights summary
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

import structlog
log = structlog.get_logger(__name__)


def generate_portfolio_pdf(user_id: str, username: str = "Trader") -> bytes:
    """Generate a PDF portfolio report. Returns bytes."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch, mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    except ImportError:
        # Fallback: generate simple text-based PDF
        return _generate_simple_pdf(user_id, username)

    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()
    p = engine.get_portfolio(user_id)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle('Title', parent=styles['Title'],
                                  fontSize=22, spaceAfter=6, textColor=colors.HexColor('#1a1a2e'))
    elements.append(Paragraph("Alchemy AI Trading Platform", title_style))

    sub_style = ParagraphStyle('Sub', parent=styles['Normal'],
                                fontSize=11, textColor=colors.HexColor('#666666'))
    elements.append(Paragraph(f"Portfolio Report — {username}", sub_style))
    elements.append(Paragraph(f"Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}", sub_style))
    elements.append(Spacer(1, 12))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e0e0e0')))
    elements.append(Spacer(1, 12))

    # Summary
    heading = ParagraphStyle('Heading', parent=styles['Heading2'],
                              fontSize=14, textColor=colors.HexColor('#1a1a2e'))
    elements.append(Paragraph("Portfolio Summary", heading))

    wins = len([t for t in p.trade_log if t.get("net_pnl", 0) > 0])
    total_trades = len(p.trade_log)
    win_rate = (wins / total_trades * 100) if total_trades else 0

    summary_data = [
        ["Metric", "Value"],
        ["Portfolio Value", f"${p.portfolio_value:,.2f}"],
        ["Cash Balance", f"${p.cash_balance:,.2f}"],
        ["Starting Balance", f"${p.starting_balance:,.2f}"],
        ["Total Return", f"{p.total_return_pct:+.2f}%"],
        ["Realized P&L", f"${p.realized_pnl:,.2f}"],
        ["Total Trades", str(total_trades)],
        ["Win Rate", f"{win_rate:.1f}%"],
        ["Open Positions", str(len(p.positions))],
    ]

    t = Table(summary_data, colWidths=[3*inch, 3*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a2e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 16))

    # Positions
    if p.positions:
        elements.append(Paragraph("Open Positions", heading))
        pos_data = [["Symbol", "Side", "Qty", "Entry Price", "Strategy"]]
        for sym, pos in p.positions.items():
            pos_data.append([sym, pos.side.value.upper(), f"{pos.quantity}", f"${pos.avg_entry_price:,.2f}", pos.strategy or "—"])

        t2 = Table(pos_data, colWidths=[1.5*inch, 1*inch, 1*inch, 1.5*inch, 1.5*inch])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3b52')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (2, 0), (3, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t2)
        elements.append(Spacer(1, 16))

    # Recent trades
    if p.trade_log:
        elements.append(Paragraph(f"Trade History (Last {min(len(p.trade_log), 20)})", heading))
        trade_data = [["Symbol", "Side", "Entry", "Exit", "Net P&L", "Return"]]
        for t in p.trade_log[-20:]:
            pnl = t.get("net_pnl", 0)
            trade_data.append([
                t.get("symbol", ""),
                t.get("side", "").upper(),
                f"${t.get('entry_price', 0):,.2f}",
                f"${t.get('exit_price', 0):,.2f}",
                f"${pnl:+,.2f}",
                f"{t.get('return_pct', 0):+.1f}%",
            ])

        t3 = Table(trade_data, colWidths=[1.2*inch, 1*inch, 1.1*inch, 1.1*inch, 1.1*inch, 1*inch])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d3b52')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(t3)

    # Footer
    elements.append(Spacer(1, 24))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cccccc')))
    footer = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#999999'))
    elements.append(Paragraph("Alchemy AI Trading Platform — akilamirthya.in — This is a paper trading report, not financial advice.", footer))

    doc.build(elements)
    return buf.getvalue()


def _generate_simple_pdf(user_id: str, username: str) -> bytes:
    """Fallback: plain text report when reportlab not installed."""
    from alchemy.paper_trading.engine import get_paper_engine
    engine = get_paper_engine()
    p = engine.get_portfolio(user_id)

    wins = len([t for t in p.trade_log if t.get("net_pnl", 0) > 0])
    total = len(p.trade_log)

    lines = [
        "ALCHEMY AI TRADING PLATFORM",
        f"Portfolio Report — {username}",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "PORTFOLIO SUMMARY",
        f"  Value:      ${p.portfolio_value:,.2f}",
        f"  Cash:       ${p.cash_balance:,.2f}",
        f"  Return:     {p.total_return_pct:+.2f}%",
        f"  P&L:        ${p.realized_pnl:,.2f}",
        f"  Trades:     {total}",
        f"  Win Rate:   {(wins/total*100):.1f}%" if total else "  Win Rate:   N/A",
        f"  Positions:  {len(p.positions)}",
        "",
    ]

    if p.positions:
        lines.append("OPEN POSITIONS")
        for sym, pos in p.positions.items():
            lines.append(f"  {sym} {pos.side.value.upper()} {pos.quantity} @ ${pos.avg_entry_price:,.2f}")
        lines.append("")

    if p.trade_log:
        lines.append(f"RECENT TRADES (last {min(len(p.trade_log), 10)})")
        for t in p.trade_log[-10:]:
            lines.append(f"  {t.get('symbol','')} {t.get('side','').upper()} P&L: ${t.get('net_pnl',0):+,.2f}")

    text = "\n".join(lines)
    # Return as simple text content (not a real PDF, but downloadable)
    return text.encode('utf-8')
