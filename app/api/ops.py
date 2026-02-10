from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import case, desc, func, select

from ..config import get_settings
from ..db import SessionLocal
from ..logging import get_logger
from ..models.call_event import CallEvent
from ..services.metrics import metrics_store

router = APIRouter(prefix="/ops", tags=["ops"])
log = get_logger()


def _db_disabled_response() -> dict:
    return {
        "enabled": False,
        "message": "DB auditing is disabled. Set DB_ENABLED=true to query audit endpoints.",
    }


@router.get("/baseline")
async def baseline_metrics():
    return metrics_store.snapshot()


@router.get("/audit/recent")
async def recent_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    tool_name: str | None = Query(default=None),
    call_id: str | None = Query(default=None),
    final_state: str | None = Query(default=None),
    ok: bool | None = Query(default=None),
    event_type: str | None = Query(default=None),
):
    settings = get_settings()
    if not settings.db_enabled:
        return _db_disabled_response()

    session = SessionLocal()
    try:
        stmt = select(CallEvent).order_by(desc(CallEvent.created_at)).limit(limit)

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
    except Exception as exc:
        log.error("ops_recent_failed", event_type="error", reason=str(exc))
        return {"enabled": True, "error": "Failed to load recent audit events"}
    finally:
        session.close()


@router.get("/audit/summary")
async def audit_summary(since_minutes: int | None = Query(default=None, ge=1, le=10080)):
    settings = get_settings()
    if not settings.db_enabled:
        return _db_disabled_response()

    session = SessionLocal()
    try:
        filters = []
        if since_minutes is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
            filters.append(CallEvent.created_at >= cutoff)

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
    except Exception as exc:
        log.error("ops_summary_failed", event_type="error", reason=str(exc))
        return {"enabled": True, "error": "Failed to load audit summary"}
    finally:
        session.close()
