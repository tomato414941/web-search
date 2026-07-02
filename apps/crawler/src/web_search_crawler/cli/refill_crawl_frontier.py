#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from typing import Sequence


ENVIRONMENTS = ("prd",)
DEFAULT_PROJECT = "web-search-prd"


def _run(
    command: Sequence[str], *, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _resolve_crawler_container(server: str, project_name: str) -> str:
    result = _run(
        [
            "ssh",
            server,
            (
                "docker ps -aq "
                f"--filter 'label=com.docker.compose.project={project_name}' "
                "--filter 'label=com.docker.compose.service=crawler' | head -n1"
            ),
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"Failed to resolve crawler container for {project_name}: {stderr or 'not found'}"
        )
    return result.stdout.strip()


def _build_remote_script(payload: dict[str, object]) -> str:
    payload_literal = json.dumps(payload, ensure_ascii=True)
    return f"""
import json

from web_search_crawler.core.config import settings
from web_search_crawler.db.crawler_runtime_store import CrawlerRuntimeStore
from web_search_crawler.services.crawl_frontier_refill import (
    refill_crawl_frontier_from_links,
)
from web_search_core.url_admission import load_url_admission_policy
from web_search_web_model import UrlLedgerRepository

payload = json.loads({payload_literal!r})

store = CrawlerRuntimeStore(settings.CRAWLER_DB_PATH)
url_ledger = UrlLedgerRepository(
    load_url_admission_policy(settings.URL_ADMISSION_RULES_PATH),
)
result = refill_crawl_frontier_from_links(
    store=store,
    url_ledger=url_ledger,
    limit=int(payload["limit"]),
    sample_percent=float(payload["sample_percent"]),
    sample_limit=int(payload["sample_limit"]),
    statement_timeout_ms=int(payload["statement_timeout_ms"]),
    dry_run=bool(payload["dry_run"]),
)

print(f"CANDIDATES {{result.candidates}}")
for url in result.urls:
    print(f"URL {{url}}")

if bool(payload["dry_run"]):
    print("DRY_RUN")
print(
    f"SUMMARY candidates={{result.candidates}} "
    f"recorded={{result.recorded}} enqueued={{result.enqueued}}"
)
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refill PRD crawl queue with diverse unindexed URLs sampled from links."
    )
    parser.add_argument("environment", choices=ENVIRONMENTS)
    parser.add_argument(
        "--server",
        help="SSH target. Defaults to the environment-specific host.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum URLs to enqueue.",
    )
    parser.add_argument(
        "--sample-percent",
        type=float,
        default=0.01,
        help="PostgreSQL TABLESAMPLE SYSTEM percentage for links.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10_000,
        help="Maximum sampled links to inspect before host diversity.",
    )
    parser.add_argument(
        "--statement-timeout-ms",
        type=int,
        default=30_000,
        help="Database statement timeout for candidate selection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print sampled URLs without recording or enqueueing them.",
    )
    args = parser.parse_args()

    server = args.server or os.environ.get("WEB_SEARCH_PRD_SERVER")
    if not server:
        parser.error("Set WEB_SEARCH_PRD_SERVER or pass --server")
    project_name = os.environ.get("WEB_SEARCH_PRD_PROJECT", DEFAULT_PROJECT)
    container = _resolve_crawler_container(server, project_name)
    payload = {
        "dry_run": args.dry_run,
        "limit": args.limit,
        "sample_percent": args.sample_percent,
        "sample_limit": args.sample_limit,
        "statement_timeout_ms": args.statement_timeout_ms,
    }
    remote_script = _build_remote_script(payload)
    result = _run(
        ["ssh", server, "docker", "exec", "-i", container, "python", "-"],
        input_text=remote_script,
    )

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
