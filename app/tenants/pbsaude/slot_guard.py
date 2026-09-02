from __future__ import annotations

from datetime import datetime, timezone

from ...config import Settings
from ...db import SessionLocal
from ...models.vapi_call_slot_state import VapiCallSlotState
from ...platform.services.vapi_conversation import keyed_hmac, normalize_text, lock_call
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
        lock_call(session, tenant_id, call_id)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            raise _unconfirmed("cpf")
        if (state.conversation_meta or {}).get("overflow"):
            raise _unconfirmed("cpf")
        if (state.conversation_meta or {}).get("terminal"):
            raise BusinessRuleError(code="CALL_TERMINAL", message="A chamada ja iniciou transferencia ou foi encerrada",
                                    retryable=False, handoff_after_retry=False, attempt=0,
                                    details={"recovery_action": "stop"})
        digits = "".join(character for character in (cpf or "") if character.isdigit())
        if len(digits) != 11 or state.cpf_hmac != keyed_hmac(secret, digits):
            raise _unconfirmed("cpf")
        if keyed_hmac(secret, normalize_text(city)) not in set(state.city_term_hmacs or []):
            raise _unconfirmed("cidade")
        specialty_candidates = _specialty_candidates(query, catalog)
        specialty_hashes = set(state.specialty_term_hmacs or [])
        if not any(keyed_hmac(secret, candidate) in specialty_hashes for candidate in specialty_candidates):
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
        attempt=0,
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
        lock_call(session, tenant_id, call_id)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            return
        _reopen(state, field)
        session.commit()
    finally:
        session.close()


def _reopen(state: VapiCallSlotState, field: str) -> None:
    # A failed model proposal is not evidence that the user's other data is invalid.
    meta = dict(state.conversation_meta or {})
    meta["recovery_field"] = field
    state.conversation_meta = meta
    state.phase = field


def recovery_attempt(*, settings: Settings, tenant_id: str, call_id: str,
                     field: str | None, code: str) -> int:
    """Count failed user evidence once, independent of model retries or batches."""
    if not field:
        return 0
    with SessionLocal() as session:
        lock_call(session, tenant_id, call_id)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            return 0
        meta = dict(state.conversation_meta or {})
        if code == "SLOT_UNCONFIRMED":
            return min(2, int(meta.get("failures", {}).get(field, 0)))
        turn = meta.get("field_turns", {}).get(field)
        if not turn:
            return 0
        attempts = dict(meta.get("recovery_attempts", {}))
        record = dict(attempts.get(field, {}))
        if record.get("turn") != turn:
            record = {"turn": turn, "count": int(record.get("count", 0)) + 1}
        attempts[field] = record
        meta["recovery_attempts"] = attempts
        meta["recovery_field"] = field
        state.conversation_meta = meta
        state.phase = field
        session.commit()
        return int(record.get("count", 0))


def clear_recovery_attempts(*, settings: Settings, tenant_id: str, call_id: str,
                            cpf: str, city: str, query: str, catalog: SpecialtyCatalog) -> None:
    """A successful search ends recovery for the evidence it actually used."""
    if not settings.vapi_slot_guard_enabled:
        return
    secret = settings.vapi_slot_state_hmac_secret
    with SessionLocal() as session:
        lock_call(session, tenant_id, call_id)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            return
        digits = "".join(c for c in cpf if c.isdigit())
        if (state.cpf_hmac != keyed_hmac(secret, digits)
                or keyed_hmac(secret, normalize_text(city)) not in (state.city_term_hmacs or [])
                or not any(keyed_hmac(secret, term) in (state.specialty_term_hmacs or [])
                           for term in _specialty_candidates(query, catalog))):
            return
        meta = dict(state.conversation_meta or {})
        meta.pop("recovery_attempts", None)
        meta.pop("recovery_field", None)
        state.conversation_meta = meta
        session.commit()


def _is_expired(value: datetime) -> bool:
    expires_at = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return expires_at <= datetime.now(timezone.utc)
