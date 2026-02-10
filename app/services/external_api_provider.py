from datetime import date
from typing import Sequence

from ..config import Settings
from ..schemas.tools import Provider
from ..utils.enums import AuthLevel, AuthorizationStatus
from .data_provider import DataProvider, ServiceUnavailable


class ExternalApiDataProvider(DataProvider):
    """
    Placeholder for the customer integration.
    Keep this class stable so plugging the real API later is only adapter work.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._validate_config()

    def authenticate_member(self, cpf: str, birthdate: date, call_id: str) -> tuple[str, AuthLevel]:
        raise ServiceUnavailable("External API authenticate_member not implemented")

    def get_authorization_status(self, member_id: str, guia_id: str) -> AuthorizationStatus:
        raise ServiceUnavailable("External API get_authorization_status not implemented")

    def search_providers(
        self, city: str, neighborhood: str | None, query: str
    ) -> Sequence[Provider]:
        raise ServiceUnavailable("External API search_providers not implemented")

    def _validate_config(self) -> None:
        if not self.settings.external_api_base_url:
            raise ServiceUnavailable("EXTERNAL_API_BASE_URL is required when DATA_MODE=external_api")
        if self.settings.external_api_auth_type == "bearer" and not self.settings.external_api_token:
            raise ServiceUnavailable("EXTERNAL_API_TOKEN is required when EXTERNAL_API_AUTH_TYPE=bearer")
