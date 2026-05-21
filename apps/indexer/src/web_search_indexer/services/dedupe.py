"""Deduplication helpers for index jobs."""

import hashlib


def hash_text(value: str) -> str:
    """SHA-256 hex digest of a string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_dedupe_key(url: str, content_hash: str, outlinks_hash: str = "") -> str:
    """Build a deduplication key from URL and content/outlinks hashes."""
    return hash_text(f"{url}\n{content_hash}\n{outlinks_hash}")
