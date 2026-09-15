from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from ...config import Settings
from .specialty_aliases import AMBIGUOUS_SPECIALTY_TERMS, DEFAULT_SPECIALTY_ALIASES

FILLER_WORDS = {
    "de",
    "do",
    "da",
    "dos",
    "das",
    "um",
    "uma",
    "para",
    "por",
    "com",
    "o",
    "a",
    "os",
    "as",
    "precisa",
    "preciso",
    "quero",
    "gostaria",
    "consulta",
    "consultar",
    "especialista",
    "especialidade",
    "medico",
    "medica",
}


def _normalize_text(value: str) -> str:
    cleaned = value.replace("\xa0", " ")
    cleaned = " ".join(cleaned.strip().split())
    normalized = unicodedata.normalize("NFKD", cleaned)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[^a-z0-9 ]+", " ", ascii_only)
    return " ".join(ascii_only.split())


@dataclass(slots=True)
class SpecialtyCatalog:
    by_normalized: dict[str, str]
    by_alias: dict[str, tuple[str, ...]]
    passthrough_unknown: bool = False

    def _candidate_keys(self, raw_value: str) -> list[str]:
        normalized = _normalize_text(raw_value)
        if not normalized:
            return []

        candidates = {normalized}
        words = [word for word in normalized.split() if word not in FILLER_WORDS]
        if words:
            candidates.add(" ".join(words))
        candidates.update(words)

        expanded: set[str] = set()
        for candidate in candidates:
            expanded.add(candidate)
            expanded.update(_role_to_specialty_aliases(candidate))

        return sorted((item for item in expanded if item), key=len, reverse=True)

    def resolve(self, raw_value: str) -> str | None:
        if _normalize_text(raw_value) in AMBIGUOUS_SPECIALTY_TERMS:
            return None
        candidate_keys = self._candidate_keys(raw_value)
        if not candidate_keys:
            return None

        prefer_pediatric = _query_prefers_pediatric(raw_value)
        for candidate in candidate_keys:
            options = self.by_alias.get(candidate)
            if options:
                return _pick_best_option(options, prefer_pediatric)

        if self.passthrough_unknown:
            return " ".join(raw_value.strip().split()) or None
        return None

    def suggest(self, raw_value: str, limit: int = 3) -> list[str]:
        candidate_keys = self._candidate_keys(raw_value)
        if not candidate_keys:
            return []

        # Fuzzy suggestions are only hints, never provenance.  Compare the
        # complete phrase first and require either a meaningful token in
        # common or a close single-token typo.  Without this guard phrases
        # such as "médico da família" matched unrelated aliases sharing only
        # the generic words "médico" and "da".
        query_key = candidate_keys[0]
        query_tokens = set(query_key.split())
        query_core = query_tokens - FILLER_WORDS
        query_is_single_token = len(_normalize_text(raw_value).split()) == 1
        ranked_keys: list[tuple[float, str]] = []
        for alias_key in self.by_alias:
            ratio = SequenceMatcher(None, query_key, alias_key).ratio()
            if ratio < 0.78:
                continue
            alias_core = set(alias_key.split()) - FILLER_WORDS
            if not (query_core & alias_core) and not query_is_single_token:
                continue
            ranked_keys.append((ratio, alias_key))
        ranked_keys.sort(key=lambda item: (-item[0], item[1]))
        out: list[str] = []
        for _, key in ranked_keys[: limit * 2]:
            for candidate in self.by_alias[key]:
                if candidate not in out:
                    out.append(candidate)
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
        return out

    @property
    def is_enabled(self) -> bool:
        return bool(self.by_normalized)


def _role_to_specialty_aliases(term: str) -> set[str]:
    aliases: set[str] = set()
    tokens = term.split()
    for token in tokens or [term]:
        aliases.update(_role_token_to_specialty(token))
    return aliases


def _role_token_to_specialty(token: str) -> set[str]:
    out = {token}
    if token.endswith("ologista") and len(token) > 9:
        out.add(token[:-8] + "ologia")
    if token.endswith("iatra") and len(token) > 6:
        out.add(token[:-5] + "iatria")
    if token.endswith("opedista") and len(token) > 8:
        out.add(token[:-7] + "opedia")
    if token.endswith("terapeuta") and len(token) > 10:
        out.add(token[:-9] + "terapia")

    manual_pairs = {
        "dermatologista": "dermatologia",
        "cardiologista": "cardiologia",
        "nutricionista": "nutricao",
        "anestesista": "anestesiologia",
        "clinico": "clinico geral",
    }
    if token in manual_pairs:
        out.add(manual_pairs[token])
    return out


def _derive_aliases_from_canonical(normalized: str) -> set[str]:
    aliases = {normalized}
    tokens = normalized.split()
    for token in tokens:
        if token.endswith("ologia") and len(token) > 7:
            aliases.add(token[:-6] + "ologista")
        if token.endswith("iatria") and len(token) > 7:
            aliases.add(token[:-6] + "iatra")
        if token.endswith("opedia") and len(token) > 7:
            aliases.add(token[:-6] + "opedista")
    return aliases


def _query_prefers_pediatric(raw_value: str) -> bool:
    normalized = _normalize_text(raw_value)
    pediatric_signals = ("pediatr", "crianca", "infantil", "bebe", "adolesc")
    return any(signal in normalized for signal in pediatric_signals)


def _is_pediatric_specialty(canonical: str) -> bool:
    upper = canonical.upper()
    return "PEDIATR" in upper or "INFANT" in upper


def _pick_best_option(options: list[str] | tuple[str, ...], prefer_pediatric: bool) -> str:
    unique = list(dict.fromkeys(options))
    if not unique:
        return ""

    def score(value: str) -> tuple[int, int]:
        pediatric = _is_pediatric_specialty(value)
        pediatric_penalty = 0 if pediatric == prefer_pediatric else 1
        return (pediatric_penalty, len(value))

    return min(unique, key=score)


@lru_cache(maxsize=16)
def _load_catalog(path_str: str) -> SpecialtyCatalog:
    path = Path(path_str)
    if not path.is_file():
        return SpecialtyCatalog(by_normalized={}, by_alias={})

    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            return SpecialtyCatalog(by_normalized={}, by_alias={})
        first_column = reader.fieldnames[0]

        mapping: dict[str, str] = {}
        explicit_aliases: dict[str, set[str]] = {}
        for row in reader:
            raw_value = (row.get("BAQ_DESCRI") or row.get(first_column) or "").strip()
            if not raw_value:
                continue
            canonical = " ".join(raw_value.replace("\xa0", " ").split()).upper()
            normalized = _normalize_text(canonical)
            if not normalized:
                continue
            if normalized not in mapping:
                mapping[normalized] = canonical
            aliases_value = row.get("ALIASES") or row.get("aliases") or ""
            for alias in aliases_value.split("|"):
                normalized_alias = _normalize_text(alias)
                if normalized_alias:
                    explicit_aliases.setdefault(normalized_alias, set()).add(canonical)

    return _build_catalog(mapping, explicit_aliases)


def _build_catalog(
    mapping: dict[str, str],
    explicit_aliases: dict[str, set[str]] | None = None,
    *,
    passthrough_unknown: bool = False,
) -> SpecialtyCatalog:
    aliases_raw: dict[str, set[str]] = {key: {value} for key, value in mapping.items()}
    for normalized, canonical in mapping.items():
        for alias in _derive_aliases_from_canonical(normalized):
            aliases_raw.setdefault(alias, set()).add(canonical)
    for alias, values in (explicit_aliases or {}).items():
        aliases_raw.setdefault(alias, set()).update(values)

    aliases: dict[str, tuple[str, ...]] = {
        key: tuple(sorted(values, key=len)) for key, values in aliases_raw.items()
    }
    return SpecialtyCatalog(by_normalized=mapping, by_alias=aliases, passthrough_unknown=passthrough_unknown)


@lru_cache(maxsize=1)
def _load_default_catalog() -> SpecialtyCatalog:
    mapping: dict[str, str] = {}
    explicit_aliases: dict[str, set[str]] = {}
    for canonical, aliases in DEFAULT_SPECIALTY_ALIASES.items():
        normalized = _normalize_text(canonical)
        mapping[normalized] = canonical
        for alias in aliases:
            normalized_alias = _normalize_text(alias)
            if normalized_alias:
                explicit_aliases.setdefault(normalized_alias, set()).add(canonical)
    return _build_catalog(mapping, explicit_aliases, passthrough_unknown=True)


def _merge_catalogs(*catalogs: SpecialtyCatalog) -> SpecialtyCatalog:
    mapping: dict[str, str] = {}
    aliases: dict[str, set[str]] = {}
    for catalog in catalogs:
        mapping.update(catalog.by_normalized)
        for alias, values in catalog.by_alias.items():
            aliases.setdefault(alias, set()).update(values)
    return SpecialtyCatalog(
        by_normalized=mapping,
        by_alias={key: tuple(sorted(values, key=len)) for key, values in aliases.items()},
        passthrough_unknown=all(catalog.passthrough_unknown for catalog in catalogs),
    )


def get_specialty_catalog(settings: Settings) -> SpecialtyCatalog:
    default_catalog = _load_default_catalog()
    if not settings.specialties_csv_path:
        return default_catalog
    external_catalog = _load_catalog(settings.specialties_csv_path)
    if not external_catalog.is_enabled:
        return default_catalog
    return _merge_catalogs(default_catalog, external_catalog)
