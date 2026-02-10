from abc import ABC, abstractmethod
from datetime import date
from typing import Sequence

from ..config import Settings
from ..schemas.tools import Provider
from ..utils.enums import AuthLevel, AuthorizationStatus


class AuthenticationError(Exception):
    """Raised when member authentication fails."""


class ServiceUnavailable(Exception):
    """Raised when upstream/unimplemented provider cannot serve the request."""


class DataProvider(ABC):
    @abstractmethod
    def authenticate_member(self, cpf: str, birthdate: date, call_id: str) -> tuple[str, AuthLevel]:
        ...

    @abstractmethod
    def get_authorization_status(self, member_id: str, guia_id: str) -> AuthorizationStatus:
        ...

    @abstractmethod
    def search_providers(
        self, city: str, neighborhood: str | None, query: str
    ) -> Sequence[Provider]:
        ...


def get_data_provider(settings: Settings) -> DataProvider:
    if settings.data_mode == "mock":
        from .mock_provider import MockDataProvider

        return MockDataProvider(settings)

    if settings.data_mode == "external_api":
        from .external_api_provider import ExternalApiDataProvider

        return ExternalApiDataProvider(settings)

    raise ServiceUnavailable(f"Unsupported DATA_MODE: {settings.data_mode}")
