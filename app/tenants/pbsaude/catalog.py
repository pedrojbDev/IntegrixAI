from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path

from ...config import Settings

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
        candidate_keys = self._candidate_keys(raw_value)
        if not candidate_keys:
            return None

        prefer_pediatric = _query_prefers_pediatric(raw_value)
        for candidate in candidate_keys:
            options = self.by_alias.get(candidate)
            if options:
                return _pick_best_option(options, prefer_pediatric)

        for candidate in candidate_keys:
            starts_with = [opt for key, values in self.by_alias.items() if key.startswith(candidate) for opt in values]
            if starts_with:
                return _pick_best_option(starts_with, prefer_pediatric)

        fuzzy_keys = get_close_matches(candidate_keys[0], self.by_alias.keys(), n=1, cutoff=0.86)
        if fuzzy_keys:
            options = self.by_alias[fuzzy_keys[0]]
            return _pick_best_option(options, prefer_pediatric)

        return None

    def suggest(self, raw_value: str, limit: int = 3) -> list[str]:
        candidate_keys = self._candidate_keys(raw_value)
        if not candidate_keys:
            return []

        fuzzy_keys = get_close_matches(candidate_keys[0], self.by_alias.keys(), n=limit * 2, cutoff=0.7)
        out: list[str] = []
        for key in fuzzy_keys:
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
    if not path.exists():
        return SpecialtyCatalog(by_normalized={}, by_alias={})

    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            return SpecialtyCatalog(by_normalized={}, by_alias={})
        first_column = reader.fieldnames[0]

        mapping: dict[str, str] = {}
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

    aliases_raw: dict[str, set[str]] = {key: {value} for key, value in mapping.items()}
    for normalized, canonical in mapping.items():
        for alias in _derive_aliases_from_canonical(normalized):
            aliases_raw.setdefault(alias, set()).add(canonical)

    aliases: dict[str, tuple[str, ...]] = {
        key: tuple(sorted(values, key=len)) for key, values in aliases_raw.items()
    }
    return SpecialtyCatalog(by_normalized=mapping, by_alias=aliases)


def get_specialty_catalog(settings: Settings) -> SpecialtyCatalog:
    if not settings.specialties_csv_path:
        return SpecialtyCatalog(by_normalized={}, by_alias={})
    return _load_catalog(settings.specialties_csv_path)
