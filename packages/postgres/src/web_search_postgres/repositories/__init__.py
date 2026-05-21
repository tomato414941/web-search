"""Repository classes for PostgreSQL data access."""

from web_search_postgres.repositories.document_repo import (
    DocumentRepository as DocumentRepository,
)
from web_search_postgres.repositories.index_job_repo import (
    IndexJobRepository as IndexJobRepository,
)
from web_search_postgres.repositories.ranking_repo import (
    RankingRepository as RankingRepository,
)
