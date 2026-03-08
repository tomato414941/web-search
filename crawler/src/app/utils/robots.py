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
MAX_FETCH_FAILURES = 3
# TTL for blocked domains (1 hour)
BLOCKED_DOMAIN_TTL = 3600


def _allow_all_parser() -> Protego:
    return Protego.parse("User-agent: *\nAllow: /")


def _disallow_all_parser() -> Protego:
    return Protego.parse("User-agent: *\nDisallow: /")


class AsyncRobotsCache:
    """Async wrapper for robots.txt parsing with LRU eviction"""

    def __init__(self, session: aiohttp.ClientSession, cache_size: int = 0):
        self._session = session
        effective_size = cache_size if cache_size > 0 else MAX_CACHED_DOMAINS
        self._parsers: LRUCache[str, Protego] = LRUCache(maxsize=effective_size)
        # TTL cache for blocked domains (expires after 1 hour)
        self._blocked_domains: TTLCache[str, bool] = TTLCache(
            maxsize=effective_size, ttl=BLOCKED_DOMAIN_TTL
        )
        self._fetch_failures: dict[str, int] = {}

    def _is_domain_blocked(self, domain: str) -> bool:
        """Check if domain is blocked due to repeated robots.txt failures."""
        return self._blocked_domains.get(domain, False)

    def _block_domain(self, domain: str) -> None:
        """Block a domain due to repeated robots.txt failures."""
        self._blocked_domains[domain] = True
        logger.warning(f"Domain blocked due to robots.txt failures: {domain}")

    async def can_fetch(self, url: str, user_agent: str) -> bool:
        """Check if URL can be fetched according to robots.txt"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if not domain:
                return False

            # Check if domain is blocked due to repeated failures
            if self._is_domain_blocked(domain):
                logger.debug(f"Domain blocked (robots.txt failures): {domain}")
                return False

            if domain not in self._parsers:
                parser = _allow_all_parser()

                scheme = parsed.scheme or "http"
                robots_url = f"{scheme}://{domain}/robots.txt"

                try:
                    from app.core.config import settings

                    async with self._session.get(
                        robots_url, timeout=settings.CRAWL_TIMEOUT_SEC
                    ) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            parser = Protego.parse(content)
                            # Reset failure count on success
                            self._fetch_failures.pop(domain, None)

                except Exception as e:
                    logger.warning(f"Robots fetch error for {domain}: {e}")
                    # Track failure count
                    self._fetch_failures[domain] = (
                        self._fetch_failures.get(domain, 0) + 1
                    )

                    if self._fetch_failures[domain] >= MAX_FETCH_FAILURES:
                        # Block domain after repeated failures
                        self._block_domain(domain)
                        parser = _disallow_all_parser()
                    else:
                        # Temporary skip, don't cache parser
                        logger.info(
                            f"Skipping {domain} (failure {self._fetch_failures[domain]}/{MAX_FETCH_FAILURES})"
                        )
                        return False

                self._parsers[domain] = parser

            return self._parsers[domain].can_fetch(url, user_agent)

        except Exception as e:
            logger.warning(f"Robots.txt check failed for {url}: {e}")
            return False  # Deny on unexpected errors for safety

    def get_crawl_delay(self, domain: str, user_agent: str) -> float | None:
        """Get Crawl-delay for a domain from cached robots.txt parser."""
        rp = self._parsers.get(domain)
        if rp is None:
            return None
        delay = rp.crawl_delay(user_agent)
        if delay is not None:
            return float(delay)
        return None
