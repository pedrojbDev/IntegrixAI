from __future__ import annotations

from datetime import datetime, timezone

from ...config import Settings
from ...db import SessionLocal
from ...models.vapi_call_slot_state import VapiCallSlotState
from ...platform.services.vapi_event_ingestion import keyed_hmac, normalize_text
from .catalog import SpecialtyCatalog
from .integration.client import BusinessRuleError


def validate_search_slot_provenance(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    cpf: str | None,
    city: str,
    query: str,
    catalog: SpecialtyCatalog,
) -> None:
    """Reject model-invented inputs before the customer API is called."""
    if not settings.vapi_slot_guard_enabled:
        return
    secret = settings.vapi_slot_state_hmac_secret
    if not secret:
        raise _unconfirmed("cpf")

    session = SessionLocal()
    try:
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            raise _unconfirmed("cpf")
        digits = "".join(character for character in (cpf or "") if character.isdigit())
        if len(digits) != 11 or state.cpf_hmac != keyed_hmac(secret, digits):
            _reopen(state, "cpf")
            session.commit()
            raise _unconfirmed("cpf")
        if keyed_hmac(secret, normalize_text(city)) not in set(state.city_term_hmacs or []):
            _reopen(state, "cidade")
            session.commit()
            raise _unconfirmed("cidade")
        specialty_candidates = _specialty_candidates(query, catalog)
        specialty_hashes = set(state.specialty_term_hmacs or [])
        if not any(keyed_hmac(secret, candidate) in specialty_hashes for candidate in specialty_candidates):
            _reopen(state, "especialidade")
            session.commit()
            raise _unconfirmed("especialidade")
    finally:
        session.close()


def _specialty_candidates(query: str, catalog: SpecialtyCatalog) -> set[str]:
    candidates = {normalize_text(query)}
    canonical = catalog.resolve(query)
    if not canonical:
        return {candidate for candidate in candidates if candidate}
    canonical_normalized = normalize_text(canonical)
    candidates.add(canonical_normalized)
    for alias, values in catalog.by_alias.items():
        if canonical in values:
            candidates.add(alias)
    return {candidate for candidate in candidates if candidate}


def _unconfirmed(field: str) -> BusinessRuleError:
    return BusinessRuleError(
        code="SLOT_UNCONFIRMED",
        field=field,
        message="Confirme o dado informado pelo usuario antes de pesquisar a rede",
        details={"recovery_action": f"collect_{field}", "confirmed": False},
    )


def reopen_slot_collection(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    field: str,
) -> None:
    """Allow the next observed user turn to replace exactly one invalid slot."""
    if not settings.vapi_slot_guard_enabled:
        return
    session = SessionLocal()
    try:
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            return
        _reopen(state, field)
        session.commit()
    finally:
        session.close()


def _reopen(state: VapiCallSlotState, field: str) -> None:
    state.phase = field
    if field == "cpf":
        state.cpf_hmac = None
        state.city_term_hmacs = []
        state.specialty_term_hmacs = []
    elif field == "cidade":
        state.city_term_hmacs = []
        state.specialty_term_hmacs = []
    elif field == "especialidade":
        state.specialty_term_hmacs = []


def _is_expired(value: datetime) -> bool:
    expires_at = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return expires_at <= datetime.now(timezone.utc)
