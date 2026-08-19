import hashlib
from datetime import date
from threading import Lock
from typing import Sequence

from ....config import Settings
from ....utils.chaos import maybe_introduce_chaos
from ....utils.enums import AuthLevel, AuthorizationStatus
from ..contracts import Provider
from .client import AuthenticationError, DataProvider


class MockDataProvider(DataProvider):
    """Deterministic mock that emulates Protheus responses."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._attempts: dict[str, int] = {}
        self._lock = Lock()
        self._providers = self._seed_providers()

    def authenticate_member(self, cpf: str, birthdate: date, call_id: str) -> tuple[str, AuthLevel]:
        maybe_introduce_chaos(self.settings)
        normalized = "".join(filter(str.isdigit, cpf))
        if len(normalized) != 11:
            raise AuthenticationError("CPF invÃ¡lido")

        attempt_key = f"{call_id}:{normalized[-4:]}"
        count = self._bump_attempt(attempt_key)
        if count > self.settings.auth_max_attempts:
            raise AuthenticationError("Limite de tentativas atingido")

        score = (sum(int(digit) for digit in normalized) + birthdate.day + birthdate.month) % 10
        if score % 2 != 0:
            raise AuthenticationError("Credenciais nÃ£o conferem")

        member_id = f"m-{normalized[-4:]}-{birthdate.strftime('%Y%m%d')}"
        return member_id, AuthLevel.HIGH

    def get_authorization_status(self, member_id: str, guia_id: str) -> AuthorizationStatus:
        maybe_introduce_chaos(self.settings)
        digest = int(hashlib.sha1(guia_id.encode()).hexdigest(), 16)
        statuses = list(AuthorizationStatus)
        return statuses[digest % len(statuses)]

    def search_providers(
        self,
        tenant_id: str,
        call_id: str,
        city: str,
        query: str,
        cpf: str | None,
        tipo_atendimento: str | None,
    ) -> Sequence[Provider]:
        maybe_introduce_chaos(self.settings)
        city_key = city.strip().lower()
        query_key = query.strip().lower()

        matches: list[Provider] = []
        for item in self._providers:
            if item.city.lower() != city_key:
                continue
            if query_key in item.name.lower() or query_key in item.specialty.lower():
                matches.append(item)

        if not matches:
            matches = [provider for provider in self._providers if provider.city.lower() == city_key]

        return matches[:5]

    def _bump_attempt(self, key: str) -> int:
        with self._lock:
            new_value = self._attempts.get(key, 0) + 1
            self._attempts[key] = new_value
            return new_value

    def _seed_providers(self) -> list[Provider]:
        data = [
            ("Clínica Alpha", "cardiologia", "Av. Paulista, 1000", "são paulo", "bela vista", "11 3333-1000"),
            ("Centro Beta", "ortopedia", "R. Augusta, 55", "são paulo", "consolação", "11 3333-2000"),
            ("Hospital Vida", "pronto-socorro", "Av. Brasil, 500", "rio de janeiro", "jardim botânico", "21 4000-5000"),
            ("Orto Norte", "ortopedia", "Av. Dom Pedro, 10", "manaus", "centro", "92 3333-9999"),
            ("Cardio Sul", "cardiologia", "R. da Praia, 45", "porto alegre", "centro", "51 4444-8888"),
            ("Diagnostika", "diagnóstico", "Av. Angélica, 200", "são paulo", "santa cecilia", "11 3333-3000"),
            ("Saúde Mais", "clínico geral", "R. XV de Novembro, 12", "curitiba", "centro", "41 2222-1111"),
        ]
        return [
            Provider(
                name=name,
                specialty=specialty,
                address=address,
                city=city,
                neighborhood=neighborhood,
                phone=phone,
            )
            for name, specialty, address, city, neighborhood, phone in data
        ]
