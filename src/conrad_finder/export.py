from __future__ import annotations

import pandas as pd

from .models import ImportRow, ProductCandidate


def build_export(
    rows: list[ImportRow],
    selected: dict[int, ProductCandidate],
) -> pd.DataFrame:
    output: list[dict[str, object]] = []

    for index, item in enumerate(rows):
        candidate = selected.get(index)
        row = dict(item.original) if item.original else {}
        row.update(
            {
                "Menge": item.quantity,
                "Artikel-Nr.": item.article_number,
                "Beschreibung": item.description,
                "Conrad URL": candidate.url if candidate else "",
                "Bestell-Nr. Conrad": candidate.article_number if candidate else "",
                "Titel Conrad": candidate.title if candidate else "",
                "Preis Conrad": candidate.price or "" if candidate else "",
                "Status": "Gefunden" if candidate else "Nicht gefunden",
                "Quelle": candidate.source.value if candidate else "",
            }
        )
        output.append(row)

    return pd.DataFrame(output)


def dataframe_to_excel_friendly_csv(dataframe: pd.DataFrame) -> bytes:
    return dataframe.to_csv(index=False).encode("utf-8-sig")
