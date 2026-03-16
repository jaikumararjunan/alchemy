"""
Alchemy - Crypto Trading Bot with Emotion Intelligence
Trades on Delta Exchange using geopolitical sentiment analysis via Claude AI.

Usage:
    python main.py [--dry-run] [--symbol BTCUSD] [--interval 30]
"""

import argparse
import time
import signal
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from config import config, AppConfig
from src.exchange import DeltaExchangeClient
from src.intelligence import EmotionEngine, GeopoliticalAnalyzer, NewsFetcher
from src.strategy import TradingStrategy
from src.risk import RiskManager
from src.utils.logger import get_logger

logger = get_logger("alchemy.main")
console = Console()

_running = True


def signal_handler(sig, frame):
    global _running
    console.print(
        "\n[yellow]Shutdown signal received. Stopping bot gracefully...[/yellow]"
    )
    _running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class AlchemyBot:
    """
    Main trading bot orchestrator.
    Coordinates: News Fetching -> Emotion Analysis -> Geo Analysis -> Strategy -> Risk -> Execution
    """

    def __init__(self, cfg: AppConfig):
        self.config = cfg
        cfg.validate()

        # Initialize components
        self.exchange = DeltaExchangeClient(
            api_key=cfg.delta.api_key,
            api_secret=cfg.delta.api_secret,
            base_url=cfg.delta.base_url,
        )
        self.emotion_engine = EmotionEngine(
            api_key=cfg.anthropic.api_key,
            model=cfg.anthropic.model,
        )
        self.geo_analyzer = GeopoliticalAnalyzer()
        self.news_fetcher = NewsFetcher(
            news_api_key=cfg.news.news_api_key,
            rss_feeds=cfg.news.rss_feeds,
            keywords=cfg.news.geopolitical_keywords,
            max_articles=cfg.news.max_articles_per_fetch,
        )
        self.strategy = TradingStrategy(cfg)
        self.risk_manager = RiskManager(cfg)

        self.symbol = cfg.trading.symbol
        self.product_id: Optional[int] = None
        self.dry_run = cfg.trading.dry_run
        self.interval = cfg.trading.analysis_interval_minutes * 60
        self._cycle_count = 0
        self._last_signal = None
        self._last_emotion = None
        self._last_geo = None

        mode = (
            "[bold red]LIVE[/bold red]"
            if not self.dry_run
            else "[bold green]DRY RUN[/bold green]"
        )
        console.print(
            Panel(
                f"[bold cyan]ALCHEMY[/bold cyan] - Crypto Trading with Emotion Intelligence\n"
                f"Symbol: [bold]{self.symbol}[/bold] | Mode: {mode} | "
                f"Model: [cyan]{cfg.anthropic.model}[/cyan]",
                border_style="cyan",
            )
        )

    def startup(self):
        """Initialize exchange connection and look up product ID."""
        logger.info("Starting Alchemy bot...")
        try:
            if not self.dry_run:
                self.product_id = self.exchange.get_product_id(self.symbol)
                if not self.product_id:
                    raise ValueError(
                        f"Product {self.symbol} not found on Delta Exchange"
                    )
                logger.info(
                    f"Connected to Delta Exchange. Product ID for {self.symbol}: {self.product_id}"
                )
                if self.config.trading.leverage > 1:
                    self.exchange.set_leverage(
                        self.product_id, self.config.trading.leverage
                    )
                    logger.info(f"Leverage set to {self.config.trading.leverage}x")
            else:
                logger.info("DRY RUN mode - skipping exchange connection")
                self.product_id = 0
        except Exception as e:
            logger.error(f"Startup failed: {e}")
            if not self.dry_run:
                raise

    def run(self):
        """Main trading loop."""
        self.startup()

        console.print(
            f"\n[green]Bot started. Analysis interval: {self.interval // 60} minutes[/green]"
        )
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        while _running:
            try:
                self._cycle_count += 1
                self._run_cycle()

                if not _running:
                    break

                next_run = datetime.now(timezone.utc).strftime("%H:%M:%S")
                console.print(
                    f"\n[dim]Cycle {self._cycle_count} complete. "
                    f"Next analysis in {self.interval // 60} min (at ~{next_run} UTC)[/dim]"
                )
                time.sleep(self.interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Cycle error: {e}", exc_info=True)
                console.print(f"[red]Cycle error: {e}. Retrying in 60s...[/red]")
                time.sleep(60)

        console.print("[yellow]Bot stopped.[/yellow]")

    def _run_cycle(self):
        """Execute one full analysis and trading cycle."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        console.rule(f"[cyan]Cycle {self._cycle_count} | {now}[/cyan]")

        # 1. Fetch news
        console.print("[bold]1. Fetching geopolitical news...[/bold]")
        articles = self.news_fetcher.fetch()
        console.print(f"   [green]{len(articles)} articles fetched[/green]")

        # 2. Emotion analysis via Claude
        console.print("[bold]2. Running Claude emotion intelligence analysis...[/bold]")
        emotion_score = self.emotion_engine.analyze(articles)
        self._last_emotion = emotion_score

        # 3. Geopolitical event detection
        console.print("[bold]3. Analyzing geopolitical events...[/bold]")
        geo_events = self.geo_analyzer.analyze(articles)
        geo_impact = self.geo_analyzer.get_aggregate_impact(geo_events)
        self._last_geo = geo_impact

        # 4. Get market data
        console.print("[bold]4. Fetching market data from Delta Exchange...[/bold]")
        price_data = self._get_market_data()

        # 5. Generate trade signal
        console.print("[bold]5. Generating trade signal...[/bold]")
        positions = self._get_positions()
        has_position = len(positions) > 0
        position_side = positions[0].side if has_position else None

        signal = self.strategy.generate_signal(
            emotion_score=emotion_score,
            geo_impact=geo_impact,
            candles=price_data["candles"],
            current_price=price_data["price"],
            has_open_position=has_position,
            open_position_side=position_side,
        )
        self._last_signal = signal

        # 6. Risk evaluation
        console.print("[bold]6. Evaluating risk...[/bold]")
        balance = self._get_balance()
        risk_metrics = self.risk_manager.evaluate(
            signal=signal,
            account_balance=balance,
            open_positions=len(positions),
            current_price=price_data["price"],
        )

        # 7. Display dashboard
        self._display_dashboard(
            emotion_score=emotion_score,
            geo_impact=geo_impact,
            geo_events=geo_events,
            signal=signal,
            risk_metrics=risk_metrics,
            price=price_data["price"],
            articles=articles,
        )

        # 8. Execute trade
        if signal.is_valid and risk_metrics.can_trade:
            self._execute_trade(signal, risk_metrics, price_data["price"], balance)
        else:
            reason = risk_metrics.rejection_reason or "Signal not actionable"
            if not signal.is_valid:
                reason = f"Signal invalid (R:R={signal.risk_reward_ratio:.2f}, confidence={signal.confidence:.2f})"
            console.print(f"\n[yellow]No trade executed: {reason}[/yellow]")

    def _get_market_data(self) -> dict:
        """Get current price and candle data."""
        try:
            if not self.dry_run:
                ticker = self.exchange.get_ticker(self.symbol)
                price = ticker.mark_price
                # Get 1-hour candles, last 100
                end_time = int(time.time())
                start_time = end_time - (100 * 3600)
                candles = self.exchange.get_candles(
                    self.symbol, resolution=3600, start=start_time, end=end_time
                )
                return {"price": price, "candles": candles}
            else:
                # Dry run: use mock data
                import random

                base_price = 65000.0
                mock_candles = [
                    {
                        "close": base_price + random.uniform(-2000, 2000),
                        "volume": random.uniform(100, 500),
                    }
                    for _ in range(60)
                ]
                return {
                    "price": base_price + random.uniform(-500, 500),
                    "candles": mock_candles,
                }
        except Exception as e:
            logger.warning(f"Failed to get market data: {e}")
            return {"price": 65000.0, "candles": []}

    def _get_positions(self):
        """Get open positions."""
        try:
            if not self.dry_run:
                return self.exchange.get_positions()
            return []
        except Exception as e:
            logger.warning(f"Failed to get positions: {e}")
            return []

    def _get_balance(self) -> float:
        """Get account balance."""
        try:
            if not self.dry_run:
                bal = self.exchange.get_wallet_balance("USDT")
                return bal.get("available_balance", 0.0)
            return 10000.0  # Mock balance for dry run
        except Exception as e:
            logger.warning(f"Failed to get balance: {e}")
            return 10000.0

    def _execute_trade(
        self, signal, risk_metrics, current_price: float, balance: float
    ):
        """Execute a trade on Delta Exchange or simulate it."""
        position_size = self.risk_manager.calculate_position_size(
            signal=signal,
            account_balance=balance,
            current_price=current_price,
            risk_metrics=risk_metrics,
        )
        contracts = self.risk_manager.calculate_contracts(
            position_size_usd=position_size,
            current_price=current_price,
            leverage=self.config.trading.leverage,
        )

        action_color = "green" if signal.action in ("buy",) else "red"
        console.print(
            f"\n[bold {action_color}]EXECUTING {signal.action.upper()}[/bold {action_color}]: "
            f"{contracts} contracts | ${position_size:.2f} | "
            f"SL: ${signal.stop_loss:.2f} | TP: ${signal.take_profit:.2f}"
        )

        if self.dry_run:
            console.print(
                "[bold yellow][DRY RUN] Trade simulated - no real order placed[/bold yellow]"
            )
            return

        try:
            from src.exchange.delta_client import Order

            if signal.action in ("buy", "sell"):
                order = Order(
                    symbol=self.symbol,
                    side=signal.action,
                    order_type="market",
                    size=contracts,
                )
                result = self.exchange.place_order(order, self.product_id)
                console.print(f"[green]Order placed: {result.get('id', 'N/A')}[/green]")

            elif signal.action == "close_long":
                result = self.exchange.close_position(self.product_id, self.symbol)
                console.print(
                    f"[green]Long position closed: {result.get('id', 'N/A')}[/green]"
                )

            elif signal.action == "close_short":
                result = self.exchange.close_position(self.product_id, self.symbol)
                console.print(
                    f"[green]Short position closed: {result.get('id', 'N/A')}[/green]"
                )

        except Exception as e:
            logger.error(f"Order execution failed: {e}")
            console.print(f"[red]Order failed: {e}[/red]")

    def _display_dashboard(
        self,
        emotion_score,
        geo_impact,
        geo_events,
        signal,
        risk_metrics,
        price,
        articles,
    ):
        """Display a rich dashboard of current bot state."""
        console.print()

        # Emotion Analysis Panel
        emotion_color = "green" if emotion_score.sentiment_score > 0 else "red"
        emotion_table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        emotion_table.add_column("Key", style="dim")
        emotion_table.add_column("Value", style="bold")
        emotion_table.add_row(
            "Dominant Emotion",
            f"[{emotion_color}]{emotion_score.dominant_emotion.upper()}[/{emotion_color}]",
        )
        emotion_table.add_row(
            "Sentiment Score",
            f"[{emotion_color}]{emotion_score.sentiment_score:+.3f}[/{emotion_color}]",
        )
        emotion_table.add_row(
            "Crypto Sentiment", f"{emotion_score.crypto_specific_sentiment:+.3f}"
        )
        emotion_table.add_row("Confidence", f"{emotion_score.confidence:.0%}")
        emotion_table.add_row(
            "Geo Risk",
            f"[{'red' if emotion_score.geopolitical_risk in ('high', 'critical') else 'yellow'}]{emotion_score.geopolitical_risk.upper()}[/{'red' if emotion_score.geopolitical_risk in ('high', 'critical') else 'yellow'}]",
        )
        emotion_table.add_row(
            "Trading Bias", f"[bold]{emotion_score.trading_bias.upper()}[/bold]"
        )
        console.print(
            Panel(
                emotion_table,
                title="[cyan]Claude Emotion Intelligence[/cyan]",
                border_style="cyan",
            )
        )

        # Key Events
        if emotion_score.key_events:
            events_text = "\n".join(f"  • {e}" for e in emotion_score.key_events[:5])
            console.print(
                Panel(
                    events_text,
                    title="[cyan]Key Geopolitical Events[/cyan]",
                    border_style="dim",
                )
            )

        # Claude Reasoning
        if emotion_score.reasoning:
            console.print(
                Panel(
                    f"[italic]{emotion_score.reasoning}[/italic]",
                    title="[cyan]Claude AI Reasoning[/cyan]",
                    border_style="dim",
                )
            )

        # Geopolitical Impact
        geo_color = {
            "neutral": "white",
            "bullish": "green",
            "strongly_bullish": "green",
            "bearish": "red",
            "strongly_bearish": "red",
        }.get(geo_impact.get("net_sentiment", ""), "white")
        geo_table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        geo_table.add_column("Key", style="dim")
        geo_table.add_column("Value", style="bold")
        geo_table.add_row(
            "Net Sentiment",
            f"[{geo_color}]{geo_impact.get('net_sentiment', 'neutral').upper()}[/{geo_color}]",
        )
        geo_table.add_row("Total Impact", f"{geo_impact.get('total_impact', 0):+.3f}")
        geo_table.add_row("Risk Level", geo_impact.get("risk_level", "low").upper())
        geo_table.add_row("Events Detected", str(geo_impact.get("event_count", 0)))
        geo_table.add_row(
            "Bullish Pressure", f"{geo_impact.get('bullish_pressure', 0):.3f}"
        )
        geo_table.add_row(
            "Bearish Pressure", f"{geo_impact.get('bearish_pressure', 0):.3f}"
        )
        console.print(
            Panel(
                geo_table,
                title="[magenta]Geopolitical Impact[/magenta]",
                border_style="magenta",
            )
        )

        # Trade Signal
        sig_color = (
            "green"
            if signal.action in ("buy", "close_short")
            else "red"
            if signal.action in ("sell", "close_long")
            else "yellow"
        )
        sig_table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        sig_table.add_column("Key", style="dim")
        sig_table.add_column("Value", style="bold")
        sig_table.add_row(
            "Action", f"[{sig_color}]{signal.action.upper()}[/{sig_color}]"
        )
        sig_table.add_row("Current Price", f"${price:,.2f}")
        sig_table.add_row("Stop Loss", f"${signal.stop_loss:,.2f}")
        sig_table.add_row("Take Profit", f"${signal.take_profit:,.2f}")
        sig_table.add_row("Confidence", f"{signal.confidence:.0%}")
        sig_table.add_row("Risk:Reward", f"{signal.risk_reward_ratio:.2f}:1")
        sig_table.add_row("Size Multiplier", f"{signal.position_size_multiplier:.0%}")
        sig_table.add_row(
            "Valid Signal", "[green]YES[/green]" if signal.is_valid else "[red]NO[/red]"
        )
        if signal.signal_sources:
            sig_table.add_row("Sources", ", ".join(signal.signal_sources))
        console.print(
            Panel(sig_table, title="[bold]Trade Signal[/bold]", border_style=sig_color)
        )

        # Risk Metrics
        risk_color = {
            "green": "green",
            "yellow": "yellow",
            "red": "red",
            "halt": "bold red",
        }
        r_color = risk_color.get(risk_metrics.risk_level, "white")
        risk_table = Table(box=box.SIMPLE, show_header=False, pad_edge=False)
        risk_table.add_column("Key", style="dim")
        risk_table.add_column("Value", style="bold")
        risk_table.add_row(
            "Risk Level", f"[{r_color}]{risk_metrics.risk_level.upper()}[/{r_color}]"
        )
        risk_table.add_row("Balance", f"${risk_metrics.account_balance:,.2f}")
        risk_table.add_row(
            "Daily PnL",
            f"${risk_metrics.daily_pnl:+.2f} ({risk_metrics.daily_pnl_pct:+.2f}%)",
        )
        risk_table.add_row("Max Drawdown", f"{risk_metrics.max_drawdown_pct:.2f}%")
        risk_table.add_row(
            "Can Trade",
            "[green]YES[/green]" if risk_metrics.can_trade else "[red]NO[/red]",
        )
        if risk_metrics.rejection_reason:
            risk_table.add_row("Reason", f"[dim]{risk_metrics.rejection_reason}[/dim]")
        console.print(
            Panel(
                risk_table,
                title="[yellow]Risk Management[/yellow]",
                border_style="yellow",
            )
        )

        # Recent news headlines
        if articles:
            news_table = Table(box=box.SIMPLE, show_header=True, pad_edge=False)
            news_table.add_column("Source", style="dim", width=15)
            news_table.add_column("Score", width=6)
            news_table.add_column("Headline")
            for a in articles[:5]:
                score_color = (
                    "green"
                    if a.relevance_score >= 0.6
                    else "yellow"
                    if a.relevance_score >= 0.3
                    else "dim"
                )
                news_table.add_row(
                    a.source[:15],
                    f"[{score_color}]{a.relevance_score:.2f}[/{score_color}]",
                    a.title[:80],
                )
            console.print(
                Panel(
                    news_table, title="[dim]Top News Articles[/dim]", border_style="dim"
                )
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Alchemy - Crypto Trading with Emotion Intelligence"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Paper trading mode (no real orders)"
    )
    parser.add_argument("--live", action="store_true", help="Enable live trading")
    parser.add_argument("--symbol", default=None, help="Trading symbol (e.g. BTCUSD)")
    parser.add_argument(
        "--interval", type=int, default=None, help="Analysis interval in minutes"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.symbol:
        config.trading.symbol = args.symbol
    if args.interval:
        config.trading.analysis_interval_minutes = args.interval
    if args.dry_run:
        config.trading.dry_run = True
    if args.live:
        config.trading.dry_run = False

    bot = AlchemyBot(config)
    bot.run()


if __name__ == "__main__":
    main()
