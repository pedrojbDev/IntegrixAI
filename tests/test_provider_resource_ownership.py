from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models.provider_resource import ProviderResource, ProviderResourceOwnership
from app.models.tenant import TenantRecord
from app.platform.services.provider_resource_ownership import (
    ProviderResourceOwnershipError,
    ProviderResourceOwnershipRequest,
    register_provider_resource_ownership,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


class ProviderResourceOwnershipRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self._tenant("pbsaude")

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _tenant(self, tenant_id: str, status: str = "active") -> None:
        self.session.add(
            TenantRecord(
                id=tenant_id,
                display_name=tenant_id,
                implementation_key="pbsaude",
                status=status,
            )
        )
        self.session.flush()

    @staticmethod
    def _request(**overrides: object) -> ProviderResourceOwnershipRequest:
        values: dict[str, object] = {
            "tenant_id": "pbsaude",
            "provider": "vapi",
            "provider_org_id": "org_real",
            "resource_kind": "phone_number",
            "external_id": "phone_real",
            "valid_from": NOW,
        }
        values.update(overrides)
        return ProviderResourceOwnershipRequest(**values)  # type: ignore[arg-type]

    def test_dry_run_does_not_write(self) -> None:
        result = register_provider_resource_ownership(
            self.session, self._request(), apply=False
        )

        self.assertEqual("would_create", result.action)
        self.assertFalse(result.applied)
        self.assertEqual(0, self.session.scalar(select(func.count(ProviderResource.id))))

    def test_apply_creates_and_repeated_apply_is_idempotent(self) -> None:
        first = register_provider_resource_ownership(
            self.session, self._request(), apply=True
        )
        second = register_provider_resource_ownership(
            self.session, self._request(), apply=True
        )

        self.assertEqual("created", first.action)
        self.assertEqual("already_owned", second.action)
        self.assertEqual(first.provider_resource_id, second.provider_resource_id)
        self.assertEqual(1, self.session.scalar(select(func.count(ProviderResource.id))))
        self.assertEqual(
            1,
            self.session.scalar(select(func.count(ProviderResourceOwnership.id))),
        )

    def test_active_ownership_for_another_tenant_is_rejected(self) -> None:
        self._tenant("tenant_b")
        register_provider_resource_ownership(self.session, self._request(), apply=True)

        with self.assertRaisesRegex(
            ProviderResourceOwnershipError, "another tenant"
        ):
            register_provider_resource_ownership(
                self.session,
                self._request(tenant_id="tenant_b"),
                apply=True,
            )

    def test_did_is_normalized_before_lookup_and_storage(self) -> None:
        first = register_provider_resource_ownership(
            self.session,
            self._request(
                resource_kind="did",
                external_id="+55 (71) 3333-4444",
            ),
            apply=True,
        )
        second = register_provider_resource_ownership(
            self.session,
            self._request(resource_kind="did", external_id="+557133334444"),
            apply=True,
        )

        self.assertEqual("+557133334444", first.external_id)
        self.assertEqual("already_owned", second.action)

    def test_missing_or_inactive_tenant_is_rejected(self) -> None:
        self._tenant("inactive", status="inactive")
        with self.assertRaisesRegex(ProviderResourceOwnershipError, "does not exist"):
            register_provider_resource_ownership(
                self.session,
                self._request(tenant_id="missing"),
                apply=False,
            )
        with self.assertRaisesRegex(ProviderResourceOwnershipError, "not active"):
            register_provider_resource_ownership(
                self.session,
                self._request(tenant_id="inactive"),
                apply=False,
            )

    def test_new_open_ownership_cannot_overlap_history(self) -> None:
        register_provider_resource_ownership(self.session, self._request(), apply=True)
        ownership = self.session.scalar(select(ProviderResourceOwnership))
        ownership.valid_to = NOW + timedelta(days=10)
        self.session.flush()

        with self.assertRaisesRegex(ProviderResourceOwnershipError, "overlaps"):
            register_provider_resource_ownership(
                self.session,
                self._request(valid_from=NOW + timedelta(days=5)),
                apply=True,
            )

    def test_same_external_id_is_scoped_by_provider_org(self) -> None:
        first = register_provider_resource_ownership(
            self.session, self._request(), apply=True
        )
        second = register_provider_resource_ownership(
            self.session,
            self._request(provider_org_id="org_enterprise"),
            apply=True,
        )

        self.assertNotEqual(first.provider_resource_id, second.provider_resource_id)
        self.assertEqual(2, self.session.scalar(select(func.count(ProviderResource.id))))


if __name__ == "__main__":
    unittest.main()
