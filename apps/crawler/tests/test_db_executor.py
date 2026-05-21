import os
import subprocess
import sys


def _read_executor_max(
    *,
    db_pool_max: str,
    db_executor_max: str | None = None,
) -> str:
    env = os.environ.copy()
    env["DB_POOL_MAX"] = db_pool_max
    if db_executor_max is None:
        env.pop("DB_EXECUTOR_MAX", None)
    else:
        env["DB_EXECUTOR_MAX"] = db_executor_max
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from web_search_crawler.db.executor import "
                "_DB_EXECUTOR_MAX, _db_executor, shutdown_db_executor; "
                "print(f'{_DB_EXECUTOR_MAX}:{_db_executor._max_workers}'); "
                "shutdown_db_executor()"
            ),
        ],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_db_executor_defaults_leave_pool_headroom():
    assert _read_executor_max(db_pool_max="10") == "8:8"


def test_db_executor_keeps_at_least_one_worker():
    assert _read_executor_max(db_pool_max="1") == "1:1"


def test_db_executor_override_is_capped_by_pool():
    assert _read_executor_max(db_pool_max="4", db_executor_max="99") == "4:4"
