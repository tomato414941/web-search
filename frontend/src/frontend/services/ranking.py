from frontend.core.config import settings
from shared.pagerank import calculate_pagerank


class RankingService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path

    def calculate_pagerank(self, iterations: int = 20, damping: float = 0.85) -> None:
        calculate_pagerank(self.db_path, iterations, damping)


# Global instance
ranking_service = RankingService()
