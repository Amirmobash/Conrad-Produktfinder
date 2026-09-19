from __future__ import annotations

import json
import re
from urllib.parse import quote, urljoin

import aiohttp
from bs4 import BeautifulSoup

from conrad_finder.article_numbers import normalize_article_number
from conrad_finder.models import ProductCandidate, ResultSource

from .base import SearchProvider, is_conrad_product_url

PRODUCT_PATH_RE = re.compile(r"/de/p/[^\"'?#]+-\d+\.html", re.I)


async def _fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
) -> str | None:
    try:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return None
            return await response.text()
    except (aiohttp.ClientError, TimeoutError):
        return None


class ConradProvider(SearchProvider):
    name = "conrad"

    async def search(
        self,
        session: aiohttp.ClientSession,
        article_number: str,
    ) -> list[ProductCandidate]:
        url = f"https://www.conrad.de/de/search.html?search={quote(article_number)}"
        html = await _fetch_text(
            session,
            url,
            headers={"User-Agent": self.config.user_agent},
        )
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        candidates: list[ProductCandidate] = []
        seen: set[str] = set()

        for link in soup.find_all("a", href=True):
            href = str(link.get("href", ""))
            if not PRODUCT_PATH_RE.search(href):
                continue

            product_url = urljoin("https://www.conrad.de", href)
            if not is_conrad_product_url(product_url) or product_url in seen:
                continue

            seen.add(product_url)
            title = link.get_text(" ", strip=True) or "Conrad Produkt"
            candidates.append(
                ProductCandidate(
                    url=product_url,
                    title=title,
                    article_number=article_number,
                    source=ResultSource.CONRAD,
                    score=85,
                )
            )

        return candidates


class ProductDetailEnricher:
    def __init__(self, config) -> None:
        self.config = config

    async def enrich(
        self,
        session: aiohttp.ClientSession,
        candidate: ProductCandidate,
        wanted_article: str,
    ) -> ProductCandidate:
        html = await _fetch_text(
            session,
            candidate.url,
            headers={"User-Agent": self.config.user_agent},
        )
        if not html:
            return candidate

        soup = BeautifulSoup(html, "lxml")
        title = candidate.title
        price = candidate.price
        article = candidate.article_number

        # JSON-LD ist stabiler als rein visuelle CSS-Klassen.
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text()
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if node.get("@type") == "Product":
                    title = str(node.get("name") or title)
                    sku = node.get("sku") or node.get("productID")
                    if sku:
                        article = str(sku)
                    offers = node.get("offers")
                    if isinstance(offers, dict) and offers.get("price"):
                        currency = offers.get("priceCurrency", "EUR")
                        price = f"{offers['price']} {currency}"

        if title == candidate.title:
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(" ", strip=True) or title

        page_text = soup.get_text(" ", strip=True)
        if not normalize_article_number(article):
            match = re.search(
                r"(?:Bestell|Artikel)[\s\-]*Nr\.?\s*:?\s*([0-9]{5,8})",
                page_text,
                re.I,
            )
            if match:
                article = match.group(1)

        normalized = normalize_article_number(article)
        score = candidate.score
        if normalized == wanted_article:
            score = 100
        elif wanted_article in page_text:
            score = max(score, 95)

        return ProductCandidate(
            url=candidate.url,
            title=title,
            article_number=normalized or article,
            price=price,
            source=candidate.source,
            score=score,
        )
