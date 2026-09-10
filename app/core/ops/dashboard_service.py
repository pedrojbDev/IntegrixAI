from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, func, select, tuple_
from sqlalchemy.orm import Session

from ...models.call_event import CallEvent
from ...models.ops_sync_state import OpsSyncState
from ...models.tool_invocation import ToolBusinessErrorAttempt
from ...models.vapi_call_cost import VapiCallCost

WINDOW_TO_MINUTES = {
    "15m": 15,
    "1h": 60,
    "24h": 1440,
    "7d": 10080,
    "15d": 21600,
    "30d": 43200,
    "60d": 86400,
    "90d": 129600,
}
WINDOW_BUCKET_MINUTES = {
    "15m": 1,
    "1h": 5,
    "24h": 60,
    "7d": 360,
    "15d": 1440,
    "30d": 1440,
    "60d": 1440,
    "90d": 1440,
}
SYNC_FRESH_SECONDS = 15 * 60
SYNC_DELAY_SECONDS = 60 * 60
METRIC_VERSION = "v5"
HANDOFF_TOOL_NAME = "handoff_human"
NATIVE_HANDOFF_EVENT_TYPE = "vapi_native_transfer_completed"
NORMAL_COMPLETION_EVENT_TYPE = "vapi_normal_call_completed"
TECHNICAL_ERROR_CODES = frozenset({
    "TIMEOUT", "UPSTREAM_503", "UPSTREAM_AUTH", "UPSTREAM_TIMEOUT",
    "UPSTREAM_NETWORK", "UPSTREAM_5XX", "UPSTREAM_UNEXPECTED",
})
SEARCH_ATTEMPT_EVENT_TYPE = "provider_search_requested"
SEARCH_BLOCKED_EVENT_TYPE = "provider_search_blocked"
SEARCH_UPSTREAM_STARTED_EVENT_TYPE = "provider_search_upstream_started"
SEARCH_COMPLETED_EVENT_TYPE = "provider_search_completed"
SEARCH_RESULT_REUSED_EVENT_TYPE = "provider_search_result_reused"
SEARCH_FAILED_EVENT_TYPE = "provider_search_failed"
SEARCH_HANDOFF_RECOMMENDED_EVENT_TYPE = "provider_handoff_recommended"
SEARCH_EVENT_TYPES = frozenset(
    {
        SEARCH_ATTEMPT_EVENT_TYPE,
        SEARCH_BLOCKED_EVENT_TYPE,
        SEARCH_UPSTREAM_STARTED_EVENT_TYPE,
        SEARCH_COMPLETED_EVENT_TYPE,
        SEARCH_RESULT_REUSED_EVENT_TYPE,
        SEARCH_FAILED_EVENT_TYPE,
        SEARCH_HANDOFF_RECOMMENDED_EVENT_TYPE,
        NATIVE_HANDOFF_EVENT_TYPE,
    }
)
UPSTREAM_FAILURE_KEYS = {
    "UPSTREAM_AUTH": "auth",
    "UPSTREAM_TIMEOUT": "timeout",
    "UPSTREAM_NETWORK": "network",
    "UPSTREAM_5XX": "five_xx",
    "UPSTREAM_UNEXPECTED": "unexpected",
}


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _floor_bucket(dt: datetime, minutes: int) -> datetime:
    dt = _ensure_utc(dt) or datetime.now(timezone.utc)
    minute_floor = (dt.minute // minutes) * minutes
    return dt.replace(minute=minute_floor, second=0, microsecond=0)


def _resolve_window(window: str) -> tuple[datetime, int]:
    if window not in WINDOW_TO_MINUTES:
        raise ValueError("window invalida")
    minutes = WINDOW_TO_MINUTES[window]
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return since, WINDOW_BUCKET_MINUTES[window]


def _search_event_rows(
    session: Session,
    *,
    since: datetime,
    until: datetime,
    tenant_id: str | None,
    call_keys_filter: set[tuple[str, str]] | None,
) -> list[tuple[str, str, str, str | None, dict | None, datetime]]:
    """Read the bounded, PII-free PB Saude search event stream for v5."""
    if call_keys_filter is not None and not call_keys_filter:
        return []
    filters = [
        CallEvent.event_type.in_(SEARCH_EVENT_TYPES),
        CallEvent.created_at >= since,
        CallEvent.created_at < until,
    ]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if not _apply_call_key_filter(
        filters,
        tenant_column=CallEvent.tenant_id,
        call_column=CallEvent.call_id,
        tenant_id=tenant_id,
        call_keys_filter=call_keys_filter,
    ):
        return []
    return list(
        session.execute(
            select(
                CallEvent.tenant_id,
                CallEvent.call_id,
                CallEvent.event_type,
                CallEvent.error_code,
                CallEvent.payload_masked,
                CallEvent.created_at,
            ).where(*filters)
        ).all()
    )


def _event_call_keys(
    rows: list[tuple[str, str, str, str | None, dict | None, datetime]],
    *,
    event_types: set[str] | frozenset[str],
    predicate=None,
) -> set[tuple[str, str]]:
    return {
        (tenant, call_id)
        for tenant, call_id, event_type, error_code, payload, _created_at in rows
        if event_type in event_types
        and (predicate is None or predicate(error_code, payload if isinstance(payload, dict) else {}))
    }


def _distinct_event_series(
    rows: list[tuple[str, str, str, str | None, dict | None, datetime]],
    *,
    bucket_minutes: int,
    event_types: set[str] | frozenset[str],
    predicate=None,
) -> list[dict[str, Any]]:
    first_event_at: dict[tuple[str, str], datetime] = {}
    for tenant, call_id, event_type, error_code, payload, created_at in rows:
        if event_type not in event_types:
            continue
        safe_payload = payload if isinstance(payload, dict) else {}
        if predicate is not None and not predicate(error_code, safe_payload):
            continue
        call_key = (tenant, call_id)
        previous = first_event_at.get(call_key)
        if previous is None or created_at < previous:
            first_event_at[call_key] = created_at
    buckets: dict[datetime, int] = defaultdict(int)
    for created_at in first_event_at.values():
        buckets[_floor_bucket(created_at, bucket_minutes)] += 1
    return [
        {"timestamp": bucket.isoformat(), "value": count}
        for bucket, count in sorted(buckets.items())
    ]


def _apply_call_key_filter(
    filters: list[Any],
    *,
    tenant_column: Any,
    call_column: Any,
    tenant_id: str | None,
    call_keys_filter: set[tuple[str, str]] | None,
) -> bool:
    """Filter calls by their tenant-local identity without penalizing tenant reads."""
    if call_keys_filter is None:
        return True
    if not call_keys_filter:
        return False
    if tenant_id:
        scoped_call_ids = {call_id for key_tenant_id, call_id in call_keys_filter if key_tenant_id == tenant_id}
        if not scoped_call_ids:
            return False
        filters.append(call_column.in_(scoped_call_ids))
        return True
    filters.append(tuple_(tenant_column, call_column).in_(call_keys_filter))
    return True


def _assistant_call_keys(
    session: Session,
    *,
    since: datetime,
    tenant_id: str | None,
    assistant_id: str | None,
) -> set[tuple[str, str]] | None:
    if not assistant_id:
        return None

    stmt = select(VapiCallCost.tenant_id, VapiCallCost.call_id).where(
        VapiCallCost.started_at >= since,
        VapiCallCost.assistant_id == assistant_id,
    )
    if tenant_id:
        stmt = stmt.where(VapiCallCost.tenant_id == tenant_id)
    rows = session.execute(stmt).all()
    return {(row.tenant_id, row.call_id) for row in rows if row.tenant_id and row.call_id}


def _latest_tool_completed_subquery(
    *,
    since: datetime,
    tenant_id: str | None,
    call_keys_filter: set[tuple[str, str]] | None = None,
):
    filters = [CallEvent.event_type == "tool_completed", CallEvent.created_at >= since]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if not _apply_call_key_filter(
        filters,
        tenant_column=CallEvent.tenant_id,
        call_column=CallEvent.call_id,
        tenant_id=tenant_id,
        call_keys_filter=call_keys_filter,
    ):
        return None

    latest_per_call = (
        select(
            CallEvent.tenant_id,
            CallEvent.call_id,
            func.max(CallEvent.created_at).label("max_created_at"),
        )
        .where(*filters)
        .group_by(CallEvent.tenant_id, CallEvent.call_id)
        .subquery()
    )

    return (
        select(
            CallEvent.tenant_id.label("tenant_id"),
            CallEvent.call_id.label("call_id"),
            CallEvent.created_at.label("created_at"),
            CallEvent.final_state.label("final_state"),
            CallEvent.duration_ms.label("duration_ms"),
        )
        .join(
            latest_per_call,
            and_(
                CallEvent.tenant_id == latest_per_call.c.tenant_id,
                CallEvent.call_id == latest_per_call.c.call_id,
                CallEvent.created_at == latest_per_call.c.max_created_at,
            ),
        )
        .subquery()
    )


def _tool_completed_filters(
    *,
    since: datetime,
    tenant_id: str | None,
    call_keys_filter: set[tuple[str, str]] | None,
) -> list[Any]:
    filters: list[Any] = [
        CallEvent.event_type == "tool_completed",
        CallEvent.created_at >= since,
    ]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if not _apply_call_key_filter(
        filters,
        tenant_column=CallEvent.tenant_id,
        call_column=CallEvent.call_id,
        tenant_id=tenant_id,
        call_keys_filter=call_keys_filter,
    ):
        return []
    return filters


def _call_outcomes_subquery(
    *,
    since: datetime,
    tenant_id: str | None,
    call_keys_filter: set[tuple[str, str]] | None,
):
    """Classify each call from all terminal tool and Vapi lifecycle events.

    A successful human handoff takes precedence over an earlier automatic
    resolution and remains unresolved from the automation perspective. A
    normal end initiated by the customer or agent is an automatic resolution.
    Technical incidents stay independent from call outcomes.
    """
    filters: list[Any] = [
        CallEvent.created_at >= since,
        CallEvent.event_type.in_(
            {"tool_completed", NATIVE_HANDOFF_EVENT_TYPE, NORMAL_COMPLETION_EVENT_TYPE}
        ),
    ]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if not _apply_call_key_filter(
        filters,
        tenant_column=CallEvent.tenant_id,
        call_column=CallEvent.call_id,
        tenant_id=tenant_id,
        call_keys_filter=call_keys_filter,
    ):
        return None

    successful_handoff = and_(
        CallEvent.ok.is_(True),
        CallEvent.final_state == "TRANSFERIDA_HUMANO",
        (
            (CallEvent.tool_name == HANDOFF_TOOL_NAME)
            | (CallEvent.event_type == NATIVE_HANDOFF_EVENT_TYPE)
        ),
    )
    automatic_resolution = and_(
        CallEvent.event_type == "tool_completed",
        CallEvent.tool_name != HANDOFF_TOOL_NAME,
        CallEvent.ok.is_(True),
        CallEvent.final_state == "RESOLVIDA_AUTOMATICO",
    )
    normal_completion = and_(
        CallEvent.event_type == NORMAL_COMPLETION_EVENT_TYPE,
        CallEvent.ok.is_(True),
    )
    return (
        select(
            CallEvent.tenant_id.label("tenant_id"),
            CallEvent.call_id.label("call_id"),
            func.min(CallEvent.created_at).label("first_event_at"),
            func.max(case((successful_handoff, 1), else_=0)).label("successful_handoff"),
            func.max(case((automatic_resolution, 1), else_=0)).label("automatic_resolution"),
            func.max(case((normal_completion, 1), else_=0)).label("normal_completion"),
        )
        .where(*filters)
        .group_by(CallEvent.tenant_id, CallEvent.call_id)
        .subquery()
    )


def _summarize_call_outcomes(rows: list[Any]) -> dict[str, int]:
    """Return mutually exclusive agent-success categories plus automation gaps.

    A successful handoff is intentionally both an agent success and an
    unresolved automation outcome: the bot successfully escalated, but did
    not resolve the request without a human.
    """
    summary = {
        "total_calls": len(rows),
        "automated_resolution_calls": 0,
        "successful_handoff_calls": 0,
        "normal_completion_calls": 0,
        "successful_agent_calls": 0,
        "unresolved_calls": 0,
    }
    for row in rows:
        handoff = bool(row.successful_handoff)
        normal_completion = bool(row.normal_completion) and not handoff
        automatic = (bool(row.automatic_resolution) or normal_completion) and not handoff

        if handoff:
            summary["successful_handoff_calls"] += 1
        if automatic:
            summary["automated_resolution_calls"] += 1
        if normal_completion:
            summary["normal_completion_calls"] += 1

        if handoff or automatic:
            summary["successful_agent_calls"] += 1

        # Handoffs deliberately remain unresolved from the automated-service
        # viewpoint, even though escalation itself is a successful agent act.
        if handoff or not automatic:
            summary["unresolved_calls"] += 1
    return summary


def _event_filters(
    *,
    since: datetime,
    tenant_id: str | None,
    call_keys_filter: set[tuple[str, str]] | None,
    event_type: str | None = None,
    ok: bool | None = None,
) -> list[Any]:
    filters: list[Any] = [CallEvent.created_at >= since]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if event_type:
        filters.append(CallEvent.event_type == event_type)
    if ok is not None:
        filters.append(CallEvent.ok == ok)
    if not _apply_call_key_filter(
        filters,
        tenant_column=CallEvent.tenant_id,
        call_column=CallEvent.call_id,
        tenant_id=tenant_id,
        call_keys_filter=call_keys_filter,
    ):
        return []
    return filters


def _bucket_series_from_rows(
    rows: list[tuple[datetime | None, float | int]],
    *,
    bucket_minutes: int,
) -> list[dict[str, Any]]:
    series_map: dict[str, float] = defaultdict(float)
    for point_time, value in rows:
        dt = _ensure_utc(point_time)
        if dt is None:
            continue
        bucket = _floor_bucket(dt, bucket_minutes).isoformat()
        series_map[bucket] += float(value)
    return [
        {"timestamp": timestamp, "value": round(value, 2)}
        for timestamp, value in sorted(series_map.items())
    ]


def _bucket_average_series_from_rows(
    rows: list[tuple[datetime | None, float | int | None]],
    *,
    bucket_minutes: int,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for point_time, value in rows:
        dt = _ensure_utc(point_time)
        if dt is None or value is None:
            continue
        buckets[_floor_bucket(dt, bucket_minutes).isoformat()].append(float(value))
    return [
        {"timestamp": timestamp, "value": round(sum(values) / len(values), 2)}
        for timestamp, values in sorted(buckets.items())
        if values
    ]


def get_overview(
    session: Session,
    *,
    window: str,
    tenant_id: str | None,
    assistant_id: str | None,
) -> dict[str, Any]:
    since, bucket_minutes = _resolve_window(window)
    assistant_call_keys = _assistant_call_keys(
        session,
        since=since,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    outcomes = _call_outcomes_subquery(
        since=since,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
    )
    tool_filters = _tool_completed_filters(
        since=since,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
    )

    if outcomes is None:
        total_calls = automated_resolution_calls = successful_handoff_calls = 0
        normal_completion_calls = unresolved_calls = 0
        avg_duration_ms = 0.0
        series_rows: list[tuple[datetime | None, int, int, int]] = []
    else:
        series_rows = session.execute(
            select(
                outcomes.c.first_event_at,
                outcomes.c.successful_handoff,
                outcomes.c.automatic_resolution,
                outcomes.c.normal_completion,
            )
            .select_from(outcomes)
            .order_by(outcomes.c.first_event_at.asc())
        ).all()
        summary = _summarize_call_outcomes(series_rows)
        total_calls = summary["total_calls"]
        successful_handoff_calls = summary["successful_handoff_calls"]
        automated_resolution_calls = summary["automated_resolution_calls"]
        normal_completion_calls = summary["normal_completion_calls"]
        unresolved_calls = summary["unresolved_calls"]

    successful_agent_calls = automated_resolution_calls + successful_handoff_calls
    # Compatibility fields retain the current agent-success semantics.
    success_calls = successful_agent_calls
    failed_calls = unresolved_calls
    handoff_calls = successful_handoff_calls

    if tool_filters:
        tool_totals = session.execute(
            select(
                func.count(CallEvent.id).label("tool_execution_count"),
                func.avg(CallEvent.duration_ms).label("avg_duration_ms"),
                func.sum(
                    case((CallEvent.error_code.in_(TECHNICAL_ERROR_CODES), 1), else_=0)
                ).label("technical_failure_events"),
            ).where(*tool_filters)
        ).one()
        tool_execution_count = int(tool_totals.tool_execution_count or 0)
        technical_failure_events = int(tool_totals.technical_failure_events or 0)
        avg_duration_ms = round(float(tool_totals.avg_duration_ms or 0.0), 2)
    else:
        tool_execution_count = technical_failure_events = 0

    series_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "calls": 0,
            "handoffs": 0,
            "successful_handoffs": 0,
            "automated_resolutions": 0,
            "normal_completions": 0,
            "unresolved_calls": 0,
        }
    )
    for created_at, successful_handoff, automatic_resolution, normal_completion in series_rows:
        created = _ensure_utc(created_at)
        if created is None:
            continue
        bucket = _floor_bucket(created, bucket_minutes).isoformat()
        series_map[bucket]["calls"] += 1
        handoff = bool(successful_handoff)
        automatic = bool(automatic_resolution) and not handoff
        normal = bool(normal_completion) and not handoff
        automatic = (bool(automatic_resolution) or normal) and not handoff
        if handoff:
            series_map[bucket]["successful_handoffs"] += 1
        if automatic:
            series_map[bucket]["automated_resolutions"] += 1
        if normal:
            series_map[bucket]["normal_completions"] += 1
        if handoff or not automatic:
            series_map[bucket]["unresolved_calls"] += 1

    for values in series_map.values():
        values["handoffs"] = values["successful_handoffs"]

    series = [
        {"timestamp": timestamp, **values}
        for timestamp, values in sorted(series_map.items())
    ]

    return {
        "metric_version": METRIC_VERSION,
        "window": window,
        "since": since.isoformat(),
        "tenant_id": tenant_id,
        "assistant_id": assistant_id,
        "kpis": {
            "total_calls": total_calls,
            "success_calls": success_calls,
            "failed_calls": failed_calls,
            "handoff_calls": handoff_calls,
            "avg_duration_ms": avg_duration_ms,
            "automated_resolution_calls": automated_resolution_calls,
            "successful_handoff_calls": successful_handoff_calls,
            "normal_completion_calls": normal_completion_calls,
            "successful_agent_calls": successful_agent_calls,
            "agent_success_rate_pct": round(
                (successful_agent_calls / total_calls) * 100.0, 2
            ) if total_calls else 0.0,
            "unresolved_calls": unresolved_calls,
            "technical_failure_events": technical_failure_events,
            "tool_execution_count": tool_execution_count,
            "technical_failure_rate_pct": round(
                (technical_failure_events / tool_execution_count) * 100.0, 2
            ) if tool_execution_count else 0.0,
        },
        "series": series,
    }


def get_costs(
    session: Session,
    *,
    window: str,
    tenant_id: str | None,
    assistant_id: str | None,
) -> dict[str, Any]:
    since, bucket_minutes = _resolve_window(window)
    until = datetime.now(timezone.utc)
    filters = [
        VapiCallCost.started_at >= since,
        VapiCallCost.started_at < until,
        VapiCallCost.tenant_id.is_not(None),
        VapiCallCost.is_verified.is_(True),
    ]
    if tenant_id:
        filters.append(VapiCallCost.tenant_id == tenant_id)
    if assistant_id:
        filters.append(VapiCallCost.assistant_id == assistant_id)

    summary = session.execute(
        select(
            func.count(VapiCallCost.call_id).label("vapi_calls"),
            func.count(VapiCallCost.cost_total_usd).label("calls_with_cost"),
            func.sum(VapiCallCost.cost_total_usd).label("total_cost_usd"),
            func.sum(VapiCallCost.cost_total_brl).label("total_cost_brl"),
            func.count(VapiCallCost.duration_seconds).label("duration_count"),
            func.sum(VapiCallCost.duration_seconds).label("total_duration_seconds"),
            func.avg(VapiCallCost.duration_seconds).label("avg_duration_seconds"),
            func.sum(
                case(
                    (
                        and_(
                            VapiCallCost.cost_total_usd.is_not(None),
                            VapiCallCost.cost_total_brl.is_(None),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("missing_rate_calls"),
            func.sum(case((VapiCallCost.fx_is_provisional.is_(True), 1), else_=0)).label(
                "provisional_calls"
            ),
            func.max(VapiCallCost.fx_rate_date).label("last_rate_date"),
        ).where(*filters)
    ).one()
    vapi_calls = int(summary.vapi_calls or 0)
    calls_with_cost = int(summary.calls_with_cost or 0)
    total_cost_usd = round(float(summary.total_cost_usd or 0.0), 6)
    missing_rate_calls = int(summary.missing_rate_calls or 0)
    total_cost_brl = (
        round(float(summary.total_cost_brl or 0.0), 2)
        if missing_rate_calls == 0
        else None
    )
    avg_cost_per_call = (
        round(total_cost_usd / calls_with_cost, 6) if calls_with_cost else 0.0
    )
    avg_cost_per_call_brl = (
        round(total_cost_brl / calls_with_cost, 2)
        if total_cost_brl is not None and calls_with_cost
        else None
    )
    duration_count = int(summary.duration_count or 0)
    total_duration_seconds = round(float(summary.total_duration_seconds or 0.0), 2)
    avg_duration_seconds = round(float(summary.avg_duration_seconds or 0.0), 2)
    rows = session.execute(
        select(
            VapiCallCost.started_at,
            VapiCallCost.synced_at,
            VapiCallCost.cost_total_usd,
            VapiCallCost.cost_total_brl,
            VapiCallCost.duration_seconds,
            VapiCallCost.fx_is_provisional,
        )
        .where(*filters)
        .order_by(VapiCallCost.started_at.asc())
    ).all()

    series_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "cost_usd": 0.0,
            "cost_brl": 0.0,
            "missing_brl": 0,
            "duration_seconds": 0.0,
            "provisional_calls": 0,
        }
    )
    for (
        started_at,
        synced_at,
        cost_total_usd,
        cost_total_brl,
        duration_seconds,
        fx_is_provisional,
    ) in rows:
        point_time = _ensure_utc(started_at) or _ensure_utc(synced_at)
        if point_time is None:
            continue
        bucket = _floor_bucket(point_time, bucket_minutes).isoformat()
        series_map[bucket]["calls"] += 1
        series_map[bucket]["cost_usd"] += float(cost_total_usd or 0.0)
        if cost_total_usd is not None and cost_total_brl is None:
            series_map[bucket]["missing_brl"] += 1
        else:
            series_map[bucket]["cost_brl"] += float(cost_total_brl or 0.0)
        series_map[bucket]["duration_seconds"] += float(duration_seconds or 0.0)
        series_map[bucket]["provisional_calls"] += int(bool(fx_is_provisional))

    series = [
        {
            "timestamp": timestamp,
            "calls": values["calls"],
            "cost_usd": round(values["cost_usd"], 6),
            "cost_brl": (
                None if values["missing_brl"] else round(values["cost_brl"], 2)
            ),
            "duration_seconds": round(values["duration_seconds"], 2),
            "provisional_calls": values["provisional_calls"],
        }
        for timestamp, values in sorted(series_map.items())
    ]

    component_columns = {
        "transport": VapiCallCost.cost_transport_usd,
        "stt": VapiCallCost.cost_stt_usd,
        "llm": VapiCallCost.cost_llm_usd,
        "tts": VapiCallCost.cost_tts_usd,
        "vapi": VapiCallCost.cost_vapi_usd,
        "analysis": VapiCallCost.cost_analysis_usd,
        "adjustment_and_other": VapiCallCost.cost_other_usd,
    }
    component_row = session.execute(
        select(
            *[
                func.sum(column).label(name)
                for name, column in component_columns.items()
            ]
        ).where(*filters)
    ).one()
    adjustment_calls = int(
        session.execute(
            select(func.count(VapiCallCost.call_id)).where(
                *filters,
                VapiCallCost.cost_other_usd.is_not(None),
                VapiCallCost.cost_other_usd != 0,
            )
        ).scalar()
        or 0
    )
    breakdown = []
    for name in component_columns:
        cost_usd = round(float(getattr(component_row, name) or 0.0), 6)
        breakdown.append(
            {
                "category": name,
                "cost_usd": cost_usd,
                "share_pct": (
                    round((cost_usd / total_cost_usd) * 100.0, 2)
                    if total_cost_usd
                    else 0.0
                ),
            }
        )

    event_filters = [CallEvent.created_at >= since, CallEvent.created_at < until]
    if tenant_id:
        event_filters.append(CallEvent.tenant_id == tenant_id)
    operational_calls = int(
        session.execute(
            select(func.count(func.distinct(CallEvent.call_id))).where(*event_filters)
        ).scalar()
        or 0
    )
    cost_call_ids = select(VapiCallCost.call_id).where(*filters)
    linked_operational_calls = int(
        session.execute(
            select(func.count(func.distinct(CallEvent.call_id))).where(
                *event_filters,
                CallEvent.call_id.in_(cost_call_ids),
            )
        ).scalar()
        or 0
    )

    return {
        "window": window,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "tenant_id": tenant_id,
        "assistant_id": assistant_id,
        "summary": {
            "total_cost_usd": total_cost_usd,
            "total_cost_brl": total_cost_brl,
            "vapi_calls": vapi_calls,
            "calls_with_cost": calls_with_cost,
            "calls_without_cost": max(0, vapi_calls - calls_with_cost),
            "coverage_pct": (
                round((calls_with_cost / vapi_calls) * 100.0, 2) if vapi_calls else 0.0
            ),
            "avg_cost_per_call_usd": avg_cost_per_call,
            "avg_cost_per_call_brl": avg_cost_per_call_brl,
            "calls_with_duration": duration_count,
            "total_duration_seconds": total_duration_seconds,
            "avg_duration_seconds": avg_duration_seconds,
        },
        "fx": {
            "source": "BCB_PTAX",
            "basis": "closing_sale_rate_on_call_date",
            "complete": missing_rate_calls == 0,
            "provisional_calls": int(summary.provisional_calls or 0),
            "missing_rate_calls": missing_rate_calls,
            "last_rate_date": (
                summary.last_rate_date.isoformat() if summary.last_rate_date else None
            ),
        },
        "reconciliation": {
            "operational_calls": operational_calls,
            "linked_operational_calls": linked_operational_calls,
            "linkage_coverage_pct": (
                round((linked_operational_calls / operational_calls) * 100.0, 2)
                if operational_calls
                else 0.0
            ),
            "component_adjustment_calls": adjustment_calls,
        },
        "breakdown": breakdown,
        "series": series,
    }


def get_tools(
    session: Session,
    *,
    window: str,
    tenant_id: str | None,
    assistant_id: str | None,
) -> dict[str, Any]:
    since, _ = _resolve_window(window)
    assistant_call_keys = _assistant_call_keys(
        session,
        since=since,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )

    filters = _tool_completed_filters(
        since=since,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
    )
    if not filters:
        return {
            "metric_version": METRIC_VERSION,
            "window": window,
            "since": since.isoformat(),
            "tenant_id": tenant_id,
            "assistant_id": assistant_id,
            "items": [],
        }

    summary_stmt = (
        select(
            CallEvent.tool_name.label("tool_name"),
            func.count(CallEvent.id).label("total_calls"),
            func.sum(case((CallEvent.ok.is_(True), 1), else_=0)).label("success_calls"),
            func.sum(case((CallEvent.ok.is_(False), 1), else_=0)).label("failed_calls"),
            func.sum(
                case((CallEvent.error_code.in_(TECHNICAL_ERROR_CODES), 1), else_=0)
            ).label("technical_failure_events"),
            func.sum(case((CallEvent.final_state == "TRANSFERIDA_HUMANO", 1), else_=0)).label(
                "handoff_calls"
            ),
            func.avg(CallEvent.duration_ms).label("avg_duration_ms"),
            func.count(func.distinct(CallEvent.call_id)).label("unique_calls"),
        )
        .where(*filters)
        .group_by(CallEvent.tool_name)
    )

    tools: list[dict[str, Any]] = []
    for item in session.execute(summary_stmt).all():
        tool_name = item.tool_name or "unknown"
        total_calls = int(item.total_calls or 0)
        unique_calls = int(item.unique_calls or 0)
        avg_duration = round(float(item.avg_duration_ms or 0.0), 2)
        failure_rate = (
            round((int(item.failed_calls or 0) / total_calls) * 100.0, 2)
            if total_calls
            else 0.0
        )
        technical_failure_events = int(item.technical_failure_events or 0)
        tools.append(
            {
                "tool_name": tool_name,
                "total_calls": total_calls,
                "success_calls": int(item.success_calls or 0),
                "failed_calls": int(item.failed_calls or 0),
                "handoff_calls": int(item.handoff_calls or 0),
                "avg_duration_ms": avg_duration,
                "failure_rate_pct": failure_rate,
                "technical_failure_events": technical_failure_events,
                "technical_failure_rate_pct": (
                    round((technical_failure_events / total_calls) * 100.0, 2)
                    if total_calls
                    else 0.0
                ),
                "unique_calls": unique_calls,
            }
        )

    tools.sort(key=lambda item: item["total_calls"], reverse=True)
    return {
        "metric_version": METRIC_VERSION,
        "window": window,
        "since": since.isoformat(),
        "tenant_id": tenant_id,
        "assistant_id": assistant_id,
        "items": tools,
    }


def _sync_snapshot(session: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    state = session.get(OpsSyncState, "vapi_costs")
    last_synced_at = (
        _ensure_utc(state.last_successful_run_at)
        if state and state.last_successful_run_at
        else (_ensure_utc(state.last_synced_at) if state and state.last_synced_at else None)
    )
    freshness_seconds = (
        int((now - last_synced_at).total_seconds()) if last_synced_at is not None else None
    )
    if freshness_seconds is None:
        freshness_state = "unknown"
    elif freshness_seconds <= SYNC_FRESH_SECONDS:
        freshness_state = "fresh"
    elif freshness_seconds <= SYNC_DELAY_SECONDS:
        freshness_state = "delayed"
    else:
        freshness_state = "stale"
    return {
        "last_synced_at": last_synced_at.isoformat() if last_synced_at is not None else None,
        "freshness_seconds": freshness_seconds,
        "freshness_state": freshness_state,
        "last_error": state.last_error if state else None,
        "consecutive_failures": int(state.consecutive_failures or 0) if state else 0,
        "last_run_stats": state.last_run_stats_json if state else None,
    }


def get_health(
    session: Session,
    *,
    window: str,
    tenant_id: str | None,
    assistant_id: str | None,
) -> dict[str, Any]:
    since, _ = _resolve_window(window)
    assistant_call_keys = _assistant_call_keys(
        session,
        since=since,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    overview = get_overview(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    costs = get_costs(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    tools = get_tools(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    sync = _sync_snapshot(session)

    repeated_filters = [ToolBusinessErrorAttempt.updated_at >= since]
    if tenant_id:
        repeated_filters.append(ToolBusinessErrorAttempt.tenant_id == tenant_id)
    if assistant_call_keys is not None:
        if not assistant_call_keys:
            repeated_business_errors = 0
        else:
            _apply_call_key_filter(
                repeated_filters,
                tenant_column=ToolBusinessErrorAttempt.tenant_id,
                call_column=ToolBusinessErrorAttempt.call_id,
                tenant_id=tenant_id,
                call_keys_filter=assistant_call_keys,
            )
            repeated_business_errors = int(
                session.execute(
                    select(func.sum(ToolBusinessErrorAttempt.attempts - 1)).where(
                        *repeated_filters, ToolBusinessErrorAttempt.attempts > 1
                    )
                ).scalar()
                or 0
            )
    else:
        repeated_business_errors = int(
            session.execute(
                select(func.sum(ToolBusinessErrorAttempt.attempts - 1)).where(
                    *repeated_filters, ToolBusinessErrorAttempt.attempts > 1
                )
            ).scalar()
            or 0
        )

    idempotency_filters = _event_filters(
        since=since,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
        event_type="idempotency_hit",
    )
    idempotency_hits = (
        int(session.execute(select(func.count(CallEvent.id)).where(*idempotency_filters)).scalar() or 0)
        if idempotency_filters
        else 0
    )

    total_calls = int(overview["kpis"]["total_calls"])
    tool_execution_count = sum(int(item["total_calls"]) for item in tools["items"])
    technical_failure_events = sum(
        int(item["technical_failure_events"]) for item in tools["items"]
    )
    technical_failure_rate = (
        round((technical_failure_events / tool_execution_count) * 100.0, 2)
        if tool_execution_count
        else 0.0
    )
    coverage_pct = float(costs["summary"]["coverage_pct"])

    if total_calls == 0:
        health_state = "no_data"
    elif (
        sync["freshness_state"] == "stale"
        or technical_failure_rate >= 25
        or coverage_pct < 50
    ):
        health_state = "critical"
    elif (
        sync["freshness_state"] == "delayed"
        or technical_failure_rate >= 10
        or coverage_pct < 80
        or idempotency_hits > 0
    ):
        health_state = "warning"
    else:
        health_state = "stable"

    top_degrading_tools = sorted(
        tools["items"],
        key=lambda item: (
            float(item["technical_failure_rate_pct"]),
            int(item["technical_failure_events"]),
            int(item["total_calls"]),
        ),
        reverse=True,
    )[:3]

    return {
        "metric_version": METRIC_VERSION,
        "window": window,
        "since": since.isoformat(),
        "tenant_id": tenant_id,
        "assistant_id": assistant_id,
        "health_state": health_state,
        "sync": sync,
        "counters": {
            "total_calls": total_calls,
            "vapi_calls": int(costs["summary"]["vapi_calls"]),
            "failed_calls": int(overview["kpis"]["failed_calls"]),
            "handoff_calls": int(overview["kpis"]["handoff_calls"]),
            "technical_failure_events": technical_failure_events,
            "technical_failure_rate_pct": technical_failure_rate,
            "tool_execution_count": tool_execution_count,
            "calls_with_cost": int(costs["summary"]["calls_with_cost"]),
            "calls_without_cost": int(costs["summary"]["calls_without_cost"]),
            "repeated_business_errors": repeated_business_errors,
            "idempotency_hits": idempotency_hits,
            "coverage_pct": coverage_pct,
        },
        "top_degrading_tools": top_degrading_tools,
    }


def get_resilience(
    session: Session,
    *,
    window: str,
    tenant_id: str | None,
    assistant_id: str | None,
) -> dict[str, Any]:
    since, bucket_minutes = _resolve_window(window)
    until = datetime.now(timezone.utc)
    assistant_call_keys = _assistant_call_keys(
        session,
        since=since,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    overview = get_overview(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    tools = get_tools(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    health = get_health(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)

    quality_filters = [
        VapiCallCost.started_at >= since,
        VapiCallCost.started_at < until,
        VapiCallCost.tenant_id.is_not(None),
        VapiCallCost.is_verified.is_(True),
    ]
    if tenant_id:
        quality_filters.append(VapiCallCost.tenant_id == tenant_id)
    if assistant_id:
        quality_filters.append(VapiCallCost.assistant_id == assistant_id)
    metrics_available = (
        VapiCallCost.turn_latency_average_ms.is_not(None)
        | VapiCallCost.assistant_interruptions.is_not(None)
    )
    quality_summary = session.execute(
        select(
            func.count(case((metrics_available, VapiCallCost.call_id))).label("calls_with_metrics"),
            func.avg(VapiCallCost.turn_latency_average_ms).label("average_turn_latency_ms"),
            func.sum(VapiCallCost.assistant_interruptions).label("total_assistant_interruptions"),
            func.count(
                case(
                    (VapiCallCost.assistant_interruptions >= 1, VapiCallCost.call_id),
                )
            ).label("calls_with_assistant_interruptions"),
        ).where(*quality_filters)
    ).one()
    quality_rows = session.execute(
        select(
            VapiCallCost.started_at,
            VapiCallCost.turn_latency_average_ms,
            VapiCallCost.assistant_interruptions,
        ).where(*quality_filters)
    ).all()

    search_rows = _search_event_rows(
        session,
        since=since,
        until=until,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
    )
    search_funnel = {
        "attempted_calls": len(_event_call_keys(search_rows, event_types={SEARCH_ATTEMPT_EVENT_TYPE})),
        "blocked_calls": len(_event_call_keys(search_rows, event_types={SEARCH_BLOCKED_EVENT_TYPE})),
        "upstream_started_calls": len(
            _event_call_keys(search_rows, event_types={SEARCH_UPSTREAM_STARTED_EVENT_TYPE})
        ),
        "completed_calls": len(_event_call_keys(search_rows, event_types={SEARCH_COMPLETED_EVENT_TYPE})),
        "provider_result_calls": len(
            _event_call_keys(
                search_rows,
                event_types={SEARCH_COMPLETED_EVENT_TYPE, SEARCH_RESULT_REUSED_EVENT_TYPE},
                predicate=lambda _error_code, payload: isinstance(payload.get("provider_count"), (int, float))
                and not isinstance(payload.get("provider_count"), bool)
                and payload["provider_count"] > 0,
            )
        ),
        "reused_result_calls": len(_event_call_keys(search_rows, event_types={SEARCH_RESULT_REUSED_EVENT_TYPE})),
    }

    def block_category(error_code: str | None, payload: dict) -> str | None:
        if error_code == "USER_TURN_REQUIRED":
            return "waiting_for_new_turn"
        return {
            "collect_cpf": "cpf",
            "collect_cidade": "city",
            "collect_especialidade": "specialty",
        }.get(payload.get("recovery_action"))

    slot_blocks = {
        category: len(
            _event_call_keys(
                search_rows,
                event_types={SEARCH_BLOCKED_EVENT_TYPE},
                predicate=lambda error_code, payload, category=category: block_category(error_code, payload)
                == category,
            )
        )
        for category in ("cpf", "city", "specialty", "waiting_for_new_turn")
    }
    upstream_failures = {
        category: len(
            _event_call_keys(
                search_rows,
                event_types={SEARCH_FAILED_EVENT_TYPE},
                predicate=lambda error_code, _payload, code=code: error_code == code,
            )
        )
        for code, category in UPSTREAM_FAILURE_KEYS.items()
    }
    handoff_flow = {
        "recommendations": len(
            _event_call_keys(search_rows, event_types={SEARCH_HANDOFF_RECOMMENDED_EVENT_TYPE})
        ),
        "native_transfers": len(
            _event_call_keys(search_rows, event_types={NATIVE_HANDOFF_EVENT_TYPE})
        ),
    }

    failed_filters = _event_filters(
        since=since,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
        event_type="tool_completed",
        ok=False,
    )
    failed_rows = (
        [(created_at, 1) for created_at in session.execute(select(CallEvent.created_at).where(*failed_filters)).scalars().all()]
        if failed_filters
        else []
    )
    technical_failure_filters = _tool_completed_filters(
        since=since,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
    )
    technical_failure_rows = (
        [
            (created_at, 1)
            for created_at in session.execute(
                select(CallEvent.created_at).where(
                    *technical_failure_filters,
                    CallEvent.error_code.in_(TECHNICAL_ERROR_CODES),
                )
            ).scalars().all()
        ]
        if technical_failure_filters
        else []
    )
    idempotency_filters = _event_filters(
        since=since,
        tenant_id=tenant_id,
        call_keys_filter=assistant_call_keys,
        event_type="idempotency_hit",
    )
    idempotency_rows = (
        [(created_at, 1) for created_at in session.execute(select(CallEvent.created_at).where(*idempotency_filters)).scalars().all()]
        if idempotency_filters
        else []
    )

    attempt_filters = [ToolBusinessErrorAttempt.updated_at >= since]
    if tenant_id:
        attempt_filters.append(ToolBusinessErrorAttempt.tenant_id == tenant_id)
    if assistant_call_keys is not None:
        if not assistant_call_keys:
            business_series_rows: list[tuple[datetime | None, int]] = []
            business_distribution_rows: list[tuple[str | None, int, int]] = []
        else:
            _apply_call_key_filter(
                attempt_filters,
                tenant_column=ToolBusinessErrorAttempt.tenant_id,
                call_column=ToolBusinessErrorAttempt.call_id,
                tenant_id=tenant_id,
                call_keys_filter=assistant_call_keys,
            )
            business_series_rows = session.execute(
                select(
                    ToolBusinessErrorAttempt.updated_at,
                    ToolBusinessErrorAttempt.attempts,
                ).where(*attempt_filters, ToolBusinessErrorAttempt.attempts > 1)
            ).all()
            business_distribution_rows = session.execute(
                select(
                    ToolBusinessErrorAttempt.tool_name,
                    func.sum(ToolBusinessErrorAttempt.attempts - 1).label("retries"),
                    func.count(ToolBusinessErrorAttempt.id).label("scopes"),
                )
                .where(*attempt_filters)
                .group_by(ToolBusinessErrorAttempt.tool_name)
            ).all()
    else:
        business_series_rows = session.execute(
            select(
                ToolBusinessErrorAttempt.updated_at,
                ToolBusinessErrorAttempt.attempts,
            ).where(*attempt_filters, ToolBusinessErrorAttempt.attempts > 1)
        ).all()
        business_distribution_rows = session.execute(
            select(
                ToolBusinessErrorAttempt.tool_name,
                func.sum(ToolBusinessErrorAttempt.attempts - 1).label("retries"),
                func.count(ToolBusinessErrorAttempt.id).label("scopes"),
            )
            .where(*attempt_filters)
            .group_by(ToolBusinessErrorAttempt.tool_name)
        ).all()

    top_failure_tools = sorted(
        tools["items"],
        key=lambda item: (
            float(item["technical_failure_rate_pct"]),
            int(item["technical_failure_events"]),
            int(item["total_calls"]),
        ),
        reverse=True,
    )[:5]
    top_handoff_tools = sorted(
        tools["items"],
        key=lambda item: (int(item["handoff_calls"]), int(item["total_calls"])),
        reverse=True,
    )[:5]
    business_error_tools = [
        {
            "tool_name": tool_name or "unknown",
            "retries": int(retries or 0),
            "scopes": int(scopes or 0),
        }
        for tool_name, retries, scopes in business_distribution_rows
    ]
    business_error_tools.sort(key=lambda item: (item["retries"], item["scopes"]), reverse=True)

    return {
        "metric_version": METRIC_VERSION,
        "window": window,
        "since": since.isoformat(),
        "tenant_id": tenant_id,
        "assistant_id": assistant_id,
        "health_state": health["health_state"],
        "sync": health["sync"],
        "summary": {
            "total_calls": int(overview["kpis"]["total_calls"]),
            "failed_calls": int(overview["kpis"]["failed_calls"]),
            "handoff_calls": int(overview["kpis"]["handoff_calls"]),
            "technical_failure_events": int(
                health["counters"]["technical_failure_events"]
            ),
            "technical_failure_rate_pct": float(
                health["counters"]["technical_failure_rate_pct"]
            ),
            "repeated_business_errors": int(health["counters"]["repeated_business_errors"]),
            "idempotency_hits": int(health["counters"]["idempotency_hits"]),
        },
        "search_funnel": search_funnel,
        "slot_blocks": slot_blocks,
        "upstream_failures": upstream_failures,
        "handoff_flow": handoff_flow,
        "voice_quality": {
            "calls_with_metrics": int(quality_summary.calls_with_metrics or 0),
            "average_turn_latency_ms": (
                round(float(quality_summary.average_turn_latency_ms), 2)
                if quality_summary.average_turn_latency_ms is not None
                else None
            ),
            "total_assistant_interruptions": int(
                quality_summary.total_assistant_interruptions or 0
            ),
            "calls_with_assistant_interruptions": int(
                quality_summary.calls_with_assistant_interruptions or 0
            ),
        },
        "series": {
            "failed_calls": _bucket_series_from_rows(failed_rows, bucket_minutes=bucket_minutes),
            "technical_failure_events": _bucket_series_from_rows(
                technical_failure_rows,
                bucket_minutes=bucket_minutes,
            ),
            "idempotency_hits": _bucket_series_from_rows(idempotency_rows, bucket_minutes=bucket_minutes),
            "repeated_business_errors": _bucket_series_from_rows(
                [(updated_at, max(int(attempts or 0) - 1, 0)) for updated_at, attempts in business_series_rows],
                bucket_minutes=bucket_minutes,
            ),
            "blocks": _distinct_event_series(
                search_rows,
                bucket_minutes=bucket_minutes,
                event_types={SEARCH_BLOCKED_EVENT_TYPE},
            ),
            "successes": _distinct_event_series(
                search_rows,
                bucket_minutes=bucket_minutes,
                event_types={SEARCH_COMPLETED_EVENT_TYPE, SEARCH_RESULT_REUSED_EVENT_TYPE},
            ),
            "external_failures": _distinct_event_series(
                search_rows,
                bucket_minutes=bucket_minutes,
                event_types={SEARCH_FAILED_EVENT_TYPE},
                predicate=lambda error_code, _payload: error_code in UPSTREAM_FAILURE_KEYS,
            ),
            "turn_latency_average_ms": _bucket_average_series_from_rows(
                [(started_at, latency) for started_at, latency, _interruptions in quality_rows],
                bucket_minutes=bucket_minutes,
            ),
            "assistant_interruptions": _bucket_series_from_rows(
                [
                    (started_at, interruptions)
                    for started_at, _latency, interruptions in quality_rows
                    if interruptions is not None
                ],
                bucket_minutes=bucket_minutes,
            ),
        },
        "top_failure_tools": top_failure_tools,
        "top_handoff_tools": top_handoff_tools,
        "business_error_tools": business_error_tools[:5],
    }
