from conrad_finder.article_numbers import extract_article_numbers, normalize_article_number


def test_normalize_regular_number():
    assert normalize_article_number("1234567") == "1234567"


def test_normalize_excel_float():
    assert normalize_article_number("1234567.0") == "1234567"


def test_reject_short_number():
    assert normalize_article_number("1234") is None


def test_extract_keeps_order_and_removes_duplicates():
    text = "Bestell-Nr. 1234567, Artikel-Nr. 7654321, nochmal 1234567"
    assert extract_article_numbers(text) == ["1234567", "7654321"]
