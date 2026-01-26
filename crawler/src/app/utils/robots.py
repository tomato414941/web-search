"""
Robots.txt Handling

Async robots.txt parser with Redis caching and LRU eviction.
"""

import asyncio
import logging
import urllib.robotparser
from urllib.parse import urlparse
from typing import Dict

import aiohttp
from cachetools import LRUCache

logger = logging.getLogger(__name__)

# Maximum domains to cache in memory
MAX_CACHED_DOMAINS = 1000
MAX_FETCH_FAILURES = 3
BLOCKED_DOMAINS_KEY = "robots:blocked_domains"


class AsyncRobotsCache:
    """Async wrapper for robots.txt parsing with Redis persistence and LRU eviction"""

    def __init__(self, session: aiohttp.ClientSession, redis_client):
        self._session = session
        self._redis = redis_client
        self._parsers: LRUCache[str, urllib.robotparser.RobotFileParser] = LRUCache(
            maxsize=MAX_CACHED_DOMAINS
        )
        self._fetch_failures: Dict[str, int] = {}

    async def _is_domain_blocked(self, domain: str) -> bool:
        """Check if domain is blocked due to repeated robots.txt failures."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._redis.sismember(BLOCKED_DOMAINS_KEY, domain)
        )

    async def _block_domain(self, domain: str) -> None:
        """Block a domain due to repeated robots.txt failures."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: self._redis.sadd(BLOCKED_DOMAINS_KEY, domain)
        )
        logger.warning(f"🚫 Domain blocked due to robots.txt failures: {domain}")

    async def can_fetch(self, url: str, user_agent: str) -> bool:
        """Check if URL can be fetched according to robots.txt"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if not domain:
                return False

            # Check if domain is blocked due to repeated failures
            if await self._is_domain_blocked(domain):
                logger.debug(f"Domain blocked (robots.txt failures): {domain}")
                return False

            if domain not in self._parsers:
                rp = urllib.robotparser.RobotFileParser()
                redis_key = f"robots:{domain}"
                loop = asyncio.get_running_loop()
                cached_content = await loop.run_in_executor(
                    None, self._redis.get, redis_key
                )

                if cached_content:
                    if isinstance(cached_content, bytes):
                        cached_content = cached_content.decode("utf-8", errors="ignore")
                    rp.parse(cached_content.splitlines())
                    # Reset failure count on successful cache hit
                    self._fetch_failures.pop(domain, None)
                else:
                    scheme = parsed.scheme or "http"
                    robots_url = f"{scheme}://{domain}/robots.txt"

                    try:
                        from app.core.config import settings

                        async with self._session.get(
                            robots_url, timeout=settings.CRAWL_TIMEOUT_SEC
                        ) as resp:
                            if resp.status == 200:
                                content = await resp.text()
                                rp.parse(content.splitlines())
                                await loop.run_in_executor(
                                    None,
                                    lambda: self._redis.setex(
                                        redis_key, 86400, content
                                    ),
                                )
                                # Reset failure count on success
                                self._fetch_failures.pop(domain, None)
                            else:
                                rp.allow_all = True
                                allow_all_txt = "User-agent: *\nDisallow:"
                                await loop.run_in_executor(
                                    None,
                                    lambda: self._redis.setex(
                                        redis_key, 86400, allow_all_txt
                                    ),
                                )

                    except Exception as e:
                        logger.warning(f"Robots fetch error for {domain}: {e}")
                        # Track failure count
                        self._fetch_failures[domain] = (
                            self._fetch_failures.get(domain, 0) + 1
                        )

                        if self._fetch_failures[domain] >= MAX_FETCH_FAILURES:
                            # Block domain after repeated failures
                            await self._block_domain(domain)
                            # Create a disallow-all parser
                            rp.disallow_all = True
                        else:
                            # Temporary allow, but skip this domain for now
                            logger.info(
                                f"Skipping {domain} (failure {self._fetch_failures[domain]}/{MAX_FETCH_FAILURES})"
                            )
                            return False  # Skip URL, don't cache parser

                self._parsers[domain] = rp

            return self._parsers[domain].can_fetch(user_agent, url)

        except Exception as e:
            logger.warning(f"Robots.txt check failed for {url}: {e}")
            return False  # Deny on unexpected errors for safety
