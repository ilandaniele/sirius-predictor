from __future__ import annotations

import re
import unicodedata

TEAM_ALIASES = {
    "ir iran": "Iran",
    "korea republic": "Corea del Sur",
    "republic of korea": "Corea del Sur",
    "usa": "Estados Unidos",
    "united states": "Estados Unidos",
}


def comparison_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def normalize_name(value: str, aliases: dict[str, str] | None = None) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip(" \t\r\n,.;")
    mapping = aliases if aliases is not None else TEAM_ALIASES
    return mapping.get(comparison_key(cleaned), cleaned)
