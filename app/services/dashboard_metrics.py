from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..models.call_event import CallEvent
from ..models.vapi_call_cost import VapiCallCost

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
        select(CallEvent.call_id, func.max(CallEvent.created_at).label("max_created_at"))
        .where(*filters)
        .group_by(CallEvent.call_id)
        .subquery()
    )

    stmt = (
        select(CallEvent)
        .join(
            latest_per_call,
            and_(
                CallEvent.call_id == latest_per_call.c.call_id,
                CallEvent.created_at == latest_per_call.c.max_created_at,
            ),
        )
        .order_by(CallEvent.created_at.asc())
    )
    return list(session.execute(stmt).scalars().all())


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
    rows = _latest_tool_completed_rows(
        session, since=since, tenant_id=tenant_id, call_ids_filter=assistant_call_ids
    )

    total_calls = len(rows)
    success_calls = sum(1 for row in rows if row.final_state == "RESOLVIDA_AUTOMATICO")
    handoff_calls = sum(1 for row in rows if row.final_state == "TRANSFERIDA_HUMANO")
    failed_calls = total_calls - success_calls

    durations = [float(row.duration_ms) for row in rows if row.duration_ms is not None]
    avg_duration_ms = round(sum(durations) / len(durations), 2) if durations else 0.0

    series_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "handoffs": 0})
    for row in rows:
        created = _ensure_utc(row.created_at)
        if created is None:
            continue
        bucket = _floor_bucket(created, bucket_minutes).isoformat()
        series_map[bucket]["calls"] += 1
        if row.final_state == "TRANSFERIDA_HUMANO":
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

    stmt = select(VapiCallCost).where(VapiCallCost.synced_at >= since)
    if tenant_id:
        stmt = stmt.where(VapiCallCost.tenant_id == tenant_id)
    if assistant_id:
        stmt = stmt.where(VapiCallCost.assistant_id == assistant_id)

    rows = list(session.execute(stmt.order_by(VapiCallCost.synced_at.asc())).scalars().all())
    total_cost_usd = round(sum(float(row.cost_total_usd or 0.0) for row in rows), 6)
    call_count = len(rows)
    avg_cost_per_call = round(total_cost_usd / call_count, 6) if call_count else 0.0

    series_map: dict[str, dict[str, Any]] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0})
    for row in rows:
        point_time = _ensure_utc(row.started_at) or _ensure_utc(row.synced_at)
        if point_time is None:
            continue
        bucket = _floor_bucket(point_time, bucket_minutes).isoformat()
        series_map[bucket]["calls"] += 1
        series_map[bucket]["cost_usd"] += float(row.cost_total_usd or 0.0)

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

    events_stmt = select(CallEvent).where(
        CallEvent.event_type == "tool_completed",
        CallEvent.created_at >= since,
    )
    if tenant_id:
        events_stmt = events_stmt.where(CallEvent.tenant_id == tenant_id)
    if assistant_call_ids is not None:
        if not assistant_call_ids:
            return {
                "window": window,
                "since": since.isoformat(),
                "tenant_id": tenant_id,
                "assistant_id": assistant_id,
                "items": [],
            }
        events_stmt = events_stmt.where(CallEvent.call_id.in_(assistant_call_ids))
    events = list(session.execute(events_stmt).scalars().all())

    call_ids = sorted({event.call_id for event in events if event.call_id})
    costs_by_call: dict[str, float] = {}
    if call_ids:
        costs_stmt = select(VapiCallCost.call_id, VapiCallCost.cost_total_usd).where(
            VapiCallCost.call_id.in_(call_ids)
        )
        if tenant_id:
            costs_stmt = costs_stmt.where(VapiCallCost.tenant_id == tenant_id)
        for call_id, cost in session.execute(costs_stmt).all():
            costs_by_call[call_id] = float(cost or 0.0)

    by_tool: dict[str, dict[str, Any]] = {}
    for event in events:
        tool = event.tool_name or "unknown"
        item = by_tool.setdefault(
            tool,
            {
                "tool_name": tool,
                "total_calls": 0,
                "success_calls": 0,
                "failed_calls": 0,
                "handoff_calls": 0,
                "total_duration_ms": 0.0,
                "duration_count": 0,
                "call_ids": set(),
            },
        )
        item["total_calls"] += 1
        if event.ok is True:
            item["success_calls"] += 1
        if event.ok is False:
            item["failed_calls"] += 1
        if event.final_state == "TRANSFERIDA_HUMANO":
            item["handoff_calls"] += 1
        if event.duration_ms is not None:
            item["duration_count"] += 1
            item["total_duration_ms"] += float(event.duration_ms)
        if event.call_id:
            item["call_ids"].add(event.call_id)

    tools: list[dict[str, Any]] = []
    for item in by_tool.values():
        call_ids_for_tool = sorted(item["call_ids"])
        tool_cost = round(sum(costs_by_call.get(call_id, 0.0) for call_id in call_ids_for_tool), 6)
        unique_calls = len(call_ids_for_tool)
        avg_duration = (
            round(item["total_duration_ms"] / item["duration_count"], 2)
            if item["duration_count"]
            else 0.0
        )
        failure_rate = (
            round((item["failed_calls"] / item["total_calls"]) * 100.0, 2)
            if item["total_calls"]
            else 0.0
        )
        tools.append(
            {
                "tool_name": item["tool_name"],
                "total_calls": item["total_calls"],
                "success_calls": item["success_calls"],
                "failed_calls": item["failed_calls"],
                "handoff_calls": item["handoff_calls"],
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
