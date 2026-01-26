"""
Robots.txt Handling

Async robots.txt parser with Redis caching.
"""

import asyncio
import logging
import urllib.robotparser
from urllib.parse import urlparse
from typing import Dict, Set

import aiohttp

logger = logging.getLogger(__name__)


class AsyncRobotsCache:
    """Async wrapper for robots.txt parsing with Redis persistence"""

    def __init__(self, session: aiohttp.ClientSession, redis_client):
        self._session = session
        self._redis = redis_client
        self._parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._checked_domains: Set[str] = set()

    async def can_fetch(self, url: str, user_agent: str) -> bool:
        """Check if URL can be fetched according to robots.txt"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if not domain:
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
                        rp.allow_all = True

                self._parsers[domain] = rp

            return self._parsers[domain].can_fetch(user_agent, url)

        except Exception as e:
            logger.warning(f"Robots.txt check failed for {url}: {e}")
            return True
