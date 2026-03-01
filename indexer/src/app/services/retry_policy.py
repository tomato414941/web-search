"""Retry policy for index jobs."""


class RetryPolicy:
    """Encapsulates retry delay calculation and exhaustion check."""

    def __init__(
        self,
        max_retries: int = 5,
        base_seconds: int = 5,
        max_seconds: int = 1800,
    ):
        self.max_retries = max_retries
        self.base_seconds = base_seconds
        self.max_seconds = max_seconds

    def delay_seconds(self, retry_count: int) -> int:
        """Compute delay for the given retry attempt (1-indexed)."""
        raw = self.base_seconds * (2 ** (retry_count - 1))
        return min(raw, self.max_seconds)

    def is_exhausted(self, retry_count: int) -> bool:
        """Return True when retry_count has reached the limit."""
        return retry_count >= self.max_retries
