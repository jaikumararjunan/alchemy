"""
Portfolio Manager - tracks P&L, positions, equity curve, and trade history.
Provides real-time performance metrics for dashboard display.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Dict, Optional


@dataclass
class EquityPoint:
    timestamp: str
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    drawdown_pct: float


@dataclass
class TradeLog:
    id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    contracts: int
    realized_pnl: float
    unrealized_pnl: float
    status: str  # "open", "closed", "stopped_out", "take_profit"
    entry_time: str
    exit_time: Optional[str]
    emotion_score: float
    ai_confidence: float
    stop_loss: float
    take_profit: float
    reasoning: str


class PortfolioManager:
    """
    Tracks portfolio performance, equity curve, and trade history.
    Powers the dashboard P&L chart and position table.
    """

    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance
        self.peak_equity = initial_balance
        self._equity_curve: List[EquityPoint] = []
        self._trade_log: List[TradeLog] = []
        self._realized_pnl: float = 0.0
        self._daily_pnl: Dict[str, float] = {}
        self._trade_counter = 0

    def update_equity(self, balance: float, unrealized_pnl: float = 0.0):
        equity = balance + unrealized_pnl
        if equity > self.peak_equity:
            self.peak_equity = equity
        drawdown = (
            (self.peak_equity - equity) / self.peak_equity * 100
            if self.peak_equity > 0
            else 0
        )
        point = EquityPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            equity=round(equity, 2),
            unrealized_pnl=round(unrealized_pnl, 2),
            realized_pnl=round(self._realized_pnl, 2),
            drawdown_pct=round(drawdown, 3),
        )
        self._equity_curve.append(point)
        if len(self._equity_curve) > 2000:
            self._equity_curve = self._equity_curve[-2000:]

        today = datetime.now(timezone.utc).date().isoformat()
        if today not in self._daily_pnl:
            self._daily_pnl[today] = 0.0

    def open_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        contracts: int,
        stop_loss: float,
        take_profit: float,
        emotion_score: float,
        ai_confidence: float,
        reasoning: str,
    ) -> str:
        self._trade_counter += 1
        trade_id = f"T{self._trade_counter:04d}"
        trade = TradeLog(
            id=trade_id,
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=None,
            contracts=contracts,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            status="open",
            entry_time=datetime.now(timezone.utc).isoformat(),
            exit_time=None,
            emotion_score=emotion_score,
            ai_confidence=ai_confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reasoning=reasoning,
        )
        self._trade_log.insert(0, trade)
        return trade_id

    def close_trade(self, trade_id: str, exit_price: float, status: str = "closed"):
        for trade in self._trade_log:
            if trade.id == trade_id and trade.status == "open":
                direction = 1 if trade.side == "buy" else -1
                pnl = direction * (exit_price - trade.entry_price) * trade.contracts
                trade.exit_price = exit_price
                trade.realized_pnl = round(pnl, 2)
                trade.status = status
                trade.exit_time = datetime.now(timezone.utc).isoformat()
                self._realized_pnl += pnl
                today = datetime.now(timezone.utc).date().isoformat()
                self._daily_pnl[today] = self._daily_pnl.get(today, 0) + pnl
                break

    def update_unrealized(self, trade_id: str, current_price: float):
        for trade in self._trade_log:
            if trade.id == trade_id and trade.status == "open":
                direction = 1 if trade.side == "buy" else -1
                trade.unrealized_pnl = round(
                    direction * (current_price - trade.entry_price) * trade.contracts, 2
                )
                break

    def get_stats(self, balance: float) -> Dict:
        closed = [t for t in self._trade_log if t.status != "open"]
        open_trades = [t for t in self._trade_log if t.status == "open"]
        winners = [t for t in closed if t.realized_pnl > 0]
        total_unrealized = sum(t.unrealized_pnl for t in open_trades)
        equity = balance + total_unrealized

        max_dd = max((p.drawdown_pct for p in self._equity_curve), default=0)
        avg_win = sum(t.realized_pnl for t in winners) / len(winners) if winners else 0
        losers = [t for t in closed if t.realized_pnl <= 0]
        avg_loss = sum(t.realized_pnl for t in losers) / len(losers) if losers else 0
        profit_factor = (
            abs(
                sum(t.realized_pnl for t in winners)
                / sum(t.realized_pnl for t in losers)
            )
            if losers and sum(t.realized_pnl for t in losers) != 0
            else 0
        )

        today = datetime.now(timezone.utc).date().isoformat()
        return {
            "equity": round(equity, 2),
            "balance": round(balance, 2),
            "total_pnl": round(self._realized_pnl, 2),
            "total_pnl_pct": round(
                (self._realized_pnl / self.initial_balance) * 100, 2
            ),
            "unrealized_pnl": round(total_unrealized, 2),
            "daily_pnl": round(self._daily_pnl.get(today, 0), 2),
            "max_drawdown_pct": round(max_dd, 2),
            "open_positions": len(open_trades),
            "total_trades": len(self._trade_log),
            "closed_trades": len(closed),
            "win_rate": round(len(winners) / len(closed) * 100, 1) if closed else 0,
            "profit_factor": round(profit_factor, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "best_trade": round(max((t.realized_pnl for t in closed), default=0), 2),
            "worst_trade": round(min((t.realized_pnl for t in closed), default=0), 2),
        }

    @property
    def equity_curve(self) -> List[Dict]:
        return [
            {
                "t": p.timestamp,
                "eq": p.equity,
                "dd": p.drawdown_pct,
                "upnl": p.unrealized_pnl,
                "rpnl": p.realized_pnl,
            }
            for p in self._equity_curve[-500:]
        ]

    @property
    def trade_log(self) -> List[Dict]:
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "side": t.side,
                "entry": t.entry_price,
                "exit": t.exit_price,
                "contracts": t.contracts,
                "pnl": t.realized_pnl,
                "upnl": t.unrealized_pnl,
                "status": t.status,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "emotion": t.emotion_score,
                "confidence": t.ai_confidence,
                "reasoning": t.reasoning[:150],
            }
            for t in self._trade_log[:50]
        ]
