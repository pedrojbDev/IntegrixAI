"""Rebuild Vapi terminal outcome events from retained sanitized cost snapshots."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.core.ops.cost_sync_service import VapiCostSyncService
from app.db import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        result = VapiCostSyncService(get_settings()).reconcile_saved_terminal_outcomes(
            session,
            tenant_id=args.tenant_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print(json.dumps({"tenant_id": args.tenant_id, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
