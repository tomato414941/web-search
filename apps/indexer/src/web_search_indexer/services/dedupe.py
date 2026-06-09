"""Deduplication helpers for index jobs."""

import hashlib


def hash_text(value: str) -> str:
    """SHA-256 hex digest of a string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_dedupe_key(url: str, content_hash: str, outlinks_count: int = 0) -> str:
    """Build a deduplication key from URL, content hash, and indexed link count."""
    return hash_text(f"{url}\n{content_hash}\n{max(0, outlinks_count)}")
