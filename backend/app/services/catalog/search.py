from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(_WORD_RE.findall(without_accents.casefold()))


def relevance_score(query: str, *, name: str, description: str | None, category: str | None) -> float:
    normalized_query = normalize_text(query)
    normalized_name = normalize_text(name)
    normalized_description = normalize_text(description)
    normalized_category = normalize_text(category)

    if not normalized_query:
        return 0.0
    if normalized_query == normalized_name:
        return 1.0
    if normalized_name.startswith(normalized_query):
        return 0.95
    if normalized_query in normalized_name:
        return 0.90

    query_tokens = set(normalized_query.split())
    name_tokens = set(normalized_name.split())
    description_tokens = set(normalized_description.split())
    category_tokens = set(normalized_category.split())

    name_overlap = len(query_tokens & name_tokens) / max(len(query_tokens), 1)
    description_overlap = len(query_tokens & description_tokens) / max(len(query_tokens), 1)
    category_overlap = len(query_tokens & category_tokens) / max(len(query_tokens), 1)
    sequence = SequenceMatcher(None, normalized_query, normalized_name).ratio()

    return round(
        min(
            0.89,
            (name_overlap * 0.60)
            + (description_overlap * 0.15)
            + (category_overlap * 0.10)
            + (sequence * 0.15),
        ),
        4,
    )
