from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, func, select
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
    "90d": 129600,
}
WINDOW_BUCKET_MINUTES = {
    "15m": 1,
    "1h": 5,
    "24h": 60,
    "7d": 360,
    "15d": 1440,
    "30d": 1440,
    "90d": 1440,
}
SYNC_FRESH_SECONDS = 15 * 60
SYNC_DELAY_SECONDS = 60 * 60


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


def _assistant_call_ids(
    session: Session,
    *,
    since: datetime,
    tenant_id: str | None,
    assistant_id: str | None,
) -> set[str] | None:
    if not assistant_id:
        return None

    stmt = select(VapiCallCost.call_id).where(
        VapiCallCost.started_at >= since,
        VapiCallCost.assistant_id == assistant_id,
    )
    if tenant_id:
        stmt = stmt.where(VapiCallCost.tenant_id == tenant_id)
    rows = session.execute(stmt).scalars().all()
    return {row for row in rows if row}


def _latest_tool_completed_subquery(
    *,
    since: datetime,
    tenant_id: str | None,
    call_ids_filter: set[str] | None = None,
):
    filters = [CallEvent.event_type == "tool_completed", CallEvent.created_at >= since]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if call_ids_filter is not None:
        if not call_ids_filter:
            return None
        filters.append(CallEvent.call_id.in_(call_ids_filter))

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


def _event_filters(
    *,
    since: datetime,
    tenant_id: str | None,
    call_ids_filter: set[str] | None,
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
    if call_ids_filter is not None:
        if not call_ids_filter:
            return []
        filters.append(CallEvent.call_id.in_(call_ids_filter))
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


def get_overview(
    session: Session,
    *,
    window: str,
    tenant_id: str | None,
    assistant_id: str | None,
) -> dict[str, Any]:
    since, bucket_minutes = _resolve_window(window)
    assistant_call_ids = _assistant_call_ids(
        session,
        since=since,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    latest_events = _latest_tool_completed_subquery(
        since=since,
        tenant_id=tenant_id,
        call_ids_filter=assistant_call_ids,
    )

    if latest_events is None:
        total_calls = success_calls = handoff_calls = 0
        avg_duration_ms = 0.0
        series_rows: list[tuple[datetime | None, str | None]] = []
    else:
        totals = session.execute(
            select(
                func.count(latest_events.c.call_id).label("total_calls"),
                func.sum(
                    case((latest_events.c.final_state == "RESOLVIDA_AUTOMATICO", 1), else_=0)
                ).label("success_calls"),
                func.sum(
                    case((latest_events.c.final_state == "TRANSFERIDA_HUMANO", 1), else_=0)
                ).label("handoff_calls"),
                func.avg(latest_events.c.duration_ms).label("avg_duration_ms"),
            ).select_from(latest_events)
        ).one()
        total_calls = int(totals.total_calls or 0)
        success_calls = int(totals.success_calls or 0)
        handoff_calls = int(totals.handoff_calls or 0)
        avg_duration_ms = round(float(totals.avg_duration_ms or 0.0), 2)
        series_rows = session.execute(
            select(latest_events.c.created_at, latest_events.c.final_state)
            .select_from(latest_events)
            .order_by(latest_events.c.created_at.asc())
        ).all()

    failed_calls = total_calls - success_calls
    series_map: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "handoffs": 0})
    for created_at, final_state in series_rows:
        created = _ensure_utc(created_at)
        if created is None:
            continue
        bucket = _floor_bucket(created, bucket_minutes).isoformat()
        series_map[bucket]["calls"] += 1
        if final_state == "TRANSFERIDA_HUMANO":
            series_map[bucket]["handoffs"] += 1

    series = [
        {"timestamp": timestamp, "calls": values["calls"], "handoffs": values["handoffs"]}
        for timestamp, values in sorted(series_map.items())
    ]

    return {
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
    assistant_call_ids = _assistant_call_ids(
        session,
        since=since,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )

    filters = [CallEvent.event_type == "tool_completed", CallEvent.created_at >= since]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if assistant_call_ids is not None:
        if not assistant_call_ids:
            return {
                "window": window,
                "since": since.isoformat(),
                "tenant_id": tenant_id,
                "assistant_id": assistant_id,
                "items": [],
            }
        filters.append(CallEvent.call_id.in_(assistant_call_ids))

    summary_stmt = (
        select(
            CallEvent.tool_name.label("tool_name"),
            func.count(CallEvent.id).label("total_calls"),
            func.sum(case((CallEvent.ok.is_(True), 1), else_=0)).label("success_calls"),
            func.sum(case((CallEvent.ok.is_(False), 1), else_=0)).label("failed_calls"),
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
        tools.append(
            {
                "tool_name": tool_name,
                "total_calls": total_calls,
                "success_calls": int(item.success_calls or 0),
                "failed_calls": int(item.failed_calls or 0),
                "handoff_calls": int(item.handoff_calls or 0),
                "avg_duration_ms": avg_duration,
                "failure_rate_pct": failure_rate,
                "unique_calls": unique_calls,
            }
        )

    tools.sort(key=lambda item: item["total_calls"], reverse=True)
    return {
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
    assistant_call_ids = _assistant_call_ids(
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
    if assistant_call_ids is not None:
        if not assistant_call_ids:
            repeated_business_errors = 0
        else:
            repeated_filters.append(ToolBusinessErrorAttempt.call_id.in_(assistant_call_ids))
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
        call_ids_filter=assistant_call_ids,
        event_type="idempotency_hit",
    )
    idempotency_hits = (
        int(session.execute(select(func.count(CallEvent.id)).where(*idempotency_filters)).scalar() or 0)
        if idempotency_filters
        else 0
    )

    total_calls = int(overview["kpis"]["total_calls"])
    failure_rate = (
        round((int(overview["kpis"]["failed_calls"]) / total_calls) * 100.0, 2) if total_calls else 0.0
    )
    handoff_rate = (
        round((int(overview["kpis"]["handoff_calls"]) / total_calls) * 100.0, 2) if total_calls else 0.0
    )
    coverage_pct = float(costs["summary"]["coverage_pct"])

    if total_calls == 0:
        health_state = "no_data"
    elif (
        sync["freshness_state"] == "stale"
        or failure_rate >= 25
        or handoff_rate >= 40
        or coverage_pct < 50
    ):
        health_state = "critical"
    elif (
        sync["freshness_state"] == "delayed"
        or repeated_business_errors > 0
        or failure_rate >= 10
        or handoff_rate >= 20
        or coverage_pct < 80
        or idempotency_hits > 0
    ):
        health_state = "warning"
    else:
        health_state = "stable"

    top_degrading_tools = sorted(
        tools["items"],
        key=lambda item: (
            float(item["failure_rate_pct"]),
            int(item["handoff_calls"]),
            int(item["total_calls"]),
        ),
        reverse=True,
    )[:3]

    return {
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
    assistant_call_ids = _assistant_call_ids(
        session,
        since=since,
        tenant_id=tenant_id,
        assistant_id=assistant_id,
    )
    overview = get_overview(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    tools = get_tools(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    health = get_health(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)

    failed_filters = _event_filters(
        since=since,
        tenant_id=tenant_id,
        call_ids_filter=assistant_call_ids,
        event_type="tool_completed",
        ok=False,
    )
    failed_rows = (
        [(created_at, 1) for created_at in session.execute(select(CallEvent.created_at).where(*failed_filters)).scalars().all()]
        if failed_filters
        else []
    )
    idempotency_filters = _event_filters(
        since=since,
        tenant_id=tenant_id,
        call_ids_filter=assistant_call_ids,
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
    if assistant_call_ids is not None:
        if not assistant_call_ids:
            business_series_rows: list[tuple[datetime | None, int]] = []
            business_distribution_rows: list[tuple[str | None, int, int]] = []
        else:
            attempt_filters.append(ToolBusinessErrorAttempt.call_id.in_(assistant_call_ids))
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
        key=lambda item: (float(item["failure_rate_pct"]), int(item["total_calls"])),
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
            "repeated_business_errors": int(health["counters"]["repeated_business_errors"]),
            "idempotency_hits": int(health["counters"]["idempotency_hits"]),
        },
        "series": {
            "failed_calls": _bucket_series_from_rows(failed_rows, bucket_minutes=bucket_minutes),
            "idempotency_hits": _bucket_series_from_rows(idempotency_rows, bucket_minutes=bucket_minutes),
            "repeated_business_errors": _bucket_series_from_rows(
                [(updated_at, max(int(attempts or 0) - 1, 0)) for updated_at, attempts in business_series_rows],
                bucket_minutes=bucket_minutes,
            ),
        },
        "top_failure_tools": top_failure_tools,
        "top_handoff_tools": top_handoff_tools,
        "business_error_tools": business_error_tools[:5],
    }
