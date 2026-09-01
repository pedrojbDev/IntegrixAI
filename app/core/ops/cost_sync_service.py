from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ...config import Settings
from ...logging import get_logger
from ...models.ops_sync_state import OpsSyncState
from ...models.vapi_call_cost import VapiCallCost
from ...platform.services.provider_identity_shadow import (
    VapiInboundIdentityEvidence,
    extract_vapi_inbound_identity,
)
from ...platform.services.voice_call_reconciliation import (
    InboundCallObservation,
    VoiceCallReconciliationService,
)
from ...platform.services.vapi_event_ingestion import VapiEventIngestionService
from ..tenant.resolver import resolve_tenant_details, should_reject_tenant_resolution
from .fx_service import PtaxService

log = get_logger()
COST_SYNC_ADVISORY_LOCK_ID = 732_118_408
MINIMUM_SLICE_SECONDS = 1
COMPONENT_NAMES = ("transport", "stt", "llm", "tts", "vapi", "analysis", "other")
_SENSITIVE_VAPI_SNAPSHOT_KEYS = frozenset(
    {
        "artifact",
        "analysis",
        "summary",
        "customer",
        "transcript",
        "recording",
        "recordingurl",
        "stereorecordingurl",
        "messages",
        "cpf",
    }
)


@dataclass
class ParsedCallCost:
    call_id: str
    tenant_id: str | None
    to_number: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: float | None
    assistant_id: str | None
    status: str | None
    cost_total_usd: Decimal | None
    cost_breakdown_json: dict[str, Any]
    phone_number_id: str | None = None
    tenant_resolution_source: str | None = None
    vapi_created_at: datetime | None = None
    vapi_updated_at: datetime | None = None
    components: dict[str, Decimal | None] = field(default_factory=dict)
    raw_call_json: dict[str, Any] = field(default_factory=dict)
    identity_evidence: VapiInboundIdentityEvidence | None = None
    voice_call_id: str | None = None


class VapiCostSyncService:
    provider_key = "vapi_costs"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.vapi_base_url.rstrip("/")
        self.path = settings.vapi_calls_path
        self.ptax = PtaxService(settings)

    def sync(self, session: Session) -> dict[str, Any]:
        if not self.settings.vapi_api_key:
            raise RuntimeError("VAPI_API_KEY not configured")
        if not self._try_lock(session):
            return {"provider": self.provider_key, "locked": True, "processed": 0}

        now = datetime.now(timezone.utc)
        state = session.get(OpsSyncState, self.provider_key)
        is_initial = state is None or state.cursor_updated_at is None
        start = (
            now - timedelta(days=self.settings.ops_cost_backfill_days)
            if is_initial
            else _as_utc(state.cursor_updated_at)
            - timedelta(minutes=self.settings.ops_cost_sync_overlap_minutes)
        )
        field_name = "createdAt" if is_initial else "updatedAt"
        stats: dict[str, Any] = {
            "provider": self.provider_key,
            "locked": False,
            "mode": "backfill" if is_initial else "incremental",
            "cursor_start": start.isoformat(),
            "cursor_end": now.isoformat(),
            "processed": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "missing_cost": 0,
            "unresolved_tenant": 0,
            "missing_fx": 0,
            "errors": 0,
            "native_handoffs_reconciled": 0,
        }
        try:
            current = start
            step = timedelta(days=1) if is_initial else now - start
            while current < now:
                end = min(current + step, now)
                raw_calls = self._fetch_complete_range(current, end, field_name)
                parsed_batch: list[ParsedCallCost] = []
                for raw in raw_calls:
                    parsed = self._parse_call(raw)
                    if parsed is None:
                        stats["skipped"] += 1
                        continue
                    parsed_batch.append(parsed)
                    stats["processed"] += 1
                    stats["missing_cost"] += int(parsed.cost_total_usd is None)
                    stats["unresolved_tenant"] += int(parsed.tenant_id is None)
                self.ptax.ensure_rates(
                    session,
                    {item.started_at.date() for item in parsed_batch if item.started_at is not None},
                )
                created, updated, missing_fx = self._upsert_cost_batch_detailed(
                    session, parsed_batch, now
                )
                stats["created"] += created
                stats["updated"] += updated
                stats["missing_fx"] += missing_fx
                stats["native_handoffs_reconciled"] += self._reconcile_native_handoffs(
                    session, parsed_batch
                )
                session.commit()
                current = end

            if state is None:
                state = OpsSyncState(provider=self.provider_key)
                session.add(state)
            state.last_synced_at = now
            state.cursor_updated_at = now
            state.last_successful_run_at = now
            state.updated_at = now
            state.last_error = None
            state.last_run_stats_json = stats
            state.consecutive_failures = 0
            session.commit()
            log.info("ops_cost_sync_completed", event_type="ops_cost_sync", **stats)
            return stats
        except Exception as exc:
            session.rollback()
            state = session.get(OpsSyncState, self.provider_key)
            if state is None:
                state = OpsSyncState(provider=self.provider_key)
                session.add(state)
            state.updated_at = now
            state.last_error = str(exc)[:2000]
            state.consecutive_failures = int(state.consecutive_failures or 0) + 1
            session.commit()
            log.error(
                "ops_cost_sync_failed",
                event_type="ops_cost_sync",
                reason=str(exc),
                cursor_start=start.isoformat(),
            )
            raise
        finally:
            self._unlock(session)

    def _fetch_complete_range(
        self,
        start: datetime,
        end: datetime,
        field_name: str,
    ) -> list[dict[str, Any]]:
        payload = self._fetch_calls(start, end, field_name)
        calls, _, _ = self._extract_calls(payload)
        if len(calls) < self.settings.ops_cost_sync_page_size:
            return calls
        if (end - start).total_seconds() <= MINIMUM_SLICE_SECONDS:
            raise RuntimeError("Vapi sync range saturated; cursor not advanced")
        midpoint = start + (end - start) / 2
        left = self._fetch_complete_range(start, midpoint, field_name)
        right = self._fetch_complete_range(midpoint, end, field_name)
        deduplicated = {str(item.get("id") or item.get("callId")): item for item in left + right}
        deduplicated.pop("None", None)
        return list(deduplicated.values())

    def _fetch_calls(self, start: datetime, end: datetime, field_name: str) -> Any:
        params = {
            "limit": self.settings.ops_cost_sync_page_size,
            f"{field_name}Ge": start.isoformat(),
            f"{field_name}Lt": end.isoformat(),
        }
        headers = {"Authorization": f"Bearer {self.settings.vapi_api_key}"}
        url = f"{self.base_url}/{self.path.lstrip('/')}"
        try:
            response = httpx.get(url, headers=headers, params=params, timeout=15.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Vapi sync failed with HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError("Vapi sync request failed") from exc
        except ValueError as exc:
            raise RuntimeError("Vapi sync returned non-JSON response") from exc

    @staticmethod
    def _extract_calls(payload: Any) -> tuple[list[dict[str, Any]], str | None, bool]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)], None, False
        if not isinstance(payload, dict):
            return [], None, False
        container = payload.get("data") if isinstance(payload.get("data"), dict) else payload
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
        next_cursor = container.get("nextCursor") or container.get("next_cursor")
        has_more = bool(container.get("hasMore") or container.get("has_more") or next_cursor)
        return calls, str(next_cursor) if next_cursor else None, has_more

    def _parse_call(self, raw: dict[str, Any]) -> ParsedCallCost | None:
        call_id = self._as_optional_string(raw.get("id") or raw.get("callId"))
        if not call_id:
            return None
        vapi_created_at = self._parse_datetime(raw.get("createdAt"))
        vapi_updated_at = self._parse_datetime(raw.get("updatedAt")) or vapi_created_at
        started_at = self._parse_datetime(
            raw.get("startedAt") or raw.get("createdAt") or raw.get("startTime")
        )
        ended_at = self._parse_datetime(raw.get("endedAt") or raw.get("endTime"))
        assistant_id = self._extract_assistant_id(raw)
        phone_number_id = self._as_optional_string(raw.get("phoneNumberId"))
        to_number = self._extract_to_number(raw)
        identity_evidence = extract_vapi_inbound_identity(raw)
        resolution = resolve_tenant_details(
            to_number,
            self.settings,
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
        )
        tenant_rejected = should_reject_tenant_resolution(resolution, self.settings)
        tenant_id = None if tenant_rejected else resolution.tenant_id
        cost_total, breakdown, components = self._extract_cost(raw)
        return ParsedCallCost(
            call_id=call_id,
            tenant_id=tenant_id,
            to_number=to_number,
            phone_number_id=phone_number_id,
            tenant_resolution_source=resolution.source,
            vapi_created_at=vapi_created_at,
            vapi_updated_at=vapi_updated_at,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=self._parse_duration_seconds(raw, started_at, ended_at),
            assistant_id=assistant_id,
            status=self._as_optional_string(raw.get("status")),
            cost_total_usd=cost_total,
            cost_breakdown_json=breakdown,
            components=components,
            raw_call_json=self._sanitize_call_snapshot(raw),
            identity_evidence=identity_evidence,
        )

    def _upsert_cost_batch(
        self,
        session: Session,
        parsed_batch: list[ParsedCallCost],
        synced_at: datetime,
    ) -> tuple[int, int]:
        created, updated, _ = self._upsert_cost_batch_detailed(session, parsed_batch, synced_at)
        return created, updated

    def _reconcile_native_handoffs(
        self,
        session: Session,
        parsed_batch: list[ParsedCallCost],
    ) -> int:
        ingestor = VapiEventIngestionService(self.settings)
        reconciled = 0
        for parsed in parsed_batch:
            raw = parsed.raw_call_json or {}
            nested_call = raw.get("call") if isinstance(raw.get("call"), dict) else {}
            ended_reason = self._as_optional_string(
                raw.get("endedReason")
                or raw.get("ended_reason")
                or nested_call.get("endedReason")
            )
            reconciled += int(
                ingestor.record_cost_sync_handoff(
                    session,
                    tenant_id=parsed.tenant_id,
                    call_id=parsed.call_id,
                    ended_reason=ended_reason,
                )
            )
        return reconciled

    @classmethod
    def _sanitize_call_snapshot(cls, value: Any) -> Any:
        """Keep cost reconciliation metadata without retaining call content or CPF."""
        if isinstance(value, dict):
            return {
                str(key): cls._sanitize_call_snapshot(item)
                for key, item in value.items()
                if str(key).lower() not in _SENSITIVE_VAPI_SNAPSHOT_KEYS
            }
        if isinstance(value, list):
            return [cls._sanitize_call_snapshot(item) for item in value]
        return value

    def _upsert_cost_batch_detailed(
        self,
        session: Session,
        parsed_batch: list[ParsedCallCost],
        synced_at: datetime,
    ) -> tuple[int, int, int]:
        if not parsed_batch:
            return 0, 0, 0
        if self.settings.voice_call_shadow_enabled:
            self._reconcile_voice_calls_shadow(session, parsed_batch, synced_at)
        call_ids = [parsed.call_id for parsed in parsed_batch]
        existing_ids = set(
            session.execute(
                select(VapiCallCost.call_id).where(VapiCallCost.call_id.in_(call_ids))
            ).scalars()
        )
        rows = []
        missing_fx = 0
        for parsed in parsed_batch:
            fx_date, fx_rate, provisional = self.ptax.rate_for_call(session, parsed.started_at)
            total_brl = (
                (parsed.cost_total_usd * fx_rate).quantize(Decimal("0.00000001"))
                if parsed.cost_total_usd is not None and fx_rate is not None
                else None
            )
            missing_fx += int(parsed.cost_total_usd is not None and fx_rate is None)
            row = {
                "call_id": parsed.call_id,
                "voice_call_id": parsed.voice_call_id,
                "tenant_id": parsed.tenant_id,
                "to_number": parsed.to_number,
                "phone_number_id": parsed.phone_number_id,
                "tenant_resolution_source": parsed.tenant_resolution_source,
                "vapi_created_at": parsed.vapi_created_at,
                "vapi_updated_at": parsed.vapi_updated_at,
                "started_at": parsed.started_at,
                "ended_at": parsed.ended_at,
                "duration_seconds": parsed.duration_seconds,
                "assistant_id": parsed.assistant_id,
                "status": parsed.status,
                "cost_total_usd": parsed.cost_total_usd,
                "cost_breakdown_json": parsed.cost_breakdown_json,
                "raw_call_json": parsed.raw_call_json,
                "fx_rate_date": fx_date,
                "usd_brl_rate": fx_rate,
                "cost_total_brl": total_brl,
                "fx_is_provisional": provisional,
                "is_verified": True,
                "synced_at": synced_at,
            }
            for component in COMPONENT_NAMES:
                row[f"cost_{component}_usd"] = parsed.components.get(component)
            rows.append(row)
        created = sum(1 for call_id in call_ids if call_id not in existing_ids)
        updated = len(rows) - created
        if session.bind and session.bind.dialect.name == "postgresql":
            insert_stmt = pg_insert(VapiCallCost).values(rows)
            excluded = insert_stmt.excluded
            update_values = {
                key: getattr(excluded, key) for key in rows[0] if key != "call_id"
            }
            update_values["voice_call_id"] = func.coalesce(
                excluded.voice_call_id,
                VapiCallCost.voice_call_id,
            )
            session.execute(
                insert_stmt.on_conflict_do_update(
                    index_elements=[VapiCallCost.call_id],
                    set_=update_values,
                )
            )
            return created, updated, missing_fx
        for values in rows:
            row = session.get(VapiCallCost, values["call_id"])
            if row is None:
                row = VapiCallCost(call_id=values["call_id"])
                session.add(row)
            for key, value in values.items():
                if key != "call_id":
                    if key == "voice_call_id" and value is None and row.voice_call_id:
                        continue
                    setattr(row, key, value)
        return created, updated, missing_fx

    def _reconcile_voice_calls_shadow(
        self,
        session: Session,
        parsed_batch: list[ParsedCallCost],
        received_at: datetime,
    ) -> None:
        reconciler = VoiceCallReconciliationService()
        for parsed in parsed_batch:
            evidence = parsed.identity_evidence or VapiInboundIdentityEvidence(
                call_id=parsed.call_id,
                provider_org_id=None,
                phone_number_id=parsed.phone_number_id,
                did=None,
                telephony_credential_id=None,
                assistant_id=parsed.assistant_id,
                sip_destination=None,
                sip_header_names=(),
            )
            observation = InboundCallObservation(
                provider="vapi",
                source="sync",
                event_type="call_snapshot",
                evidence=evidence,
                raw_payload=parsed.raw_call_json,
                occurred_at=parsed.vapi_updated_at or parsed.vapi_created_at,
                provider_created_at=parsed.vapi_created_at,
                provider_updated_at=parsed.vapi_updated_at,
                started_at=parsed.started_at,
                ended_at=parsed.ended_at,
                duration_seconds=parsed.duration_seconds,
                provider_status=parsed.status,
            )
            try:
                with session.begin_nested():
                    result = reconciler.reconcile(
                        session,
                        observation,
                        received_at=received_at,
                    )
                    if result.voice_call is not None:
                        parsed.voice_call_id = result.voice_call.id
            except Exception as exc:
                parsed.voice_call_id = None
                log.warning(
                    "voice_call_shadow_reconciliation_failed",
                    event_type="voice_call_shadow",
                    provider="vapi",
                    call_id=parsed.call_id,
                    reason=str(exc)[:1000],
                )

    @staticmethod
    def _extract_cost(
        raw: dict[str, Any],
    ) -> tuple[Decimal | None, dict[str, Any], dict[str, Decimal | None]]:
        total = _decimal_or_none(raw.get("cost"))
        if total is None:
            for key in ("costTotalUsd", "costTotal", "totalCostUsd", "totalCost", "price"):
                total = _decimal_or_none(raw.get(key))
                if total is not None:
                    break
        breakdown_object = raw.get("costBreakdown")
        costs_list = raw.get("costs")
        breakdown = {
            "costBreakdown": breakdown_object if isinstance(breakdown_object, dict) else None,
            "costs": costs_list if isinstance(costs_list, list) else None,
        }
        components: dict[str, Decimal | None] = {name: None for name in COMPONENT_NAMES}
        if isinstance(breakdown_object, dict):
            aliases = {
                "transport": ("transport", "telephony"),
                "stt": ("stt", "transcriber"),
                "llm": ("llm", "model"),
                "tts": ("tts", "voice"),
                "vapi": ("vapi", "platform"),
            }
            for name, keys in aliases.items():
                components[name] = next(
                    (value for key in keys if (value := _decimal_or_none(breakdown_object.get(key))) is not None),
                    None,
                )
            analysis = breakdown_object.get("analysisCostBreakdown")
            if isinstance(analysis, dict):
                components["analysis"] = _sum_leaf_costs(analysis)
        elif isinstance(costs_list, list):
            accumulated = {name: Decimal("0") for name in COMPONENT_NAMES}
            found: set[str] = set()
            aliases = {
                "transport": "transport",
                "telephony": "transport",
                "transcriber": "stt",
                "stt": "stt",
                "model": "llm",
                "llm": "llm",
                "voice": "tts",
                "tts": "tts",
                "vapi": "vapi",
                "platform": "vapi",
                "analysis": "analysis",
            }
            for item in costs_list:
                if not isinstance(item, dict):
                    continue
                category = aliases.get(str(item.get("type", "")).lower(), "other")
                value = _decimal_or_none(item.get("cost"))
                if value is not None:
                    accumulated[category] += value
                    found.add(category)
            for name in found:
                components[name] = accumulated[name]
        known = sum((value for name, value in components.items() if name != "other" and value is not None), Decimal("0"))
        if total is not None:
            components["other"] = total - known
        return total, breakdown, components

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
        candidates = [
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
    def _parse_duration_seconds(
        raw: dict[str, Any],
        started_at: datetime | None,
        ended_at: datetime | None,
    ) -> float | None:
        for key in ("durationSeconds", "duration"):
            value = raw.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        duration_ms = raw.get("durationMs") or raw.get("durationMilliseconds")
        if isinstance(duration_ms, (int, float)):
            return float(duration_ms) / 1000.0
        if started_at and ended_at:
            return max(0.0, (ended_at - started_at).total_seconds())
        return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return _as_utc(value)
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return _as_utc(datetime.fromisoformat(text))
        except ValueError:
            return None

    @staticmethod
    def _as_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _try_lock(session: Session) -> bool:
        if not session.bind or session.bind.dialect.name != "postgresql":
            return True
        return bool(
            session.execute(select(func.pg_try_advisory_lock(COST_SYNC_ADVISORY_LOCK_ID))).scalar()
        )

    @staticmethod
    def _unlock(session: Session) -> None:
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(select(func.pg_advisory_unlock(COST_SYNC_ADVISORY_LOCK_ID)))
            session.commit()


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return parsed if parsed.is_finite() else None


def _sum_leaf_costs(value: dict[str, Any]) -> Decimal | None:
    total = Decimal("0")
    found = False
    for key, item in value.items():
        if isinstance(item, dict):
            nested = _sum_leaf_costs(item)
            if nested is not None:
                total += nested
                found = True
        elif "cost" in str(key).lower() or key in {"summary", "structuredData", "successEvaluation"}:
            parsed = _decimal_or_none(item)
            if parsed is not None:
                total += parsed
                found = True
    return total if found else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
