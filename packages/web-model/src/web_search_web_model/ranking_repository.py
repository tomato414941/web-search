"""Repository helpers for graph-derived ranking data."""

from collections.abc import Iterator

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
    def fetch_links() -> Iterator[tuple[str, str]]:
        from web_search_web_model.archive.snapshots import iter_latest
        from web_search_web_model.archive.store import ObjectStore

        for record in iter_latest(ObjectStore.from_env()):
            for dst in record.outlinks:
                yield record.src, dst

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
