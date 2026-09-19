from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from urllib.parse import urlparse

import aiohttp

from conrad_finder.config import AppConfig
from conrad_finder.models import ProductCandidate


def is_conrad_product_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    host = parsed.netloc.lower().split(":")[0]
    return host in {"conrad.de", "www.conrad.de"} and "/de/p/" in parsed.path


class SearchProvider(ABC):
    name: str

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @abstractmethod
    async def search(
        self,
        session: aiohttp.ClientSession,
        article_number: str,
    ) -> list[ProductCandidate]:
        raise NotImplementedError


def deduplicate(candidates: Iterable[ProductCandidate]) -> list[ProductCandidate]:
    by_url: dict[str, ProductCandidate] = {}
    for candidate in candidates:
        current = by_url.get(candidate.url)
        if current is None or candidate.score > current.score:
            by_url[candidate.url] = candidate
    return list(by_url.values())
