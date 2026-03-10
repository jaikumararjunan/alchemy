"""
Alchemy Trading Bot - Server Entry Point
Starts FastAPI server with autonomous trading bot and WebSocket.

Usage:
    python run_server.py                    # Start with web dashboard
    python run_server.py --port 8080        # Custom port
    python run_server.py --start-bot        # Auto-start bot on launch
    python run_server.py --live             # Enable live trading
"""
import argparse
import asyncio
import sys
import os

import uvicorn

from config import config
from src.utils.logger import get_logger

logger = get_logger("alchemy.server")


def parse_args():
    p = argparse.ArgumentParser(description="Alchemy Trading Bot Server")
    p.add_argument("--host", default="0.0.0.0", help="Server host")
    p.add_argument("--port", type=int, default=8000, help="Server port")
    p.add_argument("--start-bot", action="store_true", help="Auto-start autonomous bot")
    p.add_argument("--live", action="store_true", help="Enable live trading (disable dry run)")
    p.add_argument("--dry-run", action="store_true", help="Force paper trading mode")
    p.add_argument("--symbol", default=None, help="Override trading symbol")
    p.add_argument("--interval", type=int, default=None, help="Analysis interval in minutes")
    p.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    return p.parse_args()


def main():
    args = parse_args()

    if args.live:
        config.trading.dry_run = False
        logger.info("LIVE TRADING MODE ENABLED")
    if args.dry_run:
        config.trading.dry_run = True
    if args.symbol:
        config.trading.symbol = args.symbol
    if args.interval:
        config.trading.analysis_interval_minutes = args.interval

    mode = "LIVE" if not config.trading.dry_run else "DRY RUN"
    print(f"""
╔═══════════════════════════════════════════════════════╗
║         ALCHEMY - Autonomous AI Crypto Trading        ║
╠═══════════════════════════════════════════════════════╣
║  Mode:     {mode:<44} ║
║  Symbol:   {config.trading.symbol:<44} ║
║  Interval: {config.trading.analysis_interval_minutes} min{' ' * 41} ║
║  Server:   http://{args.host}:{args.port:<36} ║
║  Dashboard: http://localhost:{args.port}                      ║
╚═══════════════════════════════════════════════════════╝
""")

    if args.start_bot:
        logger.info("Bot will auto-start after server launch")
        # Schedule bot start after server is up
        import threading
        def delayed_start():
            import time, requests
            time.sleep(3)
            try:
                requests.post(
                    f"http://localhost:{args.port}/api/bot/control",
                    json={"action": "start", "interval_minutes": config.trading.analysis_interval_minutes}
                )
                logger.info("Autonomous bot auto-started")
            except Exception as e:
                logger.warning(f"Auto-start failed: {e}")
        threading.Thread(target=delayed_start, daemon=True).start()

    uvicorn.run(
        "server.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
