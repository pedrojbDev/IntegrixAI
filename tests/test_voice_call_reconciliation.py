from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.ops.cost_sync_service import VapiCostSyncService
from app.db import Base
from app.models.provider_event_receipt import ProviderEventReceipt
from app.models.provider_resource import ProviderResource, ProviderResourceOwnership
from app.models.tenant import TenantRecord
from app.models.vapi_call_cost import VapiCallCost
from app.models.voice_call import VoiceCall
from app.platform.services.provider_identity_shadow import VapiInboundIdentityEvidence
from app.platform.services.voice_call_reconciliation import (
    InboundCallObservation,
    VoiceCallReconciliationService,
)


JUNE = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
AUGUST = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class VoiceCallReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.service = VoiceCallReconciliationService()
        self._tenant("pbsaude", "PB Saúde")

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _tenant(self, tenant_id: str, display_name: str | None = None) -> None:
        self.session.add(
            TenantRecord(
                id=tenant_id,
                display_name=display_name or tenant_id,
                implementation_key="pbsaude",
                status="active",
            )
        )
        self.session.flush()

    def _own(
        self,
        *,
        kind: str,
        external_id: str,
        tenant_id: str = "pbsaude",
        org_id: str = "org_real",
        valid_from: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc),
        valid_to: datetime | None = None,
    ) -> ProviderResource:
        resource = ProviderResource(
            provider="vapi",
            provider_org_id=org_id,
            resource_kind=kind,
            external_id=external_id,
            normalized_value=external_id,
            configuration_source="manual",
        )
        self.session.add(resource)
        self.session.flush()
        self.session.add(
            ProviderResourceOwnership(
                provider_resource_id=resource.id,
                tenant_id=tenant_id,
                valid_from=valid_from,
                valid_to=valid_to,
                source="manual",
            )
        )
        self.session.flush()
        return resource

    @staticmethod
    def _evidence(**overrides: object) -> VapiInboundIdentityEvidence:
        values: dict[str, object] = {
            "call_id": "call_123",
            "provider_org_id": "org_real",
            "phone_number_id": "phone_123",
            "did": "+557133334444",
            "telephony_credential_id": None,
            "assistant_id": None,
            "sip_destination": None,
            "sip_header_names": (),
        }
        values.update(overrides)
        return VapiInboundIdentityEvidence(**values)  # type: ignore[arg-type]

    @classmethod
    def _observation(
        cls,
        *,
        source: str = "sync",
        event_type: str = "call_snapshot",
        raw_suffix: str = "first",
        provider_updated_at: datetime | None = AUGUST,
        started_at: datetime | None = JUNE,
        provider_status: str | None = "ended",
        evidence: VapiInboundIdentityEvidence | None = None,
    ) -> InboundCallObservation:
        return InboundCallObservation(
            provider="vapi",
            source=source,
            event_type=event_type,
            evidence=evidence or cls._evidence(),
            raw_payload={"sample": raw_suffix},
            occurred_at=provider_updated_at,
            provider_created_at=started_at,
            provider_updated_at=provider_updated_at,
            started_at=started_at,
            ended_at=AUGUST if provider_status == "ended" else None,
            duration_seconds=120.0 if provider_status == "ended" else None,
            provider_status=provider_status,
        )

    def test_duplicate_snapshot_creates_one_receipt_and_one_call(self) -> None:
        self._own(kind="phone_number", external_id="phone_123")
        observation = self._observation()

        first = self.service.reconcile(self.session, observation, received_at=AUGUST)
        second = self.service.reconcile(self.session, observation, received_at=AUGUST)

        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(first.voice_call.id, second.voice_call.id)
        self.assertEqual(
            1, self.session.scalar(select(func.count(VoiceCall.id)))
        )
        self.assertEqual(
            1, self.session.scalar(select(func.count(ProviderEventReceipt.id)))
        )

    def test_sync_and_webhook_converge_regardless_of_arrival_order(self) -> None:
        self._own(kind="phone_number", external_id="phone_123")
        webhook = self._observation(
            source="webhook",
            event_type="status_update",
            raw_suffix="webhook",
        )
        sync = self._observation(source="sync", raw_suffix="sync")

        webhook_result = self.service.reconcile(
            self.session, webhook, received_at=AUGUST
        )
        sync_result = self.service.reconcile(self.session, sync, received_at=AUGUST)

        self.assertEqual(webhook_result.voice_call.id, sync_result.voice_call.id)
        self.assertEqual("pbsaude", sync_result.voice_call.tenant_id)
        self.assertEqual("admitted", sync_result.voice_call.identity_status)
        self.assertEqual(
            2, self.session.scalar(select(func.count(ProviderEventReceipt.id)))
        )

    def test_conflicting_later_identifier_never_reassigns_tenant(self) -> None:
        self._tenant("tenant_b")
        self._own(kind="phone_number", external_id="phone_123")
        self._own(
            kind="phone_number",
            external_id="phone_b",
            tenant_id="tenant_b",
        )
        first = self.service.reconcile(
            self.session, self._observation(), received_at=AUGUST
        )
        conflict_evidence = self._evidence(phone_number_id="phone_b")

        conflict = self.service.reconcile(
            self.session,
            self._observation(
                source="webhook",
                event_type="status_update",
                raw_suffix="conflict",
                evidence=conflict_evidence,
            ),
            received_at=AUGUST,
        )

        self.assertEqual("pbsaude", first.voice_call.tenant_id)
        self.assertEqual("pbsaude", conflict.voice_call.tenant_id)
        self.assertEqual("admitted", conflict.voice_call.identity_status)
        self.assertEqual("conflict", conflict.voice_call.reconciliation_status)
        self.assertEqual("conflict", conflict.receipt.processing_status)

    def test_ownership_is_evaluated_at_original_call_time(self) -> None:
        self._tenant("tenant_b")
        transfer_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
        resource = self._own(
            kind="phone_number",
            external_id="phone_123",
            valid_to=transfer_at,
        )
        self.session.add(
            ProviderResourceOwnership(
                provider_resource_id=resource.id,
                tenant_id="tenant_b",
                valid_from=transfer_at,
                source="manual",
            )
        )
        self.session.flush()

        first = self.service.reconcile(
            self.session, self._observation(), received_at=AUGUST
        )
        later = self.service.reconcile(
            self.session,
            self._observation(source="webhook", raw_suffix="later"),
            received_at=AUGUST,
        )

        self.assertEqual("pbsaude", first.voice_call.tenant_id)
        self.assertEqual("pbsaude", later.voice_call.tenant_id)
        self.assertEqual("consistent", later.voice_call.reconciliation_status)

    def test_older_snapshot_cannot_regress_provider_lifecycle(self) -> None:
        self._own(kind="phone_number", external_id="phone_123")
        newer = self._observation(provider_updated_at=AUGUST, provider_status="ended")
        older_time = datetime(2026, 8, 19, 11, 0, tzinfo=timezone.utc)
        older = self._observation(
            source="webhook",
            raw_suffix="older",
            provider_updated_at=older_time,
            provider_status="ringing",
        )

        self.service.reconcile(self.session, newer, received_at=AUGUST)
        result = self.service.reconcile(self.session, older, received_at=AUGUST)

        self.assertEqual("ended", result.voice_call.provider_status)
        self.assertEqual(120.0, result.voice_call.duration_seconds)

    def test_missing_org_is_quarantined_without_default_account(self) -> None:
        self._own(kind="phone_number", external_id="phone_123")
        evidence = self._evidence(provider_org_id=None)

        result = self.service.reconcile(
            self.session,
            self._observation(evidence=evidence),
            received_at=AUGUST,
        )

        self.assertIsNone(result.voice_call.tenant_id)
        self.assertEqual("quarantined", result.voice_call.identity_status)
        self.assertEqual("missing_provider_org_id", result.identity_result)

    def test_observation_without_call_id_is_kept_only_in_quarantine_inbox(self) -> None:
        evidence = self._evidence(call_id=None)

        result = self.service.reconcile(
            self.session,
            self._observation(evidence=evidence),
            received_at=AUGUST,
        )

        self.assertIsNone(result.voice_call)
        self.assertEqual("missing_call_id", result.identity_result)
        self.assertEqual("quarantined", result.receipt.processing_status)

    def test_cost_sync_shadow_links_cost_without_changing_legacy_tenant(self) -> None:
        self._own(kind="phone_number", external_id="phone_123")
        settings = Settings(
            _env_file=None,
            voice_call_shadow_enabled=True,
            tenant_map={"+557133334444": "pbsaude"},
        )
        cost_service = VapiCostSyncService(settings)
        parsed = cost_service._parse_call(
            {
                "id": "cost_call_123",
                "orgId": "org_real",
                "phoneNumberId": "phone_123",
                "to": "+557133334444",
                "createdAt": JUNE.isoformat(),
                "updatedAt": AUGUST.isoformat(),
                "startedAt": JUNE.isoformat(),
                "endedAt": AUGUST.isoformat(),
                "status": "ended",
                "cost": "1.25000000",
            }
        )

        with patch.object(
            cost_service.ptax,
            "rate_for_call",
            return_value=(None, None, False),
        ):
            cost_service._upsert_cost_batch(self.session, [parsed], AUGUST)
        self.session.flush()
        cost = self.session.get(VapiCallCost, "cost_call_123")
        voice_call = self.session.get(VoiceCall, cost.voice_call_id)

        self.assertEqual("pbsaude", cost.tenant_id)
        self.assertEqual(Decimal("1.25000000"), cost.cost_total_usd)
        self.assertEqual("pbsaude", voice_call.tenant_id)
        self.assertEqual("phone_number", voice_call.identity_source)

    def test_shadow_failure_does_not_block_existing_cost_projection(self) -> None:
        settings = Settings(_env_file=None, voice_call_shadow_enabled=True)
        cost_service = VapiCostSyncService(settings)
        parsed = cost_service._parse_call(
            {"id": "cost_only", "cost": "2.00000000"}
        )

        with (
            patch.object(
                VoiceCallReconciliationService,
                "reconcile",
                side_effect=RuntimeError("shadow unavailable"),
            ),
            patch.object(
                cost_service.ptax,
                "rate_for_call",
                return_value=(None, None, False),
            ),
        ):
            cost_service._upsert_cost_batch(self.session, [parsed], AUGUST)
        self.session.flush()
        cost = self.session.get(VapiCallCost, "cost_only")

        self.assertEqual(Decimal("2.00000000"), cost.cost_total_usd)
        self.assertIsNone(cost.voice_call_id)


if __name__ == "__main__":
    unittest.main()
