"""
alchemy.auth.feature_gate
==========================
Subscription-based feature gating.
Every protected endpoint calls check_feature() before processing.
"""
from __future__ import annotations
from fastapi import HTTPException
from typing import Any

PLANS = {
    "free":       0,
    "pro":        1,
    "team":       2,
    "enterprise": 3,
}

# Feature matrix: feature_key → minimum_plan
FEATURES: dict[str, str] = {
    # Trading
    "trading.live":              "pro",
    "trading.orders":            "pro",
    "trading.all_strategies":    "pro",
    "trading.custom_strategy":   "team",

    # Exchanges
    "exchange.2_connections":    "pro",
    "exchange.4_connections":    "team",
    "exchange.unlimited":        "enterprise",

    # Chart / Data
    "chart.candles_500":         "pro",
    "chart.candles_5000":        "team",
    "chart.candles_unlimited":   "enterprise",
    "chart.drawing_tools":       "pro",

    # AI
    "ai.ideas_50":               "pro",
    "ai.ideas_unlimited":        "team",
    "ai.ml_prediction":          "team",
    "ai.custom_model":           "enterprise",

    # Intelligence
    "intel.geo_signals":         "pro",
    "intel.premium_feeds":       "team",
    "intel.sentiment_nlp":       "pro",
    "intel.options_analytics":   "pro",

    # Alerts
    "alerts.telegram":           "pro",
    "alerts.whatsapp":           "team",
    "alerts.sms":                "team",
    "alerts.webhook":            "enterprise",

    # Analytics
    "analytics.export_csv":      "pro",
    "analytics.export_json":     "team",
    "analytics.backtesting":     "pro",
    "analytics.tax_report":      "pro",

    # API / Integrations
    "api.external_read":         "team",
    "api.external_write":        "enterprise",
    "api.webhooks":              "team",
    "api.sdk":                   "team",

    # Team / Admin
    "team.multi_user":           "team",
    "team.audit_logs":           "team",
    "team.copy_trading":         "team",
    "team.white_label":          "enterprise",
}

# Per-plan limits
LIMITS: dict[str, dict[str, Any]] = {
    "free": {
        "ai_ideas_per_day":   5,
        "candles":            50,
        "exchanges":          1,
        "ws_connections":     1,
        "alert_channels":     0,
    },
    "pro": {
        "ai_ideas_per_day":   50,
        "candles":            500,
        "exchanges":          2,
        "ws_connections":     1,
        "alert_channels":     2,
    },
    "team": {
        "ai_ideas_per_day":   -1,   # unlimited
        "candles":            5000,
        "exchanges":          4,
        "ws_connections":     10,
        "alert_channels":     5,
    },
    "enterprise": {
        "ai_ideas_per_day":   -1,
        "candles":            -1,
        "exchanges":          -1,
        "ws_connections":     -1,
        "alert_channels":     -1,
    },
}


def check_feature(user_plan: str, feature: str) -> None:
    """Raise 403 with upgrade message if plan insufficient."""
    plan_level    = PLANS.get(user_plan, 0)
    required_plan = FEATURES.get(feature, "free")
    required_level= PLANS.get(required_plan, 0)
    if plan_level < required_level:
        raise HTTPException(
            status_code=403,
            detail={
                "error":         "plan_upgrade_required",
                "message":       f"This feature requires the {required_plan.title()} plan.",
                "current_plan":  user_plan,
                "required_plan": required_plan,
                "upgrade_url":   "/settings/billing",
            }
        )


def get_limit(user_plan: str, limit_key: str) -> Any:
    """Get numeric limit for plan. -1 = unlimited."""
    plan_limits = LIMITS.get(user_plan, LIMITS["free"])
    return plan_limits.get(limit_key, 0)


def get_plan_features(user_plan: str) -> dict:
    """Return all features available for a plan."""
    plan_level = PLANS.get(user_plan, 0)
    return {
        feat: PLANS[req] <= plan_level
        for feat, req in FEATURES.items()
    }
