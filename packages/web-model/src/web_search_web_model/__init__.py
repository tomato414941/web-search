"""Web model boundary for known URLs and observed links."""

from web_search_web_model.links import LinkGraphRepository as LinkGraphRepository
from web_search_web_model.urls import UrlLedgerRepository as UrlLedgerRepository

__all__ = [
    "LinkGraphRepository",
    "UrlLedgerRepository",
]
