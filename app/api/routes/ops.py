from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import case, desc, func, select

from ...config import Settings, get_settings
from ...core.metrics.service import metrics_store
from ...core.ops.cost_sync_service import VapiCostSyncService
from ...core.ops.dashboard_service import (
    METRIC_VERSION,
    TECHNICAL_ERROR_CODES,
    get_costs,
    get_health,
    get_overview,
    get_resilience,
    get_tools,
)
from ...core.ops.report_service import build_operational_report_pdf
from ...core.security.ops import (
    OpsPrincipal,
    authorize_tenant_scope,
    record_auth_event,
    require_csrf,
    require_platform_admin,
    require_ready_principal,
)
from ...db import SessionLocal
from ...logging import get_logger
from ...models.call_event import CallEvent
from ...models.vapi_call_cost import VapiCallCost

router = APIRouter(prefix="/ops", tags=["ops"])
log = get_logger()


def _assert_db_enabled(settings: Settings) -> None:
    if not settings.db_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DB auditing is disabled. Set DB_ENABLED=true.",
        )


def _authorized_tenant(
    principal: OpsPrincipal,
    settings: Settings,
    tenant_id: str | None,
) -> str | None:
    try:
        resolved = authorize_tenant_scope(principal, tenant_id, settings)
    except HTTPException:
        log.warning(
            "ops_authorization_denied",
            event_type="ops_authorization",
            principal_id=principal.id,
            requested_tenant_id=tenant_id,
        )
        raise
    log.info(
        "ops_authorization_granted",
        event_type="ops_authorization",
        principal_id=principal.id,
        tenant_id=resolved,
        global_scope=resolved is None,
    )
    return resolved


def _admin_mutation(
    admin: OpsPrincipal = Depends(require_platform_admin),
    csrf: OpsPrincipal = Depends(require_csrf),
) -> OpsPrincipal:
    if admin.id != csrf.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Principal mismatch")
    return admin


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
        stmt = stmt.where(VapiCallCost.started_at >= since)
    rows = session.execute(stmt).scalars().all()
    return {row for row in rows if row}


@router.get("/baseline")
async def baseline_metrics(_: OpsPrincipal = Depends(require_platform_admin)):
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
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)

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
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)

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
                    "metric_version": METRIC_VERSION,
                    "enabled": True,
                    "window_minutes": since_minutes,
                    "totals": {
                        "total_calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                        "handoff_calls": 0,
                        "technical_failure_events": 0,
                        "avg_duration_ms": 0.0,
                    },
                    "per_tool": [],
                }
            filters.append(CallEvent.call_id.in_(assistant_call_ids))

        base_stmt = select(
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
        )
        if filters:
            base_stmt = base_stmt.where(*filters)
        totals = session.execute(base_stmt).one()

        per_tool_stmt = select(
            CallEvent.tool_name,
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
        ).group_by(CallEvent.tool_name)
        if filters:
            per_tool_stmt = per_tool_stmt.where(*filters)
        per_tool_rows = session.execute(per_tool_stmt).all()

        return {
            "metric_version": METRIC_VERSION,
            "enabled": True,
            "window_minutes": since_minutes,
            "totals": {
                "total_calls": totals.total_calls or 0,
                "success_calls": totals.success_calls or 0,
                "failed_calls": totals.failed_calls or 0,
                "handoff_calls": totals.handoff_calls or 0,
                "technical_failure_events": totals.technical_failure_events or 0,
                "avg_duration_ms": round(float(totals.avg_duration_ms or 0.0), 2),
            },
            "per_tool": [
                {
                    "tool_name": row.tool_name,
                    "total_calls": row.total_calls or 0,
                    "success_calls": row.success_calls or 0,
                    "failed_calls": row.failed_calls or 0,
                    "handoff_calls": row.handoff_calls or 0,
                    "technical_failure_events": row.technical_failure_events or 0,
                    "avg_duration_ms": round(float(row.avg_duration_ms or 0.0), 2),
                }
                for row in per_tool_rows
            ],
        }
    finally:
        session.close()


@router.post("/costs/sync")
async def sync_vapi_costs(
    settings: Settings = Depends(get_settings),
    admin: OpsPrincipal = Depends(_admin_mutation),
):
    _assert_db_enabled(settings)
    session = SessionLocal()
    try:
        result = VapiCostSyncService(settings).sync(session)
        record_auth_event(
            session,
            event_type="cost_sync_requested",
            success=True,
            user_id=admin.id,
            details={"processed": result.get("processed", 0)},
        )
        session.commit()
        log.info("ops_cost_sync_completed", event_type="ops_cost_sync", **result)
        return {"ok": True, "result": result}
    except Exception as exc:
        record_auth_event(
            session,
            event_type="cost_sync_requested",
            success=False,
            user_id=admin.id,
        )
        session.commit()
        log.error("ops_cost_sync_failed", event_type="error", message=str(exc))
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        session.close()


@router.get("/reports/operational.pdf")
async def download_operational_report(
    period_days: int = Query(default=30),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    """Export tenant-scoped operational aggregates as a PDF report."""
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)
    if period_days not in {7, 15, 30, 90}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="period_days deve ser 7, 15, 30 ou 90",
        )
    session = SessionLocal()
    try:
        if not settings.ops_cost_v2_enabled and not principal.is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Financial report is not enabled",
            )
        report_pdf = build_operational_report_pdf(
            session,
            period_days=period_days,
            tenant_id=tenant_id,
            assistant_id=assistant_id,
        )
        record_auth_event(
            session,
            event_type="report_exported",
            success=True,
            user_id=principal.id,
            tenant_id=tenant_id,
            details={"period_days": period_days, "assistant_filter": bool(assistant_id)},
        )
        session.commit()
        log.info(
            "ops_operational_report_exported",
            event_type="ops_report_export",
            tenant_id=tenant_id,
            assistant_id=assistant_id,
            period_days=period_days,
        )
        return Response(
            content=report_pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="relatorio-operacional-{period_days}-dias.pdf"'
                )
            },
        )
    finally:
        session.close()


@router.get("/dashboard/overview")
async def dashboard_overview(
    window: str = Query(default="24h", pattern="^(15m|1h|24h|7d)$"),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)
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
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)
    session = SessionLocal()
    try:
        payload = get_costs(
            session,
            window=window,
            tenant_id=tenant_id,
            assistant_id=assistant_id,
        )
        if settings.ops_cost_v2_enabled:
            payload["visibility"] = "enabled"
        elif principal.is_platform_admin:
            payload["visibility"] = "admin_preview"
        else:
            payload["visibility"] = "hidden"
            payload["summary"]["total_cost_usd"] = 0.0
            payload["summary"]["total_cost_brl"] = None
            payload["summary"]["avg_cost_per_call_usd"] = 0.0
            payload["summary"]["avg_cost_per_call_brl"] = None
            payload["breakdown"] = []
            for point in payload["series"]:
                point["cost_usd"] = 0.0
                point["cost_brl"] = None
        return payload
    finally:
        session.close()


@router.get("/dashboard/tools")
async def dashboard_tools(
    window: str = Query(default="24h", pattern="^(15m|1h|24h|7d)$"),
    tenant_id: str | None = Query(default=None),
    assistant_id: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)
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
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)
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
    principal: OpsPrincipal = Depends(require_ready_principal),
):
    _assert_db_enabled(settings)
    tenant_id = _authorized_tenant(principal, settings, tenant_id)
    session = SessionLocal()
    try:
        return get_resilience(session, window=window, tenant_id=tenant_id, assistant_id=assistant_id)
    finally:
        session.close()
