import unittest

from pydantic import ValidationError

from app.tenants.pbsaude.contracts import Provider
from app.tenants.pbsaude.provider_policy import (
    ProviderPolicyConfig,
    apply_provider_policy,
    apply_provider_policy_business_override,
    load_provider_policy,
)


def provider(
    name: str,
    *,
    city: str = "Salvador",
    address: str = "Rua da API, 10",
    code: str | None = None,
) -> Provider:
    return Provider(
        name=name,
        specialty="CARDIOLOGIA",
        address=address,
        city=city,
        neighborhood="Centro",
        phone="(71) 3333-4444",
        provider_code=code,
    )


class ProviderPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        load_provider_policy.cache_clear()
        cls.config = load_provider_policy()

    def apply(self, providers, *, city, query, tenant_id="tenant_demo", config=None, limit=3):
        return apply_provider_policy(
            providers,
            tenant_id=tenant_id,
            city=city,
            query=query,
            max_results=limit,
            enabled=True,
            config=config or self.config,
        )

    def test_loads_versioned_tenant_scoped_configuration(self) -> None:
        self.assertEqual(2, self.config.policy_version)
        self.assertEqual(["tenant_demo"], self.config.tenant_ids)
        self.assertEqual(
            ["ESPECIALIDADE_INVALIDA", "CIDADE_INVALIDA", "CIDADE_SEM_COBERTURA"],
            self.config.business_error_fallback_codes,
        )
        self.assertEqual(
            {"salvador", "goiania", "vitoria_da_conquista", "feira_de_santana"},
            {item.city_key for item in self.config.cities},
        )

    def test_rejects_fallback_provider_without_contact_data(self) -> None:
        payload = self.config.model_dump(mode="json")
        payload["cities"][0]["providers"][0]["phone"] = None

        with self.assertRaisesRegex(ValidationError, "fallback providers require"):
            ProviderPolicyConfig.model_validate(payload)

    def test_rejects_duplicate_provider_keys(self) -> None:
        payload = self.config.model_dump(mode="json")
        payload["cities"][0]["providers"][1]["key"] = payload["cities"][0]["providers"][0]["key"]

        with self.assertRaisesRegex(ValidationError, "provider keys must be unique"):
            ProviderPolicyConfig.model_validate(payload)

    def test_rejects_duplicate_active_priorities(self) -> None:
        payload = self.config.model_dump(mode="json")
        payload["cities"][0]["providers"][1]["priority"] = payload["cities"][0]["providers"][0][
            "priority"
        ]

        with self.assertRaisesRegex(ValidationError, "active provider priorities must be unique"):
            ProviderPolicyConfig.model_validate(payload)

    def test_rejects_unsupported_service_mode(self) -> None:
        payload = self.config.model_dump(mode="json")
        payload["cities"][0]["providers"][0]["services"][0]["service_mode"] = "telephone"

        with self.assertRaisesRegex(ValidationError, "service_mode"):
            ProviderPolicyConfig.model_validate(payload)

    def test_rejects_duplicate_business_error_fallback_codes(self) -> None:
        payload = self.config.model_dump(mode="json")
        payload["business_error_fallback_codes"].append("ESPECIALIDADE_INVALIDA")

        with self.assertRaisesRegex(ValidationError, "business_error_fallback_codes must be unique"):
            ProviderPolicyConfig.model_validate(payload)

    def test_disabled_policy_preserves_upstream_results(self) -> None:
        upstream = [provider("Clínica da API")]

        result = apply_provider_policy(
            upstream,
            tenant_id="tenant_demo",
            city="Salvador",
            query="Cardiologia",
            max_results=3,
            enabled=False,
        )

        self.assertFalse(result.evaluated)
        self.assertEqual(upstream, result.providers)

    def test_tenant_outside_allowlist_preserves_upstream_results(self) -> None:
        upstream = [provider("Clínica da API")]

        result = self.apply(upstream, city="Salvador", query="Cardiologia", tenant_id="tenant_other")

        self.assertFalse(result.evaluated)
        self.assertEqual(upstream, result.providers)

    def test_city_without_policy_preserves_upstream_results(self) -> None:
        upstream = [provider("Clínica da API", city="Ilhéus")]

        result = self.apply(upstream, city="Ilhéus", query="Cardiologia")

        self.assertTrue(result.evaluated)
        self.assertFalse(result.applied)
        self.assertEqual(upstream, result.providers)

    def test_salvador_cardiology_returns_only_centro_medico_pituba(self) -> None:
        upstream = [provider("Clínica não autorizada")]

        result = self.apply(upstream, city="SALVADOR", query="CARDIOLOGIA")

        self.assertTrue(result.applied)
        self.assertEqual(["Centro Médico Pituba"], [item.name for item in result.providers])
        self.assertEqual(1, result.fallback_count)
        self.assertEqual("in_person", result.providers[0].service_mode)

    def test_matching_upstream_provider_keeps_fresh_contact_data(self) -> None:
        upstream = [provider("Centro Médico Pituba", address="Avenida atualizada, 99")]

        result = self.apply(upstream, city="Salvador", query="Cardiologista")

        self.assertEqual("Avenida atualizada, 99", result.providers[0].address)
        self.assertEqual(0, result.fallback_count)

    def test_salvador_endoscopy_returns_only_hospital_pituba(self) -> None:
        result = self.apply([], city="Salvador", query="Endoscopia")

        self.assertEqual(["Hospital Pituba - Rede Grand"], [item.name for item in result.providers])
        self.assertEqual("Endoscopia", result.providers[0].specialty)

    def test_unmatched_specialty_uses_api_results(self) -> None:
        upstream = [provider("Clínica da API")]

        result = self.apply(upstream, city="Salvador", query="Neurologia")

        self.assertTrue(result.evaluated)
        self.assertFalse(result.applied)
        self.assertEqual(upstream, result.providers)

    def test_online_service_omits_physical_address_and_neighborhood(self) -> None:
        result = self.apply(
            [],
            city="VITORIA DA CONQUISTA",
            query="Medicina de Família e Comunidade",
        )

        self.assertEqual(1, len(result.providers))
        online = result.providers[0]
        self.assertEqual("online", online.service_mode)
        self.assertEqual("", online.address)
        self.assertIsNone(online.neighborhood)
        self.assertEqual("0800 940 9778", online.phone)

    def test_business_override_returns_fallback_for_each_allowed_code(self) -> None:
        for error_code in self.config.business_error_fallback_codes:
            with self.subTest(error_code=error_code):
                result = apply_provider_policy_business_override(
                    tenant_id="tenant_demo",
                    city="Vitoria da Conquista",
                    query="Médico da Família",
                    business_error_code=error_code,
                    max_results=3,
                    policy_enabled=True,
                    business_override_enabled=True,
                    config=self.config,
                )

                self.assertTrue(result.applied)
                self.assertEqual(1, result.fallback_count)
                self.assertEqual("online", result.providers[0].service_mode)

    def test_business_override_denies_unlisted_error_or_tenant(self) -> None:
        unsupported_error = apply_provider_policy_business_override(
            tenant_id="tenant_demo",
            city="Vitoria da Conquista",
            query="Médico da Família",
            business_error_code="CPF_INVALIDO",
            max_results=3,
            policy_enabled=True,
            business_override_enabled=True,
            config=self.config,
        )
        other_tenant = apply_provider_policy_business_override(
            tenant_id="tenant_other",
            city="Vitoria da Conquista",
            query="Médico da Família",
            business_error_code="ESPECIALIDADE_INVALIDA",
            max_results=3,
            policy_enabled=True,
            business_override_enabled=True,
            config=self.config,
        )

        self.assertFalse(unsupported_error.applied)
        self.assertFalse(other_tenant.applied)

    def test_business_override_requires_both_feature_flags(self) -> None:
        for policy_enabled, override_enabled in ((False, True), (True, False)):
            with self.subTest(
                policy_enabled=policy_enabled,
                override_enabled=override_enabled,
            ):
                result = apply_provider_policy_business_override(
                    tenant_id="tenant_demo",
                    city="Feira de Santana",
                    query="Médico da Família",
                    business_error_code="CIDADE_SEM_COBERTURA",
                    max_results=3,
                    policy_enabled=policy_enabled,
                    business_override_enabled=override_enabled,
                    config=self.config,
                )
                self.assertFalse(result.applied)

    def test_city_and_service_normalization_handles_accents_and_aliases(self) -> None:
        goiania = self.apply([], city="GOIÂNIA", query="cardiologista")
        feira = self.apply([], city="feira de santana", query="medico de familia")
        ecg = self.apply([], city="salvador", query="eletrocardiograma")
        dermatology = self.apply([], city="salvador", query="eletrocauterização")

        self.assertEqual("Hospital Santa Maria", goiania.providers[0].name)
        self.assertEqual("Centro Médico Rede Grand – Feira de Santana", feira.providers[0].name)
        self.assertEqual("Centro Médico Pituba", ecg.providers[0].name)
        self.assertEqual("Hospital Pituba - Rede Grand", dermatology.providers[0].name)

    def test_priority_mode_places_curated_before_upstream_and_deduplicates(self) -> None:
        city_policy = self.config.cities[0].model_copy(update={"mode": "priority"})
        config = self.config.model_copy(update={"cities": [city_policy]})
        upstream = [provider("Clínica da API"), provider("Centro Médico Pituba")]

        result = self.apply(
            upstream,
            city="Salvador",
            query="Cardiologia",
            config=config,
            limit=3,
        )

        self.assertEqual(["Centro Médico Pituba", "Clínica da API"], [item.name for item in result.providers])

    def test_ensure_mode_preserves_upstream_order_but_protects_curated_from_limit(self) -> None:
        city_policy = self.config.cities[0].model_copy(update={"mode": "ensure"})
        config = self.config.model_copy(update={"cities": [city_policy]})
        upstream = [provider("Clínica A"), provider("Clínica B"), provider("Clínica C")]

        result = self.apply(
            upstream,
            city="Salvador",
            query="Cardiologia",
            config=config,
            limit=3,
        )

        self.assertEqual(["Clínica A", "Clínica B", "Centro Médico Pituba"], [item.name for item in result.providers])

    def test_provider_code_is_internal_and_service_mode_is_serialized(self) -> None:
        item = provider("Clínica", code="provider-123").model_copy(
            update={"service_mode": "hybrid"}
        )

        serialized = item.model_dump()

        self.assertNotIn("provider_code", serialized)
        self.assertEqual("hybrid", serialized["service_mode"])


if __name__ == "__main__":
    unittest.main()
