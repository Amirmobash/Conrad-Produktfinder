from conrad_finder.models import ProductCandidate, ResultSource
from conrad_finder.search.base import deduplicate, is_conrad_product_url


def test_conrad_url_validation():
    assert is_conrad_product_url(
        "https://www.conrad.de/de/p/beispiel-produkt-1234567.html"
    )
    assert not is_conrad_product_url("https://example.com/de/p/foo.html")


def test_deduplicate_keeps_best_score():
    low = ProductCandidate(
        url="https://www.conrad.de/de/p/x-1234567.html",
        title="x",
        article_number="1234567",
        source=ResultSource.CONRAD,
        score=50,
    )
    high = ProductCandidate(
        url=low.url,
        title="x",
        article_number="1234567",
        source=ResultSource.CONRAD,
        score=90,
    )
    assert deduplicate([low, high])[0].score == 90
