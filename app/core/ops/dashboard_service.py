from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from ...models.call_event import CallEvent
from ...models.vapi_call_cost import VapiCallCost

WINDOW_TO_MINUTES = {"15m": 15, "1h": 60, "24h": 1440, "7d": 10080}
WINDOW_BUCKET_MINUTES = {"15m": 1, "1h": 5, "24h": 60, "7d": 360}


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


def _latest_tool_completed_rows(
    session: Session,
    *,
    since: datetime,
    tenant_id: str | None,
    call_ids_filter: set[str] | None = None,
) -> list[CallEvent]:
    filters = [CallEvent.event_type == "tool_completed", CallEvent.created_at >= since]
    if tenant_id:
        filters.append(CallEvent.tenant_id == tenant_id)
    if call_ids_filter is not None:
        if not call_ids_filter:
            return []
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

    stmt = (
        select(CallEvent)
        .join(
            latest_per_call,
            and_(
                CallEvent.tenant_id == latest_per_call.c.tenant_id,
                CallEvent.call_id == latest_per_call.c.call_id,
                CallEvent.created_at == latest_per_call.c.max_created_at,
            ),
        )
        .order_by(CallEvent.created_at.asc())
    )
    return list(session.execute(stmt).scalars().all())


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


def _assistant_call_ids(
    session: Session, *, since: datetime, tenant_id: str | None, assistant_id: str | None
) -> set[str] | None:
    if not assistant_id:
        return None
    stmt = select(VapiCallCost.call_id).where(
        VapiCallCost.synced_at >= since,
        VapiCallCost.assistant_id == assistant_id,
    )
    if tenant_id:
        stmt = stmt.where(VapiCallCost.tenant_id == tenant_id)
    rows = session.execute(stmt).scalars().all()
    return {row for row in rows if row}


def get_overview(
    session: Session,
    *,
    window: str,
    tenant_id: str | None,
    assistant_id: str | None,
) -> dict[str, Any]:
    since, bucket_minutes = _resolve_window(window)
    assistant_call_ids = _assistant_call_ids(
        session, since=since, tenant_id=tenant_id, assistant_id=assistant_id
    )
    latest_events = _latest_tool_completed_subquery(
        since=since, tenant_id=tenant_id, call_ids_filter=assistant_call_ids
    )

    if latest_events is None:
        total_calls = success_calls = handoff_calls = 0
        avg_duration_ms = 0.0
        series_rows = []
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

    series_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "handoffs": 0})
    for created_at, final_state in series_rows:
        created = _ensure_utc(created_at)
        if created is None:
            continue
        bucket = _floor_bucket(created, bucket_minutes).isoformat()
        series_map[bucket]["calls"] += 1
        if final_state == "TRANSFERIDA_HUMANO":
            series_map[bucket]["handoffs"] += 1

    series = [
        {"timestamp": ts, "calls": values["calls"], "handoffs": values["handoffs"]}
        for ts, values in sorted(series_map.items())
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

    filters = [VapiCallCost.synced_at >= since]
    if tenant_id:
        filters.append(VapiCallCost.tenant_id == tenant_id)
    if assistant_id:
        filters.append(VapiCallCost.assistant_id == assistant_id)

    summary = session.execute(
        select(
            func.count(VapiCallCost.call_id).label("call_count"),
            func.sum(VapiCallCost.cost_total_usd).label("total_cost_usd"),
        ).where(*filters)
    ).one()
    call_count = int(summary.call_count or 0)
    total_cost_usd = round(float(summary.total_cost_usd or 0.0), 6)
    avg_cost_per_call = round(total_cost_usd / call_count, 6) if call_count else 0.0
    rows = session.execute(
        select(VapiCallCost.started_at, VapiCallCost.synced_at, VapiCallCost.cost_total_usd)
        .where(*filters)
        .order_by(VapiCallCost.synced_at.asc())
    ).all()

    series_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0})
    for started_at, synced_at, cost_total_usd in rows:
        point_time = _ensure_utc(started_at) or _ensure_utc(synced_at)
        if point_time is None:
            continue
        bucket = _floor_bucket(point_time, bucket_minutes).isoformat()
        series_map[bucket]["calls"] += 1
        series_map[bucket]["cost_usd"] += float(cost_total_usd or 0.0)

    series = [
        {
            "timestamp": ts,
            "calls": values["calls"],
            "cost_usd": round(values["cost_usd"], 6),
        }
        for ts, values in sorted(series_map.items())
    ]

    return {
        "window": window,
        "since": since.isoformat(),
        "tenant_id": tenant_id,
        "assistant_id": assistant_id,
        "summary": {
            "total_cost_usd": total_cost_usd,
            "calls_with_cost": call_count,
            "avg_cost_per_call_usd": avg_cost_per_call,
        },
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
        session, since=since, tenant_id=tenant_id, assistant_id=assistant_id
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

    distinct_call_tool = (
        select(
            CallEvent.tenant_id.label("tenant_id"),
            CallEvent.tool_name.label("tool_name"),
            CallEvent.call_id.label("call_id"),
        )
        .where(*filters)
        .distinct()
        .subquery()
    )
    costs_stmt = (
        select(
            distinct_call_tool.c.tool_name,
            func.sum(VapiCallCost.cost_total_usd).label("total_cost_usd"),
        )
        .join(
            VapiCallCost,
            and_(
                VapiCallCost.call_id == distinct_call_tool.c.call_id,
                VapiCallCost.tenant_id == distinct_call_tool.c.tenant_id,
            ),
        )
        .group_by(distinct_call_tool.c.tool_name)
    )
    costs_by_tool = {
        tool_name or "unknown": float(total_cost_usd or 0.0)
        for tool_name, total_cost_usd in session.execute(costs_stmt).all()
    }

    tools: list[dict[str, Any]] = []
    for item in session.execute(summary_stmt).all():
        tool_name = item.tool_name or "unknown"
        total_calls = int(item.total_calls or 0)
        unique_calls = int(item.unique_calls or 0)
        tool_cost = round(costs_by_tool.get(tool_name, 0.0), 6)
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
                "total_cost_usd": tool_cost,
                "avg_cost_per_call_usd": round(tool_cost / unique_calls, 6) if unique_calls else 0.0,
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
