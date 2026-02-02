"""
Crawler Database Layer

Provides Frontier (pending URLs) and History (visited URLs) storage.
"""

from app.db.frontier import Frontier
from app.db.history import History

__all__ = ["Frontier", "History"]
