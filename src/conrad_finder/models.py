from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ResultSource(StrEnum):
    CONRAD = "conrad"
    DUCKDUCKGO = "duckduckgo"
    SERPER = "serper"
    BING = "bing"


@dataclass(slots=True)
class ProductCandidate:
    url: str
    title: str
    article_number: str
    price: str | None = None
    source: ResultSource = ResultSource.CONRAD
    score: int = 0

    def display_label(self) -> str:
        price = self.price or "Preis unbekannt"
        return f"{self.title} · {self.article_number or 'ohne Nr.'} · {price}"


@dataclass(slots=True)
class ImportRow:
    quantity: int = 1
    article_number: str = ""
    description: str = ""
    original: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchOutcome:
    article_number: str
    candidates: list[ProductCandidate]
    error: str | None = None
