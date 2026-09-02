"""PB Saúde conversation reducer. Stored evidence contains hashes, never speech."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ...models.vapi_call_slot_state import VapiCallSlotState
from ...platform.services.vapi_conversation import (
    conversation_turns, event_time, keyed_hmac, lock_call, normalize_text, term_hmacs,
)
from .catalog import get_specialty_catalog

MAX_TURNS = 256
KEYPAD = re.compile(r"(?:user'?s\s+keypad\s+entry|keypad\s+entry)\s*:\s*([0-9\s.#*-]+)", re.I)
NOISE = re.compile(r"^(alo|oi|ola|sim estou ouvindo|esta ouvindo|ta ouvindo|so um momento|um momento|aguarde|pera ai|deixa eu ver|nao entendi)[ !?.]*$")
YES = {"sim", "isso", "isso mesmo", "correto", "certo", "exatamente", "pode", "pode sim"}
ALL = {"todos", "todos os tres", "todos os 3", "os tres", "os 3", "ambos", "as duas", "os dois"}


def _specialties(value: str, catalog) -> set[str]:
    """Exact, longest non-overlapping aliases only; no fuzzy provenance."""
    words = value.split()
    found = set()
    i = 0
    while i < len(words):
        for end in range(min(len(words), i + 6), i, -1):
            phrase = " ".join(words[i:end])
            choices = catalog.by_alias.get(phrase)
            if choices and len(choices) == 1:
                found.add(phrase)
                found.add(normalize_text(choices[0]))
                i = end
                break
        else:
            i += 1
    return found


def _question(value: str) -> str | None:
    # Use the last question/sentence so reading a result does not reopen a slot.
    value = re.split(r"[.!?]", value.rstrip(" .!?"))[-1]
    value = normalize_text(value)
    if any(t in value for t in ("transferir", "atendente", "atendimento humano")):
        return "handoff"
    if any(t in value for t in ("mais alguma", "proxima busca", "proximo pedido", "mais opcoes", "posso continuar")):
        return "continue"
    if any(t in value for t in ("cidade", "municipio")):
        return "cidade"
    if any(t in value for t in ("especialidade", "exame", "procedimento", "qual atendimento")):
        return "especialidade"
    if "cpf" in value and any(t in value for t in ("digite", "digitar", "novamente")):
        return "cpf"
    return None


def _encode(turn: dict, secret: str, catalog) -> dict:
    raw = turn["text"]
    normalized = normalize_text(raw)
    entry = {k: turn[k] for k in ("order", "role")}
    entry["digest"] = keyed_hmac(secret, normalized)
    if turn["role"] == "assistant":
        entry["question"] = _question(raw)
        # A read-back is evidence only after a subsequent explicit assent.
        confirmation = any(t in normalized for t in ("confirmar", "voce quis dizer", "voce quer dizer")) or normalized.endswith("certo")
        if confirmation:
            entry["confirmation"] = sorted(term_hmacs(secret, raw))
            if not entry["question"] and _specialties(normalized, catalog):
                entry["question"] = "especialidade"
            entry["ambiguous"] = " ou " in f" {normalized} "
        return entry

    match = KEYPAD.search(raw)
    if match:
        digits = re.sub(r"\D", "", match.group(1))
        entry["keypad"] = True
        entry["cpf"] = keyed_hmac(secret, digits) if len(digits) == 11 else None
        # Speech surrounding keypad input is not implicitly another slot.
        return entry
    entry["yes"] = normalized in YES
    entry["all"] = normalized in ALL
    entry["noise"] = bool(NOISE.fullmatch(normalized)) or not normalized
    entry["negative"] = normalized in {"nao", "nao e isso", "nenhum", "nenhuma"}
    if entry["noise"] or entry["yes"] or entry["all"] or entry["negative"]:
        return entry
    if "cpf" in normalized or re.search(r"\d{11}", normalized):
        entry["noise"] = True  # Spoken identifiers must never become a city.
        return entry
    entry["terms"] = sorted(term_hmacs(secret, raw))
    specialties = _specialties(normalized, catalog)
    entry["specialties"] = sorted(keyed_hmac(secret, t) for t in specialties)
    location = re.search(r"(?:\bem\s+|\bcidade(?:\s+e|\s+de)?\s+)(.+)", normalized)
    if location:
        # Stop a location phrase before a subsequent explicit search request.
        city = re.split(r"\b(?:quero|preciso|procuro|busco)\b", location.group(1))[0].strip()
        if city and not _specialties(city, catalog):
            entry["city"] = sorted(term_hmacs(secret, city))
    entry["correction"] = bool(re.search(r"\b(?:na verdade|corrigindo|corrigir|trocar|mudar|agora quero)\b", normalized))
    return entry


def _reduce(turns: list[dict]) -> dict:
    result = {"cpf": None, "cidade": [], "especialidade": [], "pending": "cpf",
              "last_user": None, "last_order": -1, "failures": {}, "field_turns": {}}
    confirmation = None
    assistant_seen = False
    for entry in turns:
        if entry["role"] == "assistant":
            assistant_seen = True
            if entry.get("question"):
                result["pending"] = entry["question"]
            confirmation = entry.get("confirmation") if not entry.get("ambiguous") else None
            continue
        result["last_user"] = entry["key"]
        result["last_order"] = entry["order"]
        field = result["pending"]
        if entry.get("noise"):
            continue
        if entry.get("keypad"):
            if entry.get("cpf"):
                result["cpf"] = entry["cpf"]
                result["field_turns"]["cpf"] = entry["key"]
                if field == "cpf":
                    result["pending"] = "cidade" if not result["cidade"] else "especialidade"
                result["failures"]["cpf"] = 0
            else:
                result["cpf"] = None
                result["failures"]["cpf"] = result["failures"].get("cpf", 0) + 1
            continue
        if entry.get("yes") or entry.get("all"):
            if confirmation and field in {"cidade", "especialidade"}:
                result[field] = sorted(set(result[field]) | set(confirmation)) if field == "especialidade" else confirmation
                result["field_turns"][field] = entry["key"]
                result["failures"][field] = 0
            confirmation = None
            continue
        if entry.get("negative"):
            if field in {"cidade", "especialidade"}:
                result["failures"][field] = result["failures"].get(field, 0) + 1
            confirmation = None
            continue
        confirmation = None
        if entry.get("city"):
            result["cidade"] = entry["city"]
            result["field_turns"]["cidade"] = entry["key"]
        if entry.get("specialties"):
            # Keep the whole explicitly requested set across acknowledgements.
            result["especialidade"] = entry["specialties"] if entry.get("correction") else sorted(set(result["especialidade"]) | set(entry["specialties"]))
            result["field_turns"]["especialidade"] = entry["key"]
        if field == "cidade" and entry.get("terms") and not entry.get("city"):
            if not entry.get("specialties"):
                result["cidade"] = entry["terms"]
                result["field_turns"][field] = entry["key"]
            elif not result["cidade"]:
                # A combined answer may contain both slots. Only actually spoken
                # substrings can pass the guard; no guessed city is introduced.
                result["cidade"] = entry["terms"]
                result["field_turns"][field] = entry["key"]
        elif field == "especialidade" and entry.get("terms") and not entry.get("specialties") and not entry.get("city"):
            result["especialidade"] = entry["terms"]
            result["field_turns"][field] = entry["key"]
        for updated_field, turn_key in result["field_turns"].items():
            if turn_key == entry["key"]:
                result["failures"][updated_field] = 0
        # Compatibility for complete user-only snapshots: no assistant text is
        # available to associate a question, so use only still-missing slots.
        if not assistant_seen and result["cpf"] and result["cidade"]:
            result["pending"] = "especialidade"
    return result


def capture_pbsaude_conversation(session, settings, tenant_id: str, call_id: str, message) -> None:
    secret = settings.vapi_slot_state_hmac_secret
    if not secret:
        raise ValueError("Vapi conversation evidence requires a configured HMAC secret")
    revision = event_time(message.get("timestamp"))
    now = datetime.now(timezone.utc)
    retention = timedelta(hours=settings.vapi_slot_state_retention_hours)
    if revision is not None and not (now.timestamp() * 1000 - retention.total_seconds() * 1000
                                     <= revision <= now.timestamp() * 1000 + 300000):
        return  # Old deliveries must not revive expired conversation evidence.
    observed = conversation_turns(message)
    if not observed:
        return
    lock_call(session, tenant_id, call_id)
    state = session.get(VapiCallSlotState, {"tenant_id": tenant_id, "call_id": call_id})
    if state is None:
        state = VapiCallSlotState(tenant_id=tenant_id, call_id=call_id, conversation_meta={})
        session.add(state)
    expired = state.expires_at is not None and state.expires_at.replace(tzinfo=timezone.utc) <= now
    if expired and revision is None:
        return
    meta = dict(state.conversation_meta or {}) if not expired else {}
    ledger = dict(meta.get("turns", {}))
    # A missing timestamp is permitted for full snapshots, but must not replace
    # an already versioned transcript revision of the same turn.
    revision = revision if revision is not None else 0
    catalog = get_specialty_catalog(settings)
    changed = False
    for turn in observed:
        key = keyed_hmac(secret, turn["id"])
        encoded = _encode(turn, secret, catalog)
        encoded.update(key=key, revision=revision)
        old = ledger.get(key)
        if old and old["revision"] >= revision:
            continue
        ledger[key] = encoded
        changed = True
    if not changed:
        return
    if len(ledger) > MAX_TURNS:
        # Fail closed, rather than silently dropping the turns proving a value.
        meta["overflow"] = True
        ledger = dict(sorted(ledger.items(), key=lambda p: p[1]["order"])[-MAX_TURNS:])
    result = _reduce(sorted(ledger.values(), key=lambda e: (e["order"], e["key"])))
    meta.update(turns=ledger, last_user=result["last_user"], last_order=result["last_order"],
                field_turns=result["field_turns"], pending=result["pending"],
                failures=result["failures"], revision=int(meta.get("revision", 0)) + 1)
    state.cpf_hmac = result["cpf"]
    state.city_term_hmacs = result["cidade"]
    state.specialty_term_hmacs = result["especialidade"]
    state.phase = result["pending"]
    state.conversation_meta = meta
    state.last_event_at = max(filter(None, (state.last_event_at.replace(tzinfo=timezone.utc) if state.last_event_at else None,
                                          datetime.fromtimestamp(revision / 1000, timezone.utc) if revision else now)))
    state.expires_at = now + retention
