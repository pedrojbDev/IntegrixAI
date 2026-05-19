from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, desc, func, select

from ...config import Settings, get_settings
from ...core.metrics.service import metrics_store
from ...core.ops.cost_sync_service import VapiCostSyncService
from ...core.ops.dashboard_service import (
    get_costs,
    get_health,
    get_overview,
    get_resilience,
    get_tools,
)
from ...core.security.ops import require_ops_token
from ...db import SessionLocal
from ...logging import get_logger
from ...models.call_event import CallEvent
from ...models.vapi_call_cost import VapiCallCost

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require_ops_token)])
log = get_logger()


def _assert_db_enabled(settings: Settings) -> None:
    if not settings.db_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DB auditing is disabled. Set DB_ENABLED=true.",
        )


def _assert_tenant_scope(settings: Settings, tenant_id: str | None) -> None:
    if settings.is_production and not settings.ops_allow_global_queries and not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id obrigatorio em producao",
        )


def _assistant_call_ids_for_filter(
    session,
    *,
    tenant_id: str | None,
    assistant_id: str | None,
    since: datetime | None = None,
) -> set[str] | None:
    if not assistant_id:
        return None

    stmt = select(VapiCallCost.call_id).where(VapiCallCost.assistant_id == assistant_id)
    if tenant_id:
        stmt = stmt.where(VapiCallCost.tenant_id == tenant_id)
    if since is not None:
        stmt = stmt.where(VapiCallCost.synced_at >= since)
    rows = session.execute(stmt).scalars().all()
    return {row for row in rows if row}


@router.get("/baseline")
async def baseline_metrics():
    return metrics_store.snapshot()


@router.get("/audit/recent")
async def recent_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    call_id: str | None = Query(default=None),
    final_state: str | None = Query(default=None),
    ok: bool | None = Query(default=None),
    event_type: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    _assert_db_enabled(settings)
    _assert_tenant_scope(settings, tenant_id)

    session = SessionLocal()
    try:
        stmt = select(CallEvent).order_by(desc(CallEvent.created_at)).limit(limit)
        if tenant_id:
            stmt = stmt.where(CallEvent.tenant_id == tenant_id)
        assistant_call_ids = _assistant_call_ids_for_filter(
            session,
            tenant_id=tenant_id,
            assistant_id=assistant_id,
        )
        if assistant_call_ids is not None:
            if not assistant_call_ids:
                return {"enabled": True, "count": 0, "items": []}
            stmt = stmt.where(CallEvent.call_id.in_(assistant_call_ids))
        if tool_name:
            stmt = stmt.where(CallEvent.tool_name == tool_name)
        if call_id:
            stmt = stmt.where(CallEvent.call_id == call_id)
        if final_state:
            stmt = stmt.where(CallEvent.final_state == final_state)
        if ok is not None:
            stmt = stmt.where(CallEvent.ok == ok)
        if event_type:
            stmt = stmt.where(CallEvent.event_type == event_type)

        rows = session.execute(stmt).scalars().all()
        return {
            "enabled": True,
            "count": len(rows),
            "items": [
                {
                    "id": row.id,
                    "tenant_id": row.tenant_id,
                    "call_id": row.call_id,
                    "tool_name": row.tool_name,
                    "event_type": row.event_type,
                    "final_state": row.final_state,
                    "ok": row.ok,
                    "duration_ms": row.duration_ms,
                    "error_code": row.error_code,
                    "created_at": row.created_at,
                    "payload_masked": row.payload_masked,
                }
                for row in rows
            ],
        }
    finally:
        session.close()


@router.get("/audit/summary")
async def audit_summary(
    since_minutes: int | None = Query(default=None, ge=1, le=10080),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    _assert_db_enabled(settings)
    _assert_tenant_scope(settings, tenant_id)

    session = SessionLocal()
    try:
        filters = []
        if tenant_id:
            filters.append(CallEvent.tenant_id == tenant_id)
        if since_minutes is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            filters.append(CallEvent.created_at >= cutoff)
        else:
            cutoff = None

        assistant_call_ids = _assistant_call_ids_for_filter(
            session,
            tenant_id=tenant_id,
            assistant_id=assistant_id,
            since=cutoff,
        )
        if assistant_call_ids is not None:
            if not assistant_call_ids:
                return {
                    "enabled": True,
                    "window_minutes": since_minutes,
                    "totals": {
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "handoff_calls": 0,
                        "avg_duration_ms": 0.0,
                    },
                    "per_tool": [],
                }
            filters.append(CallEvent.call_id.in_(assistant_call_ids))

        base_stmt = select(
            func.count(CallEvent.id).label("total_calls"),
            func.sum(case((CallEvent.ok.is_(True), 1), else_=0)).label("success_calls"),
            func.sum(case((CallEvent.ok.is_(False), 1), else_=0)).label("failed_calls"),
            func.sum(case((CallEvent.final_state == "TRANSFERIDA_HUMANO", 1), else_=0)).label(
                "handoff_calls"
            ),
            func.avg(CallEvent.duration_ms).label("avg_duration_ms"),
        )
        if filters:
            base_stmt = base_stmt.where(*filters)
        totals = session.execute(base_stmt).one()

        per_tool_stmt = select(
            CallEvent.tool_name,
            func.count(CallEvent.id).label("total_calls"),
            func.sum(case((CallEvent.ok.is_(True), 1), else_=0)).label("success_calls"),
            func.sum(case((CallEvent.ok.is_(False), 1), else_=0)).label("failed_calls"),
            func.sum(case((CallEvent.final_state == "TRANSFERIDA_HUMANO", 1), else_=0)).label(
                "handoff_calls"
            ),
            func.avg(CallEvent.duration_ms).label("avg_duration_ms"),
        ).group_by(CallEvent.tool_name)
        if filters:
            per_tool_stmt = per_tool_stmt.where(*filters)
        per_tool_rows = session.execute(per_tool_stmt).all()

        return {
            "enabled": True,
            "window_minutes": since_minutes,
            "totals": {
                "total_calls": totals.total_calls or 0,
                "success_calls": totals.success_calls or 0,
                "failed_calls": totals.failed_calls or 0,
                "handoff_calls": totals.handoff_calls or 0,
                "avg_duration_ms": round(float(totals.avg_duration_ms or 0.0), 2),
            },
            "per_tool": [
                {
                    "tool_name": row.tool_name,
                    "total_calls": row.total_calls or 0,
                    "success_calls": row.success_calls or 0,
                    "failed_calls": row.failed_calls or 0,
                    "handoff_calls": row.handoff_calls or 0,
                    "avg_duration_ms": round(float(row.avg_duration_ms or 0.0), 2),
                }
                for row in per_tool_rows
            ],
        }
    finally:
        session.close()


@router.post("/costs/sync")
async def sync_vapi_costs(settings: Settings = Depends(get_settings)):
    # TODO: add CSRF protection if the ops dashboard becomes externally exposed.
    _assert_db_enabled(settings)
    session = SessionLocal()
    try:
        result = VapiCostSyncService(settings).sync(session)
        log.info("ops_cost_sync_completed", event_type="ops_cost_sync", **result)
        return {"ok": True, "result": result}
    except Exception as exc:
        log.error("ops_cost_sync_failed", event_type="error", message=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        session.close()


@router.get("/dashboard/overview")
async def dashboard_overview(
    window: str = Query(default="24h", pattern="^(15m|1h|24h|7d)$"),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    _assert_db_enabled(settings)
    _assert_tenant_scope(settings, tenant_id)
    session = SessionLocal()
    try:
        return get_overview(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    finally:
        session.close()


@router.get("/dashboard/costs")
async def dashboard_costs(
    window: str = Query(default="24h", pattern="^(15m|1h|24h|7d)$"),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    _assert_db_enabled(settings)
    _assert_tenant_scope(settings, tenant_id)
    session = SessionLocal()
    try:
        return get_costs(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    finally:
        session.close()


@router.get("/dashboard/tools")
async def dashboard_tools(
    window: str = Query(default="24h", pattern="^(15m|1h|24h|7d)$"),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    _assert_db_enabled(settings)
    _assert_tenant_scope(settings, tenant_id)
    session = SessionLocal()
    try:
        return get_tools(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    finally:
        session.close()


@router.get("/dashboard/health")
async def dashboard_health(
    window: str = Query(default="24h", pattern="^(15m|1h|24h|7d)$"),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    _assert_db_enabled(settings)
    _assert_tenant_scope(settings, tenant_id)
    session = SessionLocal()
    try:
        return get_health(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    finally:
        session.close()


@router.get("/dashboard/resilience")
async def dashboard_resilience(
    window: str = Query(default="24h", pattern="^(15m|1h|24h|7d)$"),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
):
    _assert_db_enabled(settings)
    _assert_tenant_scope(settings, tenant_id)
    session = SessionLocal()
    try:
        return get_resilience(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    finally:
        session.close()
