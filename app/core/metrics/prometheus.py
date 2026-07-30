import os
from time import perf_counter

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send


INTERNAL_METRICS_PATH = "/internal/metrics"
UNMATCHED_ROUTE = "__unmatched__"
OTHER_METHOD = "OTHER"
KNOWN_HTTP_METHODS = frozenset(
    {
        "CONNECT",
        "DELETE",
        "GET",
        "HEAD",
        "OPTIONS",
        "PATCH",
        "POST",
        "PUT",
        "TRACE",
    }
)

HTTP_REQUESTS_TOTAL = Counter(
    "integrix_http_requests_total",
    "Completed HTTP requests, recorded at response completion time.",
    ("method", "route", "status"),
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "integrix_http_request_duration_seconds",
    "HTTP request duration in seconds, measured until the response is completed.",
    ("method", "route", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "integrix_http_requests_in_progress",
    "HTTP requests currently being processed.",
    ("method",),
    multiprocess_mode="livesum",
)


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return UNMATCHED_ROUTE


class PrometheusHttpMetricsMiddleware:
    """Record bounded-cardinality HTTP metrics without tenant or PII labels."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or scope.get("path") == INTERNAL_METRICS_PATH:
            await self.app(scope, receive, send)
            return

        raw_method = str(scope.get("method", "")).upper()
        method = raw_method if raw_method in KNOWN_HTTP_METHODS else OTHER_METHOD
        status_code = 500
        started_at = perf_counter()
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            route = _route_template(scope)
            status = str(status_code)
            duration_seconds = max(0.0, perf_counter() - started_at)
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status=status).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                route=route,
                status=status,
            ).observe(duration_seconds)


def render_prometheus_metrics() -> tuple[bytes, str]:
    multiprocess_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if multiprocess_dir:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry, path=multiprocess_dir)
    else:
        registry = REGISTRY
    return generate_latest(registry), CONTENT_TYPE_LATEST
