from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Integer, func, select

from app.config import get_settings
from app.core.ops.cost_sync_service import VapiCostSyncService
from app.db import SessionLocal
from app.models.vapi_call_cost import VapiCallCost


USD_TOLERANCE = Decimal("0.000001")


def main() -> int:
    args = parse_args()
    start = datetime.combine(args.start, time.min, tzinfo=timezone.utc)
    end = datetime.combine(args.end, time.min, tzinfo=timezone.utc)
    if end <= start:
        raise SystemExit("--end must be after --start")

    settings = get_settings()
    if not settings.vapi_api_key:
        raise SystemExit("VAPI_API_KEY is required")
    service = VapiCostSyncService(settings)
    raw_calls = service._fetch_complete_range(
        start - timedelta(days=1),
        end + timedelta(days=1),
        "createdAt",
    )
    parsed = [
        item
        for raw in raw_calls
        if (item := service._parse_call(raw)) is not None
        and item.started_at is not None
        and start <= item.started_at.astimezone(timezone.utc) < end
        and item.tenant_id == args.tenant_id
        and (not args.assistant_id or item.assistant_id == args.assistant_id)
    ]
    vapi_known = [item for item in parsed if item.cost_total_usd is not None]
    vapi_total = sum(
        (item.cost_total_usd for item in vapi_known),
        Decimal("0"),
    )

    session = SessionLocal()
    try:
        filters = [
            VapiCallCost.started_at >= start,
            VapiCallCost.started_at < end,
            VapiCallCost.tenant_id == args.tenant_id,
            VapiCallCost.is_verified.is_(True),
        ]
        if args.assistant_id:
            filters.append(VapiCallCost.assistant_id == args.assistant_id)
        row = session.execute(
            select(
                func.count(VapiCallCost.call_id).label("calls"),
                func.count(VapiCallCost.cost_total_usd).label("known"),
                func.sum(VapiCallCost.cost_total_usd).label("total_usd"),
                func.sum(VapiCallCost.cost_total_brl).label("total_brl"),
                func.sum(
                    (VapiCallCost.cost_total_usd.is_not(None)
                    & VapiCallCost.cost_total_brl.is_(None)).cast(Integer)
                ).label("missing_fx"),
            ).where(*filters)
        ).one()
    finally:
        session.close()

    db_total = Decimal(row.total_usd or 0)
    delta = abs(vapi_total - db_total)
    result = {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "tenant_id": args.tenant_id,
        "assistant_id": args.assistant_id,
        "vapi": {
            "calls": len(parsed),
            "calls_with_cost": len(vapi_known),
            "total_usd": str(vapi_total),
        },
        "database": {
            "calls": int(row.calls or 0),
            "calls_with_cost": int(row.known or 0),
            "total_usd": str(db_total),
            "total_brl": str(row.total_brl) if row.total_brl is not None else None,
            "missing_fx": int(row.missing_fx or 0),
        },
        "delta_usd": str(delta),
        "within_tolerance": (
            len(parsed) == int(row.calls or 0)
            and len(vapi_known) == int(row.known or 0)
            and delta <= USD_TOLERANCE
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["within_tolerance"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile Vapi official costs with verified database rows."
    )
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat, help="Exclusive date")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--assistant-id")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
