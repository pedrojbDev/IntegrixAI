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


if __name__ == "__main__":
    unittest.main()
