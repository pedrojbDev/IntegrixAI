from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ...config import Settings
from ...logging import get_logger
from ...models.ops_sync_state import OpsSyncState
from ...models.vapi_call_cost import VapiCallCost
from ..tenant.resolver import resolve_tenant_details, should_reject_tenant_resolution

log = get_logger()


@dataclass
class ParsedCallCost:
    call_id: str
    tenant_id: str
    to_number: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float | None
    assistant_id: str | None
    status: str | None
    cost_total_usd: float
    cost_breakdown_json: dict[str, Any]


class VapiCostSyncService:
    provider_key = "vapi_costs"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.vapi_base_url.rstrip("/")
        self.path = settings.vapi_calls_path

    def sync(self, session: Session) -> dict[str, Any]:
        if not self.settings.vapi_api_key:
            raise RuntimeError("VAPI_API_KEY not configured")

        state = session.get(OpsSyncState, self.provider_key)
        now = datetime.now(timezone.utc)
        if state and state.last_synced_at:
            cursor = state.last_synced_at.astimezone(timezone.utc) - timedelta(seconds=1)
        else:
            cursor = now - timedelta(minutes=self.settings.ops_cost_sync_lookback_minutes)
        initial_cursor = cursor

        processed = 0
        created = 0
        updated = 0
        skipped = 0
        max_seen = cursor
        next_cursor: str | None = None

        for _ in range(20):
            payload = self._fetch_calls(cursor, next_cursor)
            calls, next_cursor, has_more = self._extract_calls(payload)
            if not calls:
                break

            parsed_batch: list[ParsedCallCost] = []
            for raw in calls:
                parsed = self._parse_call(raw)
                if not parsed:
                    skipped += 1
                    continue

                processed += 1
                if parsed.started_at and parsed.started_at > max_seen:
                    max_seen = parsed.started_at

                parsed_batch.append(parsed)

            batch_created, batch_updated = self._upsert_cost_batch(session, parsed_batch, now)
            created += batch_created
            updated += batch_updated
            session.commit()
            if next_cursor:
                continue
            if has_more and max_seen > cursor:
                cursor = max_seen
                continue
            break

        if state is None:
            state = OpsSyncState(provider=self.provider_key)
            session.add(state)
        state.last_synced_at = max_seen
        state.updated_at = now
        session.commit()

        return {
            "provider": self.provider_key,
            "cursor_start": initial_cursor.isoformat(),
            "cursor_end": max_seen.isoformat(),
            "processed": processed,
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }

    def _upsert_cost_batch(
        self,
        session: Session,
        parsed_batch: list[ParsedCallCost],
        synced_at: datetime,
    ) -> tuple[int, int]:
        if not parsed_batch:
            return 0, 0

        call_ids = [parsed.call_id for parsed in parsed_batch]
        existing_ids = set(
            session.execute(
                select(VapiCallCost.call_id).where(VapiCallCost.call_id.in_(call_ids))
            ).scalars()
        )
        created = sum(1 for call_id in call_ids if call_id not in existing_ids)
        updated = len(parsed_batch) - created
        rows = [
            {
                "call_id": parsed.call_id,
                "tenant_id": parsed.tenant_id,
                "to_number": parsed.to_number,
                "started_at": parsed.started_at,
                "ended_at": parsed.ended_at,
                "duration_seconds": parsed.duration_seconds,
                "assistant_id": parsed.assistant_id,
                "status": parsed.status,
                "cost_total_usd": parsed.cost_total_usd,
                "cost_breakdown_json": parsed.cost_breakdown_json,
                "synced_at": synced_at,
            }
            for parsed in parsed_batch
        ]

        if session.bind and session.bind.dialect.name == "postgresql":
            insert_stmt = pg_insert(VapiCallCost).values(rows)
            excluded = insert_stmt.excluded
            session.execute(
                insert_stmt.on_conflict_do_update(
                    index_elements=[VapiCallCost.call_id],
                    set_={
                        "tenant_id": excluded.tenant_id,
                        "to_number": excluded.to_number,
                        "started_at": excluded.started_at,
                        "ended_at": excluded.ended_at,
                        "duration_seconds": excluded.duration_seconds,
                        "assistant_id": excluded.assistant_id,
                        "status": excluded.status,
                        "cost_total_usd": excluded.cost_total_usd,
                        "cost_breakdown_json": excluded.cost_breakdown_json,
                        "synced_at": excluded.synced_at,
                    },
                )
            )
            return created, updated

        for parsed in parsed_batch:
            existing = session.get(VapiCallCost, parsed.call_id)
            if existing is None:
                row = VapiCallCost(call_id=parsed.call_id)
                session.add(row)
            else:
                row = existing

            row.tenant_id = parsed.tenant_id
            row.to_number = parsed.to_number
            row.started_at = parsed.started_at
            row.ended_at = parsed.ended_at
            row.duration_seconds = parsed.duration_seconds
            row.assistant_id = parsed.assistant_id
            row.status = parsed.status
            row.cost_total_usd = parsed.cost_total_usd
            row.cost_breakdown_json = parsed.cost_breakdown_json
            row.synced_at = synced_at
        return created, updated

    def _fetch_calls(self, cursor: datetime, next_cursor: str | None) -> Any:
        params: dict[str, Any] = {
            "limit": self.settings.ops_cost_sync_page_size,
            "createdAtGt": cursor.isoformat(),
        }
        if next_cursor:
            params["cursor"] = next_cursor

        headers = {"Authorization": f"Bearer {self.settings.vapi_api_key}"}
        url = f"{self.base_url}/{self.path.lstrip('/')}"

        try:
            response = httpx.get(url, headers=headers, params=params, timeout=15.0)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Vapi sync failed with HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("Vapi sync request failed") from exc

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Vapi sync returned non-JSON response") from exc

    @staticmethod
    def _extract_calls(payload: Any) -> tuple[list[dict[str, Any]], str | None, bool]:
        if isinstance(payload, list):
            calls = [item for item in payload if isinstance(item, dict)]
            return calls, None, False
        if not isinstance(payload, dict):
            return [], None, False

        container = payload
        if isinstance(payload.get("data"), dict):
            container = payload["data"]

        calls_raw = (
            container.get("calls")
            or container.get("items")
            or container.get("results")
            or payload.get("calls")
            or payload.get("items")
            or payload.get("results")
            or []
        )
        calls = [item for item in calls_raw if isinstance(item, dict)] if isinstance(calls_raw, list) else []
        next_cursor = (
            container.get("nextCursor")
            or container.get("next_cursor")
            or payload.get("nextCursor")
            or payload.get("next_cursor")
        )
        has_more = bool(
            container.get("hasMore")
            or container.get("has_more")
            or payload.get("hasMore")
            or payload.get("has_more")
        )
        if next_cursor:
            has_more = True
        return calls, str(next_cursor) if next_cursor else None, has_more

    def _parse_call(self, raw: dict[str, Any]) -> ParsedCallCost | None:
        call_id = self._as_optional_string(raw.get("id") or raw.get("callId"))
        if not call_id:
            return None

        started_at = self._parse_datetime(
            raw.get("startedAt") or raw.get("createdAt") or raw.get("startTime")
        )
        ended_at = self._parse_datetime(raw.get("endedAt") or raw.get("endTime"))
        duration_seconds = self._parse_duration_seconds(raw, started_at, ended_at)

        to_number = self._extract_to_number(raw)
        resolution = resolve_tenant_details(to_number, self.settings)
        tenant_rejected = should_reject_tenant_resolution(resolution, self.settings)
        tenant_id = "unknown" if tenant_rejected else resolution.tenant_id
        assistant_id = self._extract_assistant_id(raw)
        status = self._as_optional_string(raw.get("status"))
        cost_total, breakdown = self._extract_cost(raw)

        if tenant_rejected:
            log.warning(
                "vapi_cost_sync_tenant_unresolved",
                event_type="tenant_resolution_rejected",
                tenant_id=tenant_id,
                call_id=call_id,
                to_number=to_number,
                resolution_source=resolution.source,
            )

        log.info(
            "vapi_cost_sync_call",
            event_type="vapi_cost_sync_call",
            tenant_id=tenant_id,
            call_id=call_id,
            status=status,
            cost_total_usd=cost_total,
            resolution_source=resolution.source,
        )

        return ParsedCallCost(
            call_id=call_id,
            tenant_id=tenant_id,
            to_number=to_number,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            assistant_id=assistant_id,
            status=status,
            cost_total_usd=cost_total,
            cost_breakdown_json=breakdown,
        )

    @staticmethod
    def _extract_assistant_id(raw: dict[str, Any]) -> str | None:
        assistant = raw.get("assistant")
        if isinstance(assistant, dict):
            return VapiCostSyncService._as_optional_string(assistant.get("id"))
        return VapiCostSyncService._as_optional_string(raw.get("assistantId"))

    @staticmethod
    def _extract_to_number(raw: dict[str, Any]) -> str | None:
        phone_number = raw.get("phoneNumber")
        customer = raw.get("customer")

        candidates: list[Any] = [
            raw.get("to"),
            raw.get("toNumber"),
            phone_number.get("number") if isinstance(phone_number, dict) else None,
            phone_number.get("phoneNumber") if isinstance(phone_number, dict) else None,
            customer.get("number") if isinstance(customer, dict) else None,
            raw.get("phoneNumber") if isinstance(raw.get("phoneNumber"), str) else None,
        ]

        for candidate in candidates:
            normalized = VapiCostSyncService._as_optional_string(candidate)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _extract_cost(raw: dict[str, Any]) -> tuple[float, dict[str, Any]]:
        direct_keys = [
            "costTotalUsd",
            "costTotal",
            "totalCostUsd",
            "totalCost",
            "cost",
            "price",
        ]
        for key in direct_keys:
            value = raw.get(key)
            if isinstance(value, (int, float)):
                return float(value), {key: value}

        breakdown_sources = [
            raw.get("costBreakdown"),
            raw.get("costs"),
            raw.get("cost") if isinstance(raw.get("cost"), dict) else None,
        ]
        for source in breakdown_sources:
            if not isinstance(source, dict):
                continue
            total = VapiCostSyncService._extract_total_from_breakdown(source)
            if total is not None:
                return total, source

        return 0.0, {}

    @staticmethod
    def _extract_total_from_breakdown(breakdown: dict[str, Any]) -> float | None:
        for key in ("total", "totalCost", "total_cost", "totalUsd", "total_usd"):
            value = breakdown.get(key)
            if isinstance(value, (int, float)):
                return float(value)

        total = 0.0
        found = False
        for key, value in breakdown.items():
            key_lower = str(key).lower()
            if isinstance(value, (int, float)) and ("cost" in key_lower or "price" in key_lower):
                total += float(value)
                found = True
            elif isinstance(value, dict):
                nested = VapiCostSyncService._extract_total_from_breakdown(value)
                if nested is not None:
                    total += nested
                    found = True
        return total if found else None

    @staticmethod
    def _parse_duration_seconds(
        raw: dict[str, Any],
        started_at: datetime | None,
        ended_at: datetime | None,
    ) -> float | None:
        duration_seconds = raw.get("durationSeconds")
        if isinstance(duration_seconds, (int, float)):
            return float(duration_seconds)

        duration_ms = raw.get("durationMs") or raw.get("durationMilliseconds")
        if isinstance(duration_ms, (int, float)):
            return float(duration_ms) / 1000.0

        duration = raw.get("duration")
        if isinstance(duration, (int, float)):
            return float(duration)

        if started_at and ended_at:
            return max(0.0, (ended_at - started_at).total_seconds())
        return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _as_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
