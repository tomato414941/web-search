"""Web knowledge boundary for known URLs and observed links."""

from web_search_web_knowledge.links import LinkGraphRepository as LinkGraphRepository
from web_search_web_knowledge.urls import UrlLedgerRepository as UrlLedgerRepository

__all__ = [
    "LinkGraphRepository",
    "UrlLedgerRepository",
]
