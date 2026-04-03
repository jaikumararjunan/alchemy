"""
alchemy.tokens.manager
======================
Token manager stub — credentials are now stored in SQLite via token_routes.py
This stub prevents the old vault-based manager from calling exchange APIs on startup.
"""
from __future__ import annotations
import structlog
log = structlog.get_logger(__name__)

class TokenManager:
    def __init__(self): 
        self._tokens = {}
        log.info("token_manager.ready", exchanges=[])

    def start_auto_refresh(self): 
        log.info("token.auto_refresh_started", interval_s=1800)

    def status(self): return {}
    def get_token(self, exchange): return None
    def register(self, token): pass
    def deregister(self, exchange): pass

_manager = None

def get_token_manager() -> TokenManager:
    global _manager
    if _manager is None:
        _manager = TokenManager()
    return _manager
