from __future__ import annotations

from datetime import datetime, timezone
from contextlib import nullcontext
from sqlalchemy.orm import Session

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
    session: Session | None = None,
) -> None:
    """Reject model-invented inputs before the customer API is called."""
    if not settings.vapi_slot_guard_enabled:
        return
    secret = settings.vapi_slot_state_hmac_secret
    if not secret:
        raise _unconfirmed("cpf")

    with (SessionLocal() if session is None else nullcontext(session)) as session:
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


def enforce_recovery_gate(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    cpf: str | None,
    city: str,
    query: str,
    session: Session | None = None,
) -> None:
    """Release a pinned field only for newer matching user evidence."""
    if not (settings.vapi_slot_guard_enabled and settings.pbsaude_vapi_recovery_gate_enabled):
        return
    owns_session = session is None
    with (SessionLocal() if owns_session else nullcontext(session)) as session:
        lock_call(session, tenant_id, call_id)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            return
        meta = dict(state.conversation_meta or {})
        field = meta.get("recovery_field")
        if field not in {"cpf", "cidade", "especialidade"}:
            return
        anchor_order = _turn_order(meta, meta.get("recovery_anchor_user"))
        evidence_turn = meta.get("field_turns", {}).get(field)
        evidence_order = _turn_order(meta, evidence_turn)
        eligible = (
            evidence_order is not None
            and anchor_order is not None
            and evidence_order > anchor_order
        )
        supplied_hmac = _argument_hmac(
            settings.vapi_slot_state_hmac_secret,
            field,
            cpf=cpf,
            city=city,
            query=query,
        )
        if not eligible or not supplied_hmac or not _matches_field(state, field, supplied_hmac):
            raise _user_turn_required(field)
        # Keep the attempt ledger pinned until the full search succeeds. A
        # catalog/provider business rejection means this newer turn was still
        # invalid and must become the next recovery anchor.


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


def _user_turn_required(field: str) -> BusinessRuleError:
    return BusinessRuleError(
        code="USER_TURN_REQUIRED",
        field=field,
        message="Aguarde uma nova resposta do usuario antes de pesquisar",
        details={"recovery_action": f"collect_{field}", "confirmed": False},
        retryable=True,
        handoff_after_retry=False,
        attempt=0,
    )


def reopen_slot_collection(
    *,
    settings: Settings,
    tenant_id: str,
    call_id: str,
    field: str,
    session: Session | None = None,
) -> None:
    """Allow the next observed user turn to replace exactly one invalid slot."""
    if not settings.vapi_slot_guard_enabled:
        return
    owns_session = session is None
    with (SessionLocal() if owns_session else nullcontext(session)) as session:
        lock_call(session, tenant_id, call_id)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            return
        _reopen(state, field)
        if owns_session:
            session.commit()


def _reopen(state: VapiCallSlotState, field: str) -> None:
    # A failed model proposal is not evidence that the user's other data is invalid.
    meta = dict(state.conversation_meta or {})
    meta["recovery_field"] = field
    state.conversation_meta = meta
    state.phase = field


def recovery_attempt(*, settings: Settings, tenant_id: str, call_id: str,
                     field: str | None, code: str, rejected_value: str | None = None,
                     session: Session | None = None) -> int:
    """Count failed user evidence once, independent of model retries or batches."""
    if not field:
        return 0
    owns_session = session is None
    with (SessionLocal() if owns_session else nullcontext(session)) as session:
        lock_call(session, tenant_id, call_id)
        state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
        if state is None or _is_expired(state.expires_at):
            return 0
        meta = dict(state.conversation_meta or {})
        if settings.pbsaude_vapi_recovery_gate_enabled:
            turn = meta.get("field_turns", {}).get(field)
            attempts = dict(meta.get("recovery_attempts", {}))
            record = dict(attempts.get(field, {}))
            if code != "SLOT_UNCONFIRMED" and turn and record.get("turn") != turn:
                record = {"turn": turn, "count": int(record.get("count", 0)) + 1}
            attempts[field] = record
            meta.update(
                recovery_attempts=attempts,
                recovery_field=field,
                recovery_anchor_user=meta.get("last_user"),
                recovery_code=code,
                rejected_attempt_hmac=_argument_value_hmac(
                    settings.vapi_slot_state_hmac_secret,
                    field,
                    rejected_value,
                ),
            )
            state.conversation_meta = meta
            state.phase = field
            if owns_session:
                session.commit()
            return 0 if code == "SLOT_UNCONFIRMED" else int(record.get("count", 0))
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
        if owns_session:
            session.commit()
        return int(record.get("count", 0))


def clear_recovery_attempts(*, settings: Settings, tenant_id: str, call_id: str,
                            cpf: str, city: str, query: str, catalog: SpecialtyCatalog,
                            session: Session | None = None) -> None:
    """A successful search ends recovery for the evidence it actually used."""
    if not settings.vapi_slot_guard_enabled:
        return
    secret = settings.vapi_slot_state_hmac_secret
    owns_session = session is None
    with (SessionLocal() if owns_session else nullcontext(session)) as session:
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
        _clear_recovery_meta(meta)
        state.conversation_meta = meta
        if owns_session:
            session.commit()


def _is_expired(value: datetime) -> bool:
    expires_at = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def _clear_recovery_meta(meta: dict) -> None:
    for key in (
        "recovery_attempts",
        "recovery_field",
        "recovery_anchor_user",
        "recovery_code",
        "rejected_attempt_hmac",
    ):
        meta.pop(key, None)


def _turn_order(meta: dict, turn_key: str | None) -> float | None:
    if not turn_key:
        return None
    turn = meta.get("turns", {}).get(turn_key)
    order = turn.get("order") if isinstance(turn, dict) else None
    return float(order) if isinstance(order, (int, float)) else None


def _argument_value_hmac(secret: str | None, field: str, value: str | None) -> str | None:
    if not secret:
        return None
    if field == "cpf":
        normalized = "".join(character for character in (value or "") if character.isdigit())
    else:
        normalized = normalize_text(value or "")
    return keyed_hmac(secret, normalized) if normalized else None


def _argument_hmac(secret: str | None, field: str, *, cpf: str | None, city: str, query: str) -> str | None:
    value = cpf if field == "cpf" else city if field == "cidade" else query
    return _argument_value_hmac(secret, field, value)


def _matches_field(state: VapiCallSlotState, field: str, supplied_hmac: str) -> bool:
    if field == "cpf":
        return state.cpf_hmac == supplied_hmac
    if field == "cidade":
        return supplied_hmac in set(state.city_term_hmacs or [])
    return supplied_hmac in set(state.specialty_term_hmacs or [])
