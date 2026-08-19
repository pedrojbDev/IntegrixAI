import unittest

from app.tenants.pbsaude.integration.translator import normalize_providers


class ProviderTranslatorTests(unittest.TestCase):
    def _normalize(self, provider_payload: dict, *, max_results: int = 5):
        return normalize_providers(
            {"prestadores": [provider_payload]},
            city="Salvador",
            query="cardiologia",
            max_results=max_results,
        )

    def test_prefers_fantasia_when_present(self) -> None:
        providers = self._normalize(
            {
                "nome": "HOSPITAL DA BAHIA LTDA",
                "fantasia": "Hospital da Bahia",
                "endereco": "Rua A, 123",
                "bairro": "Centro",
                "telefone": "71999999999",
            }
        )

        self.assertEqual("Hospital da Bahia", providers[0].name)

    def test_falls_back_to_nome_when_fantasia_is_empty(self) -> None:
        providers = self._normalize(
            {
                "nome": "HOSPITAL DA BAHIA LTDA",
                "fantasia": "",
                "endereco": "Rua A, 123",
                "bairro": "Centro",
                "telefone": "71999999999",
            }
        )

        self.assertEqual("HOSPITAL DA BAHIA LTDA", providers[0].name)

    def test_falls_back_to_nome_when_fantasia_is_whitespace(self) -> None:
        providers = self._normalize(
            {
                "nome": "HOSPITAL DA BAHIA LTDA",
                "fantasia": "   ",
                "endereco": "Rua A, 123",
                "bairro": "Centro",
                "telefone": "71999999999",
            }
        )

        self.assertEqual("HOSPITAL DA BAHIA LTDA", providers[0].name)

    def test_falls_back_to_nome_when_fantasia_is_missing(self) -> None:
        providers = self._normalize(
            {
                "nome": "HOSPITAL DA BAHIA LTDA",
                "endereco": "Rua A, 123",
                "bairro": "Centro",
                "telefone": "71999999999",
            }
        )

        self.assertEqual("HOSPITAL DA BAHIA LTDA", providers[0].name)

    def test_falls_back_to_name_when_nome_is_missing(self) -> None:
        providers = self._normalize(
            {
                "name": "Hospital English Name",
                "endereco": "Rua A, 123",
                "bairro": "Centro",
                "telefone": "71999999999",
            }
        )

        self.assertEqual("Hospital English Name", providers[0].name)

    def test_normalizes_whitespace_in_fantasia(self) -> None:
        providers = self._normalize(
            {
                "nome": "HOSPITAL DA BAHIA LTDA",
                "fantasia": "  Hospital   da   Bahia  ",
                "endereco": "Rua A, 123",
                "bairro": "Centro",
                "telefone": "71999999999",
            }
        )

        self.assertEqual("Hospital da Bahia", providers[0].name)

    def test_keeps_other_fields_and_max_results_behavior(self) -> None:
        providers = normalize_providers(
            {
                "prestadores": [
                    {
                        "nome": "HOSPITAL DA BAHIA LTDA",
                        "fantasia": "Hospital da Bahia",
                        "endereco": "Rua A, 123",
                        "bairro": "Centro",
                        "telefone": "71999999999",
                        "codigoPrestador": "prestador-123",
                    },
                    {
                        "nome": "CLINICA B LTDA",
                        "fantasia": "Clinica B",
                        "endereco": "Rua B, 456",
                        "bairro": "Pituba",
                        "telefone": "7133334444",
                    },
                ]
            },
            city="Salvador",
            query="cardiologia",
            max_results=1,
        )

        self.assertEqual(1, len(providers))
        self.assertEqual("Hospital da Bahia", providers[0].name)
        self.assertEqual("cardiologia", providers[0].specialty)
        self.assertEqual("Rua A, 123", providers[0].address)
        self.assertEqual("Salvador", providers[0].city)
        self.assertEqual("Centro", providers[0].neighborhood)
        self.assertEqual("(71) 99999-9999", providers[0].phone)
        self.assertEqual("prestador-123", providers[0].provider_code)
        self.assertNotIn("provider_code", providers[0].model_dump())

    def test_adds_controlled_accents_to_provider_presentation_fields(self) -> None:
        providers = normalize_providers(
            {
                "prestadores": [
                    {
                        "nome": "CENTRO MEDICO PITUBA - REDE GRAND",
                        "endereco": "das Hortensias,274 EDIF ANTONIO F SILVANY LOJA 01",
                        "bairro": "Pituba",
                        "telefone": "7100000000",
                    },
                    {
                        "nome": "COOPERATIVA MEDICORP",
                        "endereco": "Professor Magalhaes Neto,1550",
                        "bairro": "Pituba",
                        "telefone": "7100000000",
                    },
                ]
            },
            city="Salvador",
            query="clinico geral",
            max_results=5,
        )

        self.assertEqual("CENTRO MÉDICO PITUBA - REDE GRAND", providers[0].name)
        self.assertEqual(
            "Rua das Hortênsias,274 EDIF ANTÔNIO F SILVANY LOJA 01",
            providers[0].address,
        )
        self.assertEqual("clínico geral", providers[0].specialty)
        self.assertEqual("Salvador", providers[0].city)
        self.assertEqual("COOPERATIVA MEDICORP", providers[1].name)
        self.assertEqual("Avenida Professor Magalhães Neto,1550", providers[1].address)

    def test_expands_address_prefix_and_uses_explicit_street_type(self) -> None:
        providers = normalize_providers(
            {
                "prestadores": [
                    {
                        "nome": "Hospital A",
                        "endereco": "Av. Paulista, 1000",
                        "telefone": "1133331000",
                    },
                    {
                        "nome": "Hospital B",
                        "endereco": "Brasil, 500",
                        "tipoLogradouro": "AV",
                        "telefone": "1133332000",
                    },
                    {
                        "nome": "Hospital C",
                        "endereco": "Unidade Assistencial, 20",
                        "telefone": "1133333000",
                    },
                ]
            },
            city="Salvador",
            query="cardiologia",
            max_results=5,
        )

        self.assertEqual("Avenida Paulista, 1000", providers[0].address)
        self.assertEqual("Avenida Brasil, 500", providers[1].address)
        self.assertEqual("Unidade Assistencial, 20", providers[2].address)

    def test_does_not_apply_known_address_type_outside_its_location(self) -> None:
        providers = normalize_providers(
            {
                "prestadores": [
                    {
                        "nome": "Hospital A",
                        "endereco": "das Hortensias, 10",
                        "bairro": "Centro",
                        "telefone": "1133331000",
                    }
                ]
            },
            city="Outra Cidade",
            query="cardiologia",
            max_results=5,
        )

        self.assertEqual("das Hortênsias, 10", providers[0].address)

    def test_preserves_existing_unicode_accents(self) -> None:
        providers = self._normalize(
            {
                "nome": "Clínica São José",
                "endereco": "Rua João de Sá, 10",
                "bairro": "Graça",
                "telefone": "71999999999",
            }
        )

        self.assertEqual("Clínica São José", providers[0].name)
        self.assertEqual("Rua João de Sá, 10", providers[0].address)
        self.assertEqual("Graça", providers[0].neighborhood)


if __name__ == "__main__":
    unittest.main()
