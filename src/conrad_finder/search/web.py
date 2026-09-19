from __future__ import annotations

from urllib.parse import parse_qs, quote, unquote, urlparse

import aiohttp
from bs4 import BeautifulSoup

from conrad_finder.models import ProductCandidate, ResultSource

from .base import SearchProvider, is_conrad_product_url


def _duckduckgo_target(href: str) -> str:
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        if query.get("uddg"):
            return unquote(query["uddg"][0])
    return href


class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    async def search(self, session, article_number):
        query = quote(f"site:conrad.de/de/p/ {article_number}")
        url = f"https://html.duckduckgo.com/html/?q={query}"

        try:
            async with session.get(
                url,
                headers={"User-Agent": self.config.user_agent},
            ) as response:
                if response.status != 200:
                    return []
                html = await response.text()
        except (aiohttp.ClientError, TimeoutError):
            return []

        soup = BeautifulSoup(html, "lxml")
        out: list[ProductCandidate] = []
        seen: set[str] = set()

        for link in soup.select("a.result__a, a[href]"):
            href = _duckduckgo_target(str(link.get("href", "")))
            if not is_conrad_product_url(href) or href in seen:
                continue
            seen.add(href)
            out.append(
                ProductCandidate(
                    url=href,
                    title=link.get_text(" ", strip=True) or "Conrad Produkt",
                    article_number=article_number,
                    source=ResultSource.DUCKDUCKGO,
                    score=70,
                )
            )
        return out


class SerperProvider(SearchProvider):
    name = "serper"

    async def search(self, session, article_number):
        if not self.config.serper_api_key:
            return []

        try:
            async with session.post(
                "https://google.serper.dev/search",
                headers={
                    "X-API-KEY": self.config.serper_api_key,
                    "Content-Type": "application/json",
                },
                json={"q": f"site:conrad.de/de/p/ {article_number}", "num": self.config.max_results},
            ) as response:
                if response.status != 200:
                    return []
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError):
            return []

        out = []
        for item in payload.get("organic", []):
            url = str(item.get("link", ""))
            if is_conrad_product_url(url):
                out.append(
                    ProductCandidate(
                        url=url,
                        title=str(item.get("title") or "Conrad Produkt"),
                        article_number=article_number,
                        source=ResultSource.SERPER,
                        score=80,
                    )
                )
        return out


class BingProvider(SearchProvider):
    name = "bing"

    async def search(self, session, article_number):
        if not self.config.bing_api_key:
            return []

        params = {
            "q": f"site:conrad.de/de/p/ {article_number}",
            "count": self.config.max_results,
            "responseFilter": "Webpages",
        }
        try:
            async with session.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers={"Ocp-Apim-Subscription-Key": self.config.bing_api_key},
                params=params,
            ) as response:
                if response.status != 200:
                    return []
                payload = await response.json()
        except (aiohttp.ClientError, TimeoutError):
            return []

        out = []
        for item in payload.get("webPages", {}).get("value", []):
            url = str(item.get("url", ""))
            if is_conrad_product_url(url):
                out.append(
                    ProductCandidate(
                        url=url,
                        title=str(item.get("name") or "Conrad Produkt"),
                        article_number=article_number,
                        source=ResultSource.BING,
                        score=80,
                    )
                )
        return out
