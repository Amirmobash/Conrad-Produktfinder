from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import aiohttp

from conrad_finder.config import AppConfig
from conrad_finder.models import ProductCandidate, SearchOutcome

from .base import deduplicate
from .conrad import ConradProvider, ProductDetailEnricher
from .web import BingProvider, DuckDuckGoProvider, SerperProvider


@dataclass(slots=True)
class _CacheEntry:
    created_at: float
    candidates: list[ProductCandidate]


class ProductSearchService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.conrad = ConradProvider(config)
        self.enricher = ProductDetailEnricher(config)
        self.fallbacks = {
            "duckduckgo": DuckDuckGoProvider(config),
            "serper": SerperProvider(config),
            "bing": BingProvider(config),
        }
        self._cache: dict[str, _CacheEntry] = {}

    async def search_one(self, article_number: str) -> SearchOutcome:
        cached = self._cache.get(article_number)
        if cached and time.time() - cached.created_at < self.config.cache_ttl_seconds:
            return SearchOutcome(article_number, list(cached.candidates))

        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                candidates = await self.conrad.search(session, article_number)

                if not candidates and self.config.fallback_enabled:
                    provider = self.fallbacks.get(
                        self.config.fallback_provider,
                        self.fallbacks["duckduckgo"],
                    )
                    candidates = await provider.search(session, article_number)

                candidates = deduplicate(candidates)[: self.config.max_results]

                enriched = []
                for candidate in candidates:
                    enriched.append(
                        await self.enricher.enrich(session, candidate, article_number)
                    )

                enriched.sort(key=lambda c: c.score, reverse=True)
                self._cache[article_number] = _CacheEntry(time.time(), list(enriched))
                return SearchOutcome(article_number, enriched)
        except Exception as exc:
            return SearchOutcome(article_number, [], error=str(exc))

    async def search_many(
        self,
        article_numbers: list[str],
        progress_callback=None,
    ) -> list[SearchOutcome]:
        outcomes: list[SearchOutcome] = []
        total = len(article_numbers)

        for index, article in enumerate(article_numbers, start=1):
            outcomes.append(await self.search_one(article))

            if progress_callback:
                progress_callback(index, total, article)

            if self.config.search_delay > 0 and index < total:
                await asyncio.sleep(self.config.search_delay)

        return outcomes


def run_coroutine(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
