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

payload = json.loads({payload_literal!r})
store = CrawlerRuntimeStore(
    settings.CRAWLER_DB_PATH,
    recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
)

summary = store.purge_admission_rejected_urls(
    limit=int(payload["limit"]),
    domains=tuple(payload["domains"]),
    dry_run=bool(payload["dry_run"]),
)

print(f"MATCHED {{summary['matched']}}")
print(f"CRAWL_QUEUE_DELETED {{summary['crawl_queue_deleted']}}")
for row in summary["candidates"]:
    print(
        "CANDIDATE "
        + row["source"]
        + " "
        + row["reason_code"]
        + " "
        + row["url"]
    )
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Purge scheduled crawl URLs rejected by URL admission policy."
    )
    parser.add_argument("environment", choices=ENVIRONMENTS)
    parser.add_argument(
        "--server",
        help="SSH target. Defaults to the environment-specific host.",
    )
    parser.add_argument(
        "--domain",
        action="append",
        dest="domains",
        default=[],
        help="Restrict purge to one or more domains. Repeatable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of rejected URLs to inspect and purge (default: 200).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matching URLs without deleting anything.",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be greater than zero")
    if not args.domains:
        parser.error("Provide at least one --domain to keep the purge scoped")

    server = args.server or os.environ.get("WEB_SEARCH_PRD_SERVER")
    if not server:
        parser.error("Set WEB_SEARCH_PRD_SERVER or pass --server")
    project_name = os.environ.get("WEB_SEARCH_PRD_PROJECT", DEFAULT_PROJECT)
    container = _resolve_crawler_container(server, project_name)
    payload = {
        "domains": args.domains,
        "limit": args.limit,
        "dry_run": args.dry_run,
    }
    result = _run(
        ["ssh", server, "docker", "exec", "-i", container, "python", "-"],
        input_text=_build_remote_script(payload),
    )

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
