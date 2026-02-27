"""Unified retry policy for all services."""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Configurable retry policy with exponential backoff and jitter."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.25
    retryable_exceptions: tuple[type[Exception], ...] = field(
        default=(Exception,),
    )

    def compute_delay(self, attempt: int) -> float:
        """Compute delay for a given attempt (0-indexed)."""
        delay = min(self.base_delay * (2**attempt), self.max_delay)
        jitter_range = delay * self.jitter
        return delay + random.uniform(-jitter_range, jitter_range)

    def execute(self, fn: Callable[[], T], label: str = "operation") -> T:
        """Execute fn with retries according to policy."""
        last_exc: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return fn()
            except self.retryable_exceptions as exc:
                last_exc = exc
                if attempt + 1 >= self.max_attempts:
                    break
                delay = self.compute_delay(attempt)
                logger.warning(
                    "%s attempt %d/%d failed: %s (retry in %.1fs)",
                    label,
                    attempt + 1,
                    self.max_attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
        raise last_exc  # type: ignore[misc]
