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
CPF_CHANGE = re.compile(r"\b(?:corrigir|corrigindo|trocar|mudar)\b.*\bcpf\b|\bcpf\b.*\b(?:corrigir|corrigindo|trocar|mudar)\b")
CPF_INVALIDATION = re.compile(r"\bcpf\b.*\b(?:errado|incorreto|outro|diferente)\b")
CPF_NEGATED_CHANGE = re.compile(
    r"\bnao\b(?:\s+\w+){0,4}\s+(?:corrigir|corrigindo|trocar|mudar)\b.*\bcpf\b"
    r"|\bcpf\b.*\bnao\b(?:\s+\w+){0,4}\s+(?:corrigir|corrigindo|trocar|mudar)\b"
)
SPOKEN_CPF = re.compile(r"\b(?:(?:esse|este)\s+(?:e|eh|esta|ta)\s+)?(?:meu\s+)?cpf\b|\b\d{11}\b")
NOISE = re.compile(r"^(alo|oi|ola|sim estou ouvindo|esta ouvindo|ta ouvindo|so um momento|um momento|aguarde|pera ai|deixa eu ver|nao entendi)[ !?.]*$")
YES = {"sim", "isso", "isso mesmo", "correto", "certo", "exatamente", "pode", "pode sim"}
ALL = {"todos", "todos os tres", "todos os 3", "os tres", "os 3", "ambos", "as duas", "os dois"}
REFRESH = re.compile(r"\b(?:consulte novamente|atualize a busca|pesquise de novo)\b")
REMOVE = re.compile(r"\b(?:nao (?:quero|preciso|desejo|e)|retire|remova|exclua|cancele|tire|sem|troque|trocar|substitua|substituir)\b")


def _requests(value: str, secret: str, catalog) -> tuple[list[dict], list[dict]]:
    """Retain spoken order and canonical identity, with clause-scoped negation."""
    words = value.split()
    accepted, removed = [], []
    i = 0
    negative = False
    replacing = False
    while i < len(words):
        remaining = " ".join(words[i:])
        marker = REMOVE.match(remaining)
        if marker:
            negative = True
            replacing = marker.group() in {"troque", "trocar", "substitua", "substituir"}
            i += len(marker.group().split())
            continue
        if words[i] in {"quero", "preciso", "desejo", "inclua", "adicione", "mantenha"} or (replacing and words[i] == "por"):
            negative = False
            replacing = False
        for end in range(min(len(words), i + 6), i, -1):
            phrase = " ".join(words[i:end])
            choices = catalog.by_alias.get(phrase)
            if choices and len(choices) == 1:
                canonical = normalize_text(choices[0])
                request = {"canonical": keyed_hmac(secret, canonical),
                           "terms": sorted({keyed_hmac(secret, phrase), keyed_hmac(secret, canonical)})}
                (removed if negative else accepted).append(request)
                i = end
                break
        else:
            i += 1
    return accepted, removed


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
    value = _last_question(value)
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


def _last_question(value: str) -> str:
    sentences = [part.strip() for part in re.split(r"[.!?]", value) if part.strip()]
    while sentences and normalize_text(sentences[-1]) in {"por favor", "obrigado", "obrigada", "por gentileza"}:
        sentences.pop()
    return sentences[-1] if sentences else ""


def _is_cpf_correction(value: str) -> bool:
    return bool("cpf" in value and not CPF_NEGATED_CHANGE.search(value)
                and (CPF_CHANGE.search(value) or CPF_INVALIDATION.search(value)))


def _encode(turn: dict, secret: str, catalog) -> dict:
    raw = turn["text"]
    normalized = normalize_text(raw)
    entry = {k: turn[k] for k in ("order", "role")}
    entry["digest"] = keyed_hmac(secret, normalized)
    if turn["role"] == "assistant":
        entry["question"] = _question(raw)
        # A read-back is evidence only after a subsequent explicit assent.
        question_text = _last_question(raw)
        question_normalized = normalize_text(question_text)
        confirmation = (any(t in question_normalized for t in ("confirmar", "voce quis dizer", "voce quer dizer"))
                        or question_normalized.endswith("certo"))
        if confirmation:
            requests, _ = _requests(question_normalized, secret, catalog)
            if not entry["question"] and requests:
                entry["question"] = "especialidade"
            entry["confirmation_requests"] = requests
            city = re.search(r"\b(?:cidade|municipio)(?: e| de| para atendimento e)?\s+(.+?)\s+certo$", question_normalized)
            if not city:
                city = re.search(r"\bconfirmar\s+(?:a|o)\s+(?:cidade|municipio)(?: e| de)?\s+(.+)$", question_normalized)
            implicit = re.search(r"\bvoce (?:quis|quer) dizer\s+(.+?)(?:\s+certo)?$", question_normalized)
            candidate = city.group(1) if city else implicit.group(1) if implicit and not requests else ""
            entry["confirmation"] = sorted(term_hmacs(secret, candidate)) if candidate else []
            entry["ambiguous"] = " ou " in f" {question_normalized} "
        entry["unrelated_question"] = bool("?" in raw and not entry["question"] and not confirmation)
        return entry

    match = KEYPAD.search(raw)
    if match:
        digits = re.sub(r"\D", "", match.group(1))
        entry["keypad"] = True
        entry["cpf"] = keyed_hmac(secret, digits) if len(digits) == 11 else None
        # Vapi may combine a keypad event and speech in one transcript turn.
        # Keep their evidence separate: keypad digits are CPF-only, while the
        # remaining speech can still prove a city or specialty.
        raw = raw[:match.start()] + raw[match.end():]
        normalized = normalize_text(raw)
    entry["yes"] = normalized in YES
    entry["all"] = normalized in ALL
    entry["noise"] = bool(NOISE.fullmatch(normalized)) or not normalized
    entry["negative"] = normalized in {"nao", "nao e isso", "nenhum", "nenhuma"}
    entry["cpf_correction"] = _is_cpf_correction(normalized)
    refresh = REFRESH.search(normalized)
    entry["refresh"] = bool(refresh and not re.search(r"\bnao\b", normalized[:refresh.start()]))
    if refresh:
        normalized = REFRESH.sub("", normalized).strip()
        # Refresh/declined refresh is an operation, never a new slot value.
        if normalized in {"", "nao", "por favor", "nao por favor"}:
            entry["noise"] = True
    entry["correction"] = bool(re.search(r"\b(?:na verdade|corrigindo|corrigir|trocar|mudar|agora quero)\b", normalized))
    if entry["noise"] or entry["yes"] or entry["all"] or entry["negative"]:
        return entry
    spoken_cpf = "cpf" in normalized or bool(re.search(r"\d{11}", normalized))
    if spoken_cpf:
        # Discard spoken identifier context but retain independently spoken
        # city and specialty evidence from a combined keypad transcript.
        normalized = " ".join(SPOKEN_CPF.sub(" ", normalized).split())
        entry["noise"] = bool(NOISE.fullmatch(normalized)) or not normalized
        if entry["noise"]:
            return entry
    specialties = _specialties(normalized, catalog)
    requests, removed = _requests(normalized, secret, catalog)
    entry["requests"] = requests
    entry["removed_requests"] = removed
    entry["ambiguous_removal"] = bool(REMOVE.search(normalized) and not removed and not spoken_cpf)
    # A new affirmative request ends the previous negation's scope. Specialty
    # evidence in the same turn must not hide an explicitly rejected location.
    clauses = re.split(r"(?<!nao )\b(?:quero|preciso|desejo|procuro|busco)\b", normalized)
    entry["negated_city"] = any(
        re.search(r"\bnao\b.*\b(?:cidade|moro|em)\b", clause) for clause in clauses
    )
    location = re.search(r"(?:\bem\s+|\bcidade(?:\s+e|\s+de)?\s+)(.+)", normalized)
    if spoken_cpf and not specialties and not location:
        entry["noise"] = True
        return entry
    entry["terms"] = sorted(term_hmacs(secret, normalized))
    entry["specialties"] = sorted({term for request in requests for term in request["terms"]})
    if location:
        # Stop a location phrase before a subsequent explicit search request.
        city = re.split(r"\b(?:quero|preciso|procuro|busco)\b", location.group(1))[0].strip()
        if city and not _specialties(city, catalog):
            entry["city"] = sorted(term_hmacs(secret, city))
    return entry


def _confirmation_for_pending(entry: dict, result: dict) -> tuple[str, list[str], list[dict]] | None:
    """Bind an assent only to evidence for the latest actual question."""
    field = result["pending"]
    if field not in {"cidade", "especialidade"}:
        return None
    if field == "especialidade":
        requests = entry.get("confirmation_requests", [])
        values = sorted({term for request in requests for term in request["terms"]})
        return (field, values, requests) if values else None
    values = entry.get("confirmation") or []
    return (field, values, []) if values else None


def _update_requests(result: dict, additions: list[dict], removals: tuple | list[dict] = ()) -> None:
    removed = {request["canonical"] for request in removals}
    removed_terms = {term for request in removals for term in request["terms"]}
    current = {request["canonical"]: request for request in result["active_requests"]
               if request["canonical"] not in removed and not (set(request["terms"]) & removed_terms)}
    for request in additions:
        old = current.get(request["canonical"])
        current[request["canonical"]] = {**request, "terms": sorted(set(request["terms"]) | set(old["terms"] if old else []))}
    result["active_requests"] = list(current.values())
    result["especialidade"] = sorted({term for request in current.values() for term in request["terms"]})


def _reduce(
    turns: list[dict],
    *,
    recovery_field: str | None = None,
    recovery_anchor_user: str | None = None,
) -> dict:
    result = {"cpf": None, "cidade": [], "especialidade": [], "pending": "cpf",
              "last_user": None, "last_order": -1, "failures": {}, "field_turns": {},
              "active_requests": [], "refresh_turn": None}
    confirmation = None
    assistant_seen = False
    unrelated_question = False
    anchor_entry = next((entry for entry in turns if entry.get("key") == recovery_anchor_user), None)
    anchor_order = anchor_entry.get("order") if anchor_entry else None
    for entry in turns:
        recovery_active = (
            recovery_field in {"cpf", "cidade", "especialidade"}
            and anchor_order is not None
            and entry["order"] > anchor_order
        )
        if entry["role"] == "assistant":
            assistant_seen = True
            unrelated_question = entry.get("unrelated_question", False)
            if recovery_active:
                # Agent turns cannot redirect a backend-pinned recovery field.
                # A same-field read-back can still provide an explicit proposal
                # for a subsequent short confirmation.
                result["pending"] = recovery_field
            elif entry.get("question"):
                result["pending"] = entry["question"]
            confirmation = (
                _confirmation_for_pending(entry, result)
                if (entry.get("confirmation") or entry.get("confirmation_requests")) and not entry.get("ambiguous") else None
            )
            continue
        result["last_user"] = entry["key"]
        result["last_order"] = entry["order"]
        field = recovery_field if recovery_active else result["pending"]
        if entry.get("refresh"):
            result["refresh_turn"] = entry["key"]
        if entry.get("cpf_correction"):
            # A spoken correction is explicit evidence that the previous CPF
            # must not authorize a search while the replacement is collected.
            result["cpf"] = None
            result["field_turns"].pop("cpf", None)
            result["pending"] = "cpf"
            field = "cpf"
        if entry.get("noise") and not entry.get("keypad"):
            continue
        if entry.get("keypad"):
            # A keypad marker outside CPF collection is incidental. It must
            # neither replace nor invalidate a valid CPF.
            if field == "cpf":
                if entry.get("cpf"):
                    result["cpf"] = entry["cpf"]
                    result["field_turns"]["cpf"] = entry["key"]
                    result["pending"] = "cidade" if not result["cidade"] else "especialidade"
                    result["failures"]["cpf"] = 0
                else:
                    result["cpf"] = None
                    result["failures"]["cpf"] = result["failures"].get("cpf", 0) + 1
            field = result["pending"]
        if entry.get("yes") or entry.get("all"):
            if confirmation:
                confirmed_field, confirmed_values, requests = confirmation
                if confirmed_field == "especialidade":
                    # A single corrected read-back replaces the previous request;
                    # a confirmation within an explicitly requested set preserves it.
                    if len(result["active_requests"]) == 1 and not (set(result["especialidade"]) & set(confirmed_values)):
                        result["active_requests"] = []
                    _update_requests(result, requests)
                else:
                    result[confirmed_field] = confirmed_values
                result["field_turns"][confirmed_field] = entry["key"]
                result["failures"][confirmed_field] = 0
            confirmation = None
            continue
        if entry.get("negative"):
            if field in {"cidade", "especialidade"} and not unrelated_question:
                if field == "especialidade" and confirmation:
                    _update_requests(result, [], confirmation[2])
                else:
                    result[field] = []
                    if field == "especialidade":
                        result["active_requests"] = []
                result["field_turns"].pop(field, None)
                result["failures"][field] = result["failures"].get(field, 0) + 1
            confirmation = None
            continue
        confirmation = None
        if entry.get("negated_city") or (entry.get("ambiguous_removal") and (
                field == "cidade" or bool(set(entry.get("terms", [])) & set(result["cidade"]))
        )):
            result["cidade"] = []
            result["field_turns"].pop("cidade", None)
            result["pending"] = "cidade"
            result["failures"]["cidade"] = result["failures"].get("cidade", 0) + 1
            # Keep an explicit specialty swap while asking the caller to clarify
            # the location. Never reinstate the first (negated) location below.
            if entry.get("requests") or entry.get("removed_requests"):
                if entry.get("correction") and not entry.get("removed_requests"):
                    result["active_requests"] = []
                _update_requests(result, entry.get("requests", []), entry.get("removed_requests", []))
                result["field_turns"]["especialidade"] = entry["key"]
                result["failures"]["especialidade"] = 0
            continue
        if entry.get("ambiguous_removal"):
            result["especialidade"] = []
            result["active_requests"] = []
            result["field_turns"].pop("especialidade", None)
            result["pending"] = "especialidade"
            result["failures"]["especialidade"] = result["failures"].get("especialidade", 0) + 1
            continue
        if entry.get("city"):
            result["cidade"] = entry["city"]
            result["field_turns"]["cidade"] = entry["key"]
        if entry.get("specialties") or entry.get("removed_requests"):
            # Keep the whole explicitly requested set across acknowledgements.
            if entry.get("correction") and not entry.get("removed_requests"):
                result["active_requests"] = []
            requests = entry.get("requests")
            if requests is None:
                # Schema-one ledger entries stored only a hashed unordered set.
                # Keep its evidence; targeted removal conservatively drops any
                # inseparable legacy group containing the rejected specialty.
                requests = [{"canonical": entry["digest"], "terms": entry["specialties"]}]
            _update_requests(result, requests, entry.get("removed_requests", []))
            result["field_turns"]["especialidade"] = entry["key"]
        if field == "cidade" and entry.get("terms") and not entry.get("city") and not entry.get("removed_requests"):
            if not entry.get("specialties"):
                result["cidade"] = entry["terms"]
                result["field_turns"][field] = entry["key"]
            elif not result["cidade"]:
                # A combined answer may contain both slots. Only actually spoken
                # substrings can pass the guard; no guessed city is introduced.
                result["cidade"] = entry["terms"]
                result["field_turns"][field] = entry["key"]
        elif field == "especialidade" and entry.get("terms") and not entry.get("specialties") and not entry.get("city") and not entry.get("removed_requests"):
            result["especialidade"] = entry["terms"]
            result["active_requests"] = [{"canonical": entry["digest"], "terms": entry["terms"]}]
            result["field_turns"][field] = entry["key"]
        for updated_field, turn_key in result["field_turns"].items():
            if turn_key == entry["key"]:
                result["failures"][updated_field] = 0
        # Compatibility for complete user-only snapshots: no assistant text is
        # available to associate a question, so use only still-missing slots.
        if not assistant_seen and result["cpf"] and result["cidade"]:
            result["pending"] = "especialidade"
    if recovery_field in {"cpf", "cidade", "especialidade"}:
        result["pending"] = recovery_field
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
    result = _reduce(
        sorted(ledger.values(), key=lambda e: (e["order"], e["key"])),
        recovery_field=meta.get("recovery_field") if settings.pbsaude_vapi_recovery_gate_enabled else None,
        recovery_anchor_user=(
            meta.get("recovery_anchor_user")
            if settings.pbsaude_vapi_recovery_gate_enabled
            else None
        ),
    )
    meta.update(turns=ledger, last_user=result["last_user"], last_order=result["last_order"],
                field_turns=result["field_turns"], pending=result["pending"],
                active_requests=result["active_requests"], refresh_turn=result["refresh_turn"], schema_version=2,
                failures=result["failures"], revision=int(meta.get("revision", 0)) + 1)
    state.cpf_hmac = result["cpf"]
    state.city_term_hmacs = result["cidade"]
    state.specialty_term_hmacs = result["especialidade"]
    state.phase = result["pending"]
    state.conversation_meta = meta
    state.last_event_at = max(filter(None, (state.last_event_at.replace(tzinfo=timezone.utc) if state.last_event_at else None,
                                          datetime.fromtimestamp(revision / 1000, timezone.utc) if revision else now)))
    state.expires_at = now + retention
