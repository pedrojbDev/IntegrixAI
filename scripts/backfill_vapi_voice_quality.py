"""Backfill privacy-preserving Vapi voice-quality metrics for one tenant.

Seven-day rollout example (replace the tenant placeholder; no global fallback):
python scripts/backfill_vapi_voice_quality.py --tenant-id <tenant-id> \\
  --start 2026-09-02T00:00:00+00:00 --end 2026-09-09T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Sequence

from app.config import get_settings
from app.core.ops.cost_sync_service import VapiCostSyncService
from app.db import SessionLocal


def _utc_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--start", required=True, type=_utc_datetime, help="Inclusive ISO-8601 UTC bound")
    parser.add_argument("--end", required=True, type=_utc_datetime, help="Exclusive ISO-8601 UTC bound")
    args = parser.parse_args(argv)
    if not args.tenant_id.strip():
        parser.error("--tenant-id must not be empty")
    if args.end <= args.start:
        parser.error("--end must be after --start")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    if not settings.vapi_api_key:
        raise SystemExit("VAPI_API_KEY is required")

    session = SessionLocal()
    try:
        result = VapiCostSyncService(settings).backfill_voice_quality(
            session,
            tenant_id=args.tenant_id,
            start=args.start,
            end=args.end,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
