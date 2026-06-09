"""Repository helpers for graph-derived ranking data."""

from web_search_postgres.search import open_db, sql_placeholder

_SAVE_BATCH_SIZE = 5000


class RankingRepository:
    """Data-access helpers for graph-derived ranking calculations."""

    @staticmethod
    def fetch_document_urls() -> set[str]:
        con = open_db()
        try:
            cur = con.cursor()
            cur.execute("SELECT url FROM documents")
            nodes = {str(url) for (url,) in cur}
            cur.close()
            return nodes
        finally:
            con.close()

    @staticmethod
    def fetch_links() -> list[tuple[str, str]]:
        con = open_db()
        try:
            cur = con.cursor()
            cur.execute("SELECT src, dst FROM links")
            rows = [(str(src), str(dst)) for src, dst in cur]
            cur.close()
            return rows
        finally:
            con.close()

    @staticmethod
    def replace_page_ranks(scores: dict[str, float]) -> None:
        RankingRepository._replace_scores(
            table="page_ranks",
            key_column="url",
            scores=scores,
        )

    @staticmethod
    def replace_domain_ranks(scores: dict[str, float]) -> None:
        RankingRepository._replace_scores(
            table="domain_ranks",
            key_column="domain",
            scores=scores,
        )

    @staticmethod
    def _replace_scores(
        *, table: str, key_column: str, scores: dict[str, float]
    ) -> None:
        if not scores:
            return
        max_score = max(scores.values())
        normalized = scores
        if max_score > 0:
            normalized = {key: score / max_score for key, score in scores.items()}

        ph = sql_placeholder()
        con = open_db()
        try:
            cur = con.cursor()
            cur.execute(f"DELETE FROM {table}")
            items = list(normalized.items())
            for index in range(0, len(items), _SAVE_BATCH_SIZE):
                batch = items[index : index + _SAVE_BATCH_SIZE]
                cur.executemany(
                    f"INSERT INTO {table} ({key_column}, score) VALUES ({ph}, {ph})",
                    batch,
                )
            con.commit()
            cur.close()
        finally:
            con.close()
