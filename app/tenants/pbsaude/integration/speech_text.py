from __future__ import annotations

import re
import unicodedata


# The provider directory currently returns presentation text without diacritics.
# Keep these corrections tenant-specific and deterministic: guessing accents in
# arbitrary proper names would be unsafe and could change a provider identity.
PBSAUDE_SPEECH_ACCENT_OVERRIDES = {
    "antonio": "antônio",
    "clinica": "clínica",
    "clinicas": "clínicas",
    "clinico": "clínico",
    "clinicos": "clínicos",
    "diagnostico": "diagnóstico",
    "diagnosticos": "diagnósticos",
    "edificio": "edifício",
    "hortensia": "hortênsia",
    "hortensias": "hortênsias",
    "joao": "joão",
    "jose": "josé",
    "laboratorio": "laboratório",
    "laboratorios": "laboratórios",
    "magalhaes": "magalhães",
    "medica": "médica",
    "medicas": "médicas",
    "medico": "médico",
    "medicos": "médicos",
    "numero": "número",
    "praca": "praça",
    "saude": "saúde",
    "sao": "são",
    "terreo": "térreo",
}

PBSAUDE_ADDRESS_TYPE_OVERRIDES = {
    ("salvador", "pituba", "das hortensias"): "Rua",
    ("salvador", "pituba", "professor magalhaes neto"): "Avenida",
}

_ADDRESS_TYPE_ALIASES = {
    "al": "Alameda",
    "alameda": "Alameda",
    "av": "Avenida",
    "avenida": "Avenida",
    "estr": "Estrada",
    "estrada": "Estrada",
    "lg": "Largo",
    "largo": "Largo",
    "pc": "Praça",
    "pca": "Praça",
    "praca": "Praça",
    "praça": "Praça",
    "r": "Rua",
    "rod": "Rodovia",
    "rodovia": "Rodovia",
    "rua": "Rua",
    "travessa": "Travessa",
    "tv": "Travessa",
}

_ACCENT_PATTERN = re.compile(
    r"(?<!\w)(" + "|".join(
        sorted((re.escape(key) for key in PBSAUDE_SPEECH_ACCENT_OVERRIDES), key=len, reverse=True)
    ) + r")(?!\w)",
    flags=re.IGNORECASE,
)

_ADDRESS_PREFIX_PATTERN = re.compile(
    r"^(?P<prefix>"
    + "|".join(
        sorted((re.escape(key) for key in _ADDRESS_TYPE_ALIASES), key=len, reverse=True)
    )
    + r")\.?\s+",
    flags=re.IGNORECASE,
)


def normalize_provider_speech_text(value: str) -> str:
    """Return NFC presentation text with controlled PB Saude accents."""
    normalized = unicodedata.normalize("NFC", value)
    return _ACCENT_PATTERN.sub(_accent_match, normalized)


def normalize_provider_address(
    value: str,
    *,
    street_type: str | None = None,
    city: str | None = None,
    neighborhood: str | None = None,
) -> str:
    """Normalize an address without guessing an unknown street type."""
    normalized = normalize_provider_speech_text(value)
    prefix_match = _ADDRESS_PREFIX_PATTERN.match(normalized)
    if prefix_match:
        prefix = _canonical_address_type(prefix_match.group("prefix"))
        return f"{prefix} {normalized[prefix_match.end():].lstrip()}"

    explicit_type = _canonical_address_type(street_type)
    if explicit_type:
        return f"{explicit_type} {normalized}"

    known_type = PBSAUDE_ADDRESS_TYPE_OVERRIDES.get(
        (
            _address_lookup_key(city or ""),
            _address_lookup_key(neighborhood or ""),
            _address_lookup_key(normalized),
        )
    )
    if known_type:
        return f"{known_type} {normalized}"
    return normalized


def _accent_match(match: re.Match[str]) -> str:
    source = match.group(0)
    replacement = PBSAUDE_SPEECH_ACCENT_OVERRIDES[source.lower()]
    if source.isupper():
        return replacement.upper()
    if source.islower():
        return replacement
    if source.istitle():
        return replacement.title()
    return replacement


def _canonical_address_type(value: str | None) -> str | None:
    if not value:
        return None
    key = _address_lookup_key(value)
    return _ADDRESS_TYPE_ALIASES.get(key)


def _address_lookup_key(value: str) -> str:
    street_name = value.split(",", 1)[0]
    decomposed = unicodedata.normalize("NFKD", street_name)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).split())
