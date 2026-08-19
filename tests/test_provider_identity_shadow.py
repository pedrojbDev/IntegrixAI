from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.tenant.resolver import resolve_tenant_details
from app.models.provider_resource import ProviderResource, ProviderResourceOwnership
from app.models.tenant import TenantRecord
from app.platform.services.provider_identity_shadow import (
    ProviderIdentityShadowEvaluator,
    VapiInboundIdentityEvidence,
    extract_vapi_inbound_identity,
)


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class ProviderIdentityShadowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        TenantRecord.__table__.create(self.engine)
        ProviderResource.__table__.create(self.engine)
        ProviderResourceOwnership.__table__.create(self.engine)
        self.session = Session(self.engine)
        self.evaluator = ProviderIdentityShadowEvaluator()
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
            "phone_number_id": None,
            "did": None,
            "telephony_credential_id": None,
            "assistant_id": None,
            "sip_destination": None,
            "sip_header_names": (),
        }
        values.update(overrides)
        return VapiInboundIdentityEvidence(**values)  # type: ignore[arg-type]

    def test_extracts_nested_vapi_evidence_without_sip_header_values(self) -> None:
        evidence = extract_vapi_inbound_identity(
            {
                "message": {
                    "call": {
                        "id": "call_123",
                        "orgId": "org_real",
                        "phoneNumber": {
                            "id": "phone_123",
                            "number": "+55 (71) 3333-4444",
                            "credentialId": "cred_sip_123",
                        },
                        "assistantId": "assistant_123",
                        "destination": {
                            "sipUri": "sip:pbsaude@cred.sip.vapi.ai",
                            "sipHeaders": {"X-Tenant-Ref": "sensitive-value"},
                        },
                    }
                }
            }
        )

        self.assertEqual("call_123", evidence.call_id)
        self.assertEqual("org_real", evidence.provider_org_id)
        self.assertEqual("phone_123", evidence.phone_number_id)
        self.assertEqual("+557133334444", evidence.did)
        self.assertEqual("cred_sip_123", evidence.telephony_credential_id)
        self.assertEqual("assistant_123", evidence.assistant_id)
        self.assertEqual("sip:pbsaude@cred.sip.vapi.ai", evidence.sip_destination)
        self.assertEqual(("X-Tenant-Ref",), evidence.sip_header_names)
        self.assertNotIn("sensitive-value", repr(evidence))

    def test_ignores_ambiguous_generic_credential_id(self) -> None:
        evidence = extract_vapi_inbound_identity(
            {"call": {"id": "call_123", "orgId": "org_real", "credentialId": "ambiguous"}}
        )

        self.assertIsNone(evidence.telephony_credential_id)

    def test_phone_number_is_primary_and_assistant_corroborates(self) -> None:
        self._own(kind="phone_number", external_id="phone_123")
        self._own(kind="assistant", external_id="assistant_123")

        result = self.evaluator.evaluate(
            self.session,
            self._evidence(phone_number_id="phone_123", assistant_id="assistant_123"),
            occurred_at=NOW,
        )

        self.assertEqual("resolved", result.status)
        self.assertEqual("pbsaude", result.tenant_id)
        self.assertEqual("phone_number", result.source)

    def test_assistant_alone_is_never_authoritative(self) -> None:
        self._own(kind="assistant", external_id="assistant_123")

        result = self.evaluator.evaluate(
            self.session,
            self._evidence(assistant_id="assistant_123"),
            occurred_at=NOW,
        )

        self.assertEqual("insufficient_evidence", result.status)
        self.assertIsNone(result.tenant_id)
        self.assertEqual("assistant", result.matched[0].resource_kind)

    def test_shadow_rule_does_not_change_legacy_productive_resolver(self) -> None:
        settings = Settings(
            _env_file=None,
            tenant_assistant_map={"assistant_123": "pbsaude"},
        )

        legacy = resolve_tenant_details(None, settings, assistant_id="assistant_123")
        shadow = self.evaluator.evaluate(
            self.session,
            self._evidence(assistant_id="assistant_123"),
            occurred_at=NOW,
        )

        self.assertEqual("pbsaude", legacy.tenant_id)
        self.assertEqual("assistant_map", legacy.source)
        self.assertEqual("insufficient_evidence", shadow.status)

    def test_conflicting_phone_and_assistant_never_choose_a_winner(self) -> None:
        self._tenant("tenant_b")
        self._own(kind="phone_number", external_id="phone_123")
        self._own(kind="assistant", external_id="assistant_b", tenant_id="tenant_b")

        result = self.evaluator.evaluate(
            self.session,
            self._evidence(phone_number_id="phone_123", assistant_id="assistant_b"),
            occurred_at=NOW,
        )

        self.assertEqual("conflict", result.status)
        self.assertIsNone(result.tenant_id)
        self.assertEqual(("pbsaude", "tenant_b"), result.conflicting_tenant_ids)

    def test_conflict_is_reported_even_when_present_phone_is_not_owned(self) -> None:
        self._tenant("tenant_b")
        self._own(kind="did", external_id="+557133334444")
        self._own(kind="assistant", external_id="assistant_b", tenant_id="tenant_b")

        result = self.evaluator.evaluate(
            self.session,
            self._evidence(
                phone_number_id="phone_unknown",
                did="+557133334444",
                assistant_id="assistant_b",
            ),
            occurred_at=NOW,
        )

        self.assertEqual("conflict", result.status)
        self.assertIsNone(result.tenant_id)
        self.assertEqual(("pbsaude", "tenant_b"), result.conflicting_tenant_ids)

    def test_did_can_resolve_only_when_phone_number_id_is_absent(self) -> None:
        self._own(kind="did", external_id="+557133334444")

        fallback = self.evaluator.evaluate(
            self.session,
            self._evidence(did="+55 (71) 3333-4444"),
            occurred_at=NOW,
        )
        unknown_phone = self.evaluator.evaluate(
            self.session,
            self._evidence(phone_number_id="phone_unknown", did="+557133334444"),
            occurred_at=NOW,
        )

        self.assertEqual("resolved", fallback.status)
        self.assertEqual("pbsaude", fallback.tenant_id)
        self.assertEqual("did", fallback.source)
        self.assertEqual("insufficient_evidence", unknown_phone.status)
        self.assertIsNone(unknown_phone.tenant_id)

    def test_org_scope_prevents_cross_tenant_resource_leak(self) -> None:
        self._tenant("tenant_b")
        self._own(kind="phone_number", external_id="phone_shared", org_id="org_real")
        self._own(
            kind="phone_number",
            external_id="phone_shared",
            tenant_id="tenant_b",
            org_id="org_enterprise",
        )

        result = self.evaluator.evaluate(
            self.session,
            self._evidence(provider_org_id="org_enterprise", phone_number_id="phone_shared"),
            occurred_at=NOW,
        )

        self.assertEqual("resolved", result.status)
        self.assertEqual("tenant_b", result.tenant_id)

    def test_historical_ownership_is_resolved_at_event_time(self) -> None:
        self._tenant("tenant_b")
        transfer_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
        resource = self._own(
            kind="phone_number",
            external_id="phone_transferred",
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

        before = self.evaluator.evaluate(
            self.session,
            self._evidence(phone_number_id="phone_transferred"),
            occurred_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        after = self.evaluator.evaluate(
            self.session,
            self._evidence(phone_number_id="phone_transferred"),
            occurred_at=NOW,
        )

        self.assertEqual("pbsaude", before.tenant_id)
        self.assertEqual("tenant_b", after.tenant_id)

    def test_missing_org_id_cannot_fall_back_to_default_account(self) -> None:
        self._own(kind="phone_number", external_id="phone_123")

        result = self.evaluator.evaluate(
            self.session,
            self._evidence(provider_org_id=None, phone_number_id="phone_123"),
            occurred_at=NOW,
        )

        self.assertEqual("missing_provider_org_id", result.status)
        self.assertIsNone(result.tenant_id)


if __name__ == "__main__":
    unittest.main()
