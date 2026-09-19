from __future__ import annotations

import io

import pandas as pd

from .article_numbers import normalize_article_number
from .models import ImportRow


def read_csv(data: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"CSV konnte nicht gelesen werden: {last_error}")


def dataframe_to_rows(
    dataframe: pd.DataFrame,
    article_column: str,
    quantity_column: str | None = None,
    description_column: str | None = None,
) -> list[ImportRow]:
    rows: list[ImportRow] = []

    for _, row in dataframe.iterrows():
        article_number = normalize_article_number(row.get(article_column))
        if not article_number:
            continue

        quantity = 1
        if quantity_column:
            try:
                quantity = max(1, int(float(row.get(quantity_column, 1))))
            except (TypeError, ValueError):
                quantity = 1

        description = ""
        if description_column:
            raw = row.get(description_column, "")
            description = "" if pd.isna(raw) else str(raw).strip()

        rows.append(
            ImportRow(
                quantity=quantity,
                article_number=article_number,
                description=description,
                original=row.to_dict(),
            )
        )

    return rows
