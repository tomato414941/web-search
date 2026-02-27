"""Test helpers: PostgreSQL testcontainer for integration tests."""

import atexit
import os

_container = None


def ensure_test_pg() -> None:
    """Start PG testcontainer if DATABASE_URL is not set (no-op if already running)."""
    global _container
    if os.getenv("DATABASE_URL") or _container is not None:
        return

    from testcontainers.postgres import PostgresContainer

    _container = PostgresContainer(
        "pgvector/pgvector:pg16",
        username="postgres",
        password="postgres",
        dbname="testdb",
    )
    _container.start()
    host = _container.get_container_host_ip()
    port = _container.get_exposed_port(5432)
    os.environ["DATABASE_URL"] = f"postgresql://postgres:postgres@{host}:{port}/testdb"
    atexit.register(lambda: _container.stop())
