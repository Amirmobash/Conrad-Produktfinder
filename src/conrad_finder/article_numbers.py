from __future__ import annotations

import re
from collections.abc import Iterable

ARTICLE_RE = re.compile(r"(?<!\d)(\d{5,8})(?!\d)")
LABELED_PATTERNS = (
    re.compile(r"Bestell(?:ungs)?[\s.\-]*Nr\.?\s*:?\s*(\d{5,8})", re.I),
    re.compile(r"Artikel[\s.\-]*Nr\.?\s*:?\s*(\d{5,8})", re.I),
    re.compile(r"Conrad\s*(?:Art(?:ikel)?\.?)?[\s.\-]*Nr\.?\s*:?\s*(\d{5,8})", re.I),
)


def normalize_article_number(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    # Excel wandelt reine Nummern gern in "1234567.0" um.
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]

    labeled = ARTICLE_RE.search(text.replace(" ", ""))
    if not labeled:
        return None

    number = labeled.group(1)
    return number if 5 <= len(number) <= 8 else None


def extract_article_numbers(text: str) -> list[str]:
    if not text:
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    def add_many(values: Iterable[str]) -> None:
        for value in values:
            number = normalize_article_number(value)
            if number and number not in seen:
                seen.add(number)
                ordered.append(number)

    for pattern in LABELED_PATTERNS:
        add_many(match.group(1) for match in pattern.finditer(text))

    # Unbeschriftete Nummern ergänzen, ohne bereits gefundene Duplikate.
    add_many(match.group(1) for match in ARTICLE_RE.finditer(text))
    return ordered
