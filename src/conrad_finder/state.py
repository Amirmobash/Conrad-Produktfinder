from __future__ import annotations

from dataclasses import dataclass, field

from .models import ImportRow, ProductCandidate, SearchOutcome


@dataclass
class AppState:
    rows: list[ImportRow] = field(default_factory=list)
    results: dict[int, SearchOutcome] = field(default_factory=dict)
    selected: dict[int, ProductCandidate] = field(default_factory=dict)

    def reset_search(self) -> None:
        self.results.clear()
        self.selected.clear()
