"""
alchemy.api.metrics
====================
Prometheus metrics endpoint for Kubernetes monitoring.
"""
from __future__ import annotations
import time
from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

router = APIRouter()

# Simple in-memory metrics store
_metrics = {
    "requests_total":     {},   # {method_path_status: count}
    "request_duration":   [],   # [(method, path, duration)]
    "active_ws":          0,
    "errors_total":       0,
    "startup_time":       time.time(),
}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        key = f"{request.method}_{request.url.path}_{response.status_code}"
        _metrics["requests_total"][key] = _metrics["requests_total"].get(key, 0) + 1
        _metrics["request_duration"].append((request.method, request.url.path, duration))

        # Keep last 1000 only
        if len(_metrics["request_duration"]) > 1000:
            _metrics["request_duration"] = _metrics["request_duration"][-1000:]

        if response.status_code >= 500:
            _metrics["errors_total"] += 1

        return response


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    uptime = time.time() - _metrics["startup_time"]
    lines  = [
        "# HELP alchemy_uptime_seconds Seconds since startup",
        "# TYPE alchemy_uptime_seconds gauge",
        f"alchemy_uptime_seconds {uptime:.1f}",
        "",
        "# HELP alchemy_requests_total Total HTTP requests",
        "# TYPE alchemy_requests_total counter",
    ]
    for key, count in _metrics["requests_total"].items():
        parts = key.split("_", 2)
        if len(parts) == 3:
            method, path, status = parts
            path = path.replace('"','')
            lines.append(f'alchemy_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')

    durations = _metrics["request_duration"]
    if durations:
        avg = sum(d[2] for d in durations) / len(durations)
        p95 = sorted(d[2] for d in durations)[int(len(durations)*0.95)]
        lines += [
            "",
            "# HELP alchemy_request_duration_seconds Request duration",
            "# TYPE alchemy_request_duration_seconds gauge",
            f'alchemy_request_duration_seconds{{quantile="0.50"}} {avg:.4f}',
            f'alchemy_request_duration_seconds{{quantile="0.95"}} {p95:.4f}',
        ]

    lines += [
        "",
        "# HELP alchemy_errors_total Total 5xx errors",
        "# TYPE alchemy_errors_total counter",
        f"alchemy_errors_total {_metrics['errors_total']}",
        "",
        "# HELP alchemy_active_websockets Active WebSocket connections",
        "# TYPE alchemy_active_websockets gauge",
        f"alchemy_active_websockets {_metrics['active_ws']}",
    ]
    return Response("\n".join(lines) + "\n", media_type="text/plain; charset=utf-8")
