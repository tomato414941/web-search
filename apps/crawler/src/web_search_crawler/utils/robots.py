"""
Robots.txt Handling

Async robots.txt parser with in-memory LRU caching.
"""

import logging
from urllib.parse import urlparse

import aiohttp
from cachetools import LRUCache, TTLCache
from protego import Protego

logger = logging.getLogger(__name__)

# Maximum domains to cache in memory
MAX_CACHED_DOMAINS = 1000
# TTL for temporary allow after robots transport failure (5 minutes)
TEMPORARY_ALLOW_TTL = 300


def _allow_all_parser() -> Protego:
    return Protego.parse("User-agent: *\nAllow: /")


class AsyncRobotsCache:
    """Async wrapper for robots.txt parsing with LRU eviction."""

    def __init__(self, session: aiohttp.ClientSession, cache_size: int = 0):
        self._session = session
        effective_size = cache_size if cache_size > 0 else MAX_CACHED_DOMAINS
        self._parsers: LRUCache[str, Protego] = LRUCache(maxsize=effective_size)
        self._temporary_allow_domains: TTLCache[str, bool] = TTLCache(
            maxsize=effective_size, ttl=TEMPORARY_ALLOW_TTL
        )

    async def can_fetch(self, url: str, user_agent: str) -> bool:
        """Check if URL can be fetched according to robots.txt."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if not domain:
                return False

            if domain in self._temporary_allow_domains:
                return True

            if domain not in self._parsers:
                parser = _allow_all_parser()
                scheme = parsed.scheme or "http"
                robots_url = f"{scheme}://{domain}/robots.txt"

                try:
                    from web_search_crawler.core.config import settings

                    async with self._session.get(
                        robots_url, timeout=settings.CRAWL_TIMEOUT_SEC
                    ) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            parser = Protego.parse(content)
                        self._parsers[domain] = parser
                except Exception as exc:
                    logger.warning("Robots fetch error for %s: %s", domain, exc)
                    self._temporary_allow_domains[domain] = True
                    return True

            return self._parsers[domain].can_fetch(url, user_agent)

        except Exception as exc:
            logger.warning("Robots.txt check failed for %s: %s", url, exc)
            return False  # Deny on unexpected parsing errors for safety

    def get_crawl_delay(self, domain: str, user_agent: str) -> float | None:
        """Get Crawl-delay for a domain from cached robots.txt parser."""
        rp = self._parsers.get(domain)
        if rp is None:
            return None
        delay = rp.crawl_delay(user_agent)
        if delay is not None:
            return float(delay)
        return None
