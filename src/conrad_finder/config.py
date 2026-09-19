from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class AppConfig:
    tesseract_path: str = ""
    tessdata_path: str = ""
    poppler_path: str = ""
    ocr_language: str = "deu+eng"
    ocr_dpi: int = 300
    search_delay: float = 0.5
    max_results: int = 5
    fallback_enabled: bool = True
    fallback_provider: str = "duckduckgo"
    serper_api_key: str = ""
    bing_api_key: str = ""
    cache_ttl_seconds: int = 3600
    request_timeout_seconds: int = 15
    user_agent: str = "Mozilla/5.0 (compatible; ConradProductFinder/2.0)"

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            tesseract_path=os.getenv("TESSERACT_PATH", ""),
            tessdata_path=os.getenv("TESSDATA_PATH", ""),
            poppler_path=os.getenv("POPPLER_PATH", ""),
            search_delay=float(os.getenv("SEARCH_DELAY", "0.5")),
            max_results=int(os.getenv("MAX_RESULTS", "5")),
            fallback_enabled=_env_bool("ENABLE_FALLBACK", True),
            serper_api_key=os.getenv("SERPER_API_KEY", ""),
            bing_api_key=os.getenv("BING_API_KEY", ""),
            cache_ttl_seconds=int(os.getenv("CACHE_TTL", "3600")),
        )
