from __future__ import annotations

import time
from threading import Lock
from typing import Any

import httpx

from ....config import Settings
from ....logging import get_logger

TRANSIENT_STATUS_CODES = {500, 502, 503, 504}

_client: httpx.Client | None = None
_client_limits: tuple[int, int] | None = None
_client_lock = Lock()
log = get_logger()


def get_external_api_client(settings: Settings) -> httpx.Client:
    global _client, _client_limits

    max_connections = settings.external_api_max_connections
    max_keepalive_connections = min(
        settings.external_api_max_keepalive_connections,
        max_connections,
    )
    limits_key = (max_connections, max_keepalive_connections)
    with _client_lock:
        if _client is not None and _client_limits == limits_key:
            return _client
        if _client is not None:
            _client.close()

        _client = httpx.Client(
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_keepalive_connections,
            )
        )
        _client_limits = limits_key
        return _client


def close_external_api_client() -> None:
    global _client, _client_limits

    with _client_lock:
        if _client is not None:
            _client.close()
        _client = None
        _client_limits = None


def post_json_with_retries(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    url: str,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    auth: httpx.Auth | None,
    timeout_seconds: float,
) -> httpx.Response:
    # Voice calls have a strict end-to-end budget. Do not turn one slow
    # upstream request into two full-length waits.
    attempts_total = min(settings.external_api_max_retries, 1) + 1
    deadline = time.monotonic() + settings.external_api_total_deadline_seconds
    last_timeout: httpx.TimeoutException | None = None
    last_request_error: httpx.RequestError | None = None

    for attempt in range(1, attempts_total + 1):
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            raise httpx.TimeoutException("external API total deadline exceeded")
        started_at = time.perf_counter()
        try:
            response = get_external_api_client(settings).post(
                url,
                json=payload,
                headers=headers,
                auth=auth,
                timeout=min(timeout_seconds, remaining_seconds),
            )
        except httpx.TimeoutException as exc:
            last_timeout = exc
            _log_attempt(
                tenant_id=tenant_id,
                call_id=call_id,
                path=path,
                attempt=attempt,
                attempts_total=attempts_total,
                duration_ms=_elapsed_ms(started_at),
                outcome="timeout",
            )
            if attempt < attempts_total and _sleep_before_retry(settings, deadline):
                continue
            raise
        except httpx.RequestError as exc:
            last_request_error = exc
            _log_attempt(
                tenant_id=tenant_id,
                call_id=call_id,
                path=path,
                attempt=attempt,
                attempts_total=attempts_total,
                duration_ms=_elapsed_ms(started_at),
                outcome="request_error",
                error_type=exc.__class__.__name__,
            )
            if attempt < attempts_total and _sleep_before_retry(settings, deadline):
                continue
            raise

        duration_ms = _elapsed_ms(started_at)
        transient_http = response.status_code in TRANSIENT_STATUS_CODES
        malformed_json = _is_malformed_json_success_response(response)
        retryable_response = transient_http or malformed_json
        _log_attempt(
            tenant_id=tenant_id,
            call_id=call_id,
            path=path,
            attempt=attempt,
            attempts_total=attempts_total,
            duration_ms=duration_ms,
            outcome=(
                "transient_http"
                if transient_http
                else "malformed_json"
                if malformed_json
                else "response"
            ),
            status_code=response.status_code,
        )
        if retryable_response and attempt < attempts_total and _sleep_before_retry(settings, deadline):
            continue
        return response

    if last_timeout is not None:
        raise last_timeout
    if last_request_error is not None:
        raise last_request_error
    raise RuntimeError("external API retry loop ended without response")


def _sleep_before_retry(settings: Settings, deadline: float) -> bool:
    remaining_seconds = deadline - time.monotonic()
    if remaining_seconds <= 0:
        return False
    delay_seconds = min(settings.external_api_retry_backoff_seconds, remaining_seconds)
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    return deadline > time.monotonic()


def _is_malformed_json_success_response(response: httpx.Response) -> bool:
    if not 200 <= response.status_code < 300:
        return False
    try:
        response.json()
    except ValueError:
        return True
    return False


def _elapsed_ms(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _log_attempt(
    *,
    tenant_id: str,
    call_id: str,
    path: str,
    attempt: int,
    attempts_total: int,
    duration_ms: float,
    outcome: str,
    status_code: int | None = None,
    error_type: str | None = None,
) -> None:
    method = (
        log.warning
        if outcome in {"timeout", "request_error", "transient_http", "malformed_json"}
        else log.info
    )
    method(
        "external_api_provider_search_attempt",
        event_type="external_api_upstream",
        tenant_id=tenant_id,
        call_id=call_id,
        path=path,
        attempt=attempt,
        max_attempts=attempts_total,
        duration_ms=duration_ms,
        outcome=outcome,
        status_code=status_code,
        error_type=error_type,
    )
