from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from app.db import SessionLocal
from app.platform.services.provider_resource_ownership import (
    ProviderResourceOwnershipError,
    ProviderResourceOwnershipRequest,
    SUPPORTED_RESOURCE_KINDS,
    register_provider_resource_ownership,
)


def main() -> int:
    args = parse_args()
    request = ProviderResourceOwnershipRequest(
        tenant_id=args.tenant_id,
        provider=args.provider,
        provider_org_id=args.provider_org_id,
        resource_kind=args.resource_kind,
        external_id=args.external_id,
        valid_from=args.valid_from,
        source=args.source,
        telephony_credential_id=args.telephony_credential_id,
    )
    session = SessionLocal()
    try:
        result = register_provider_resource_ownership(
            session,
            request,
            apply=args.apply,
        )
        if args.apply:
            session.commit()
        else:
            session.rollback()
    except ProviderResourceOwnershipError as exc:
        session.rollback()
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        session.close()
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Register a tenant ownership for a provider resource. "
            "The command is a dry-run unless --apply is supplied."
        )
    )
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--provider", default="vapi")
    parser.add_argument("--provider-org-id", required=True)
    parser.add_argument(
        "--resource-kind",
        required=True,
        choices=sorted(SUPPORTED_RESOURCE_KINDS),
    )
    parser.add_argument("--external-id", required=True)
    parser.add_argument("--telephony-credential-id")
    parser.add_argument(
        "--valid-from",
        type=_parse_datetime,
        default=datetime.now(timezone.utc),
        help="ISO-8601 timestamp; defaults to now in UTC",
    )
    parser.add_argument("--source", default="operational_validation")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the ownership. Without it, no database changes are committed.",
    )
    return parser.parse_args()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("--valid-from must include a timezone")
    return parsed.astimezone(timezone.utc)


if __name__ == "__main__":
    sys.exit(main())
