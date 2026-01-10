import sqlite3
from typing import Dict, Set

from shared.db.sqlite import open_db
from frontend.core.config import settings


class RankingService:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path

    def calculate_pagerank(self, iterations: int = 20, damping: float = 0.85) -> None:
        """
        Calculate PageRank using Power Iteration and update the DB.
        """
        print(f"Calculating PageRank (iter={iterations}, d={damping})...")

        con = open_db(self.db_path)
        try:
            # 1. Load Graph
            nodes: Set[str] = set()
            cur_nodes = con.execute("SELECT url FROM pages")
            for row in cur_nodes:
                nodes.add(row[0])

            # Map URL -> List of Outbound URLs
            out_links: Dict[str, list] = {u: [] for u in nodes}
            # Map URL -> List of Inbound URLs
            in_links: Dict[str, list] = {u: [] for u in nodes}

            # Load edges
            # Ideally we only load relevant edges
            cur_links = con.execute("SELECT src, dst FROM links")
            for src, dst in cur_links:
                if src in nodes and dst in nodes:
                    out_links[src].append(dst)
                    in_links[dst].append(src)

            N = len(nodes)
            if N == 0:
                print("No pages found.")
                return

            # 2. Initialize Scores
            scores = {u: 1.0 / N for u in nodes}

            # 3. Power Iteration
            for i in range(iterations):
                new_scores = {}
                diff = 0.0

                for u in nodes:
                    incoming_score = 0.0
                    for v in in_links[u]:
                        out_degree = len(out_links[v])
                        if out_degree > 0:
                            incoming_score += scores[v] / out_degree

                    # PR formula
                    pr = (1 - damping) / N + damping * incoming_score
                    new_scores[u] = pr

                # Convergence check
                for u in nodes:
                    diff += abs(new_scores[u] - scores[u])
                scores = new_scores

                print(f"  Iter {i + 1}: diff={diff:.6f}")
                if diff < 1e-6:
                    print(f"Converged at iteration {i + 1}.")
                    break

            # 4. Save
            self._save_scores(con, scores)
            print("PageRank calculation complete. Updated DB.")

        finally:
            con.close()

    def _save_scores(self, con: sqlite3.Connection, scores: Dict[str, float]) -> None:
        con.execute("DELETE FROM page_ranks")
        con.executemany(
            "INSERT INTO page_ranks (url, score) VALUES (?, ?)", list(scores.items())
        )
        con.commit()


# Global instance
ranking_service = RankingService()
