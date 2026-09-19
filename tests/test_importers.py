import pandas as pd

from conrad_finder.importers import dataframe_to_rows


def test_dataframe_mapping():
    df = pd.DataFrame(
        [
            {"qty": 2, "art": "1234567", "desc": "Kabel"},
            {"qty": 1, "art": "ungueltig", "desc": "Fehler"},
        ]
    )

    rows = dataframe_to_rows(df, "art", "qty", "desc")
    assert len(rows) == 1
    assert rows[0].quantity == 2
    assert rows[0].article_number == "1234567"
    assert rows[0].description == "Kabel"
