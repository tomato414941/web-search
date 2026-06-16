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
from web_search_core.url_admission import load_url_admission_policy
from web_search_web_model import UrlLedgerRepository
from web_search_postgres.search import get_connection, sql_placeholder

payload = json.loads({payload_literal!r})
limit = int(payload["limit"])
dry_run = bool(payload["dry_run"])
urls = payload["urls"]
domains = payload["domains"]
force_urls = payload["force_urls"]
scan_candidates = bool(payload["scan_candidates"])

store = CrawlerRuntimeStore(settings.CRAWLER_DB_PATH)
url_ledger = UrlLedgerRepository(
    load_url_admission_policy(settings.URL_ADMISSION_RULES_PATH),
)

ph = sql_placeholder()
candidates = []
if scan_candidates:
    where = [
        f"latest.status = {{ph}}",
        f"latest.error_message = {{ph}}",
        "d.url IS NULL",
        "q.url_hash IS NULL",
    ]
    params = ["blocked", "Blocked by robots.txt"]

    if urls:
        where.append(f"u.url = ANY({{ph}})")
        params.append(urls)
    if domains:
        where.append(f"u.domain = ANY({{ph}})")
        params.append(domains)

    query = f\"\"\"
    WITH latest AS (
        SELECT DISTINCT ON (url) url, status, error_message, created_at
        FROM crawl_logs
        ORDER BY url, created_at DESC
    )
    SELECT u.url, u.domain, latest.created_at
    FROM latest
    JOIN urls u ON u.url = latest.url
    LEFT JOIN documents d ON d.url = u.url
    LEFT JOIN crawl_queue q ON q.url_hash = u.url_hash
    WHERE {{' AND '.join(where)}}
    ORDER BY latest.created_at DESC
    LIMIT {{ph}}
    \"\"\"
    params.append(limit)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        candidates = [row[0] for row in cur.fetchall()]
        cur.close()
    finally:
        conn.close()

ordered_urls = []
seen = set()
for url in force_urls + candidates:
    if url in seen:
        continue
    ordered_urls.append(url)
    seen.add(url)

print(f"CANDIDATES {{len(candidates)}}")
for url in candidates:
    print(f"CANDIDATE {{url}}")

if force_urls:
    print(f"FORCED {{len(force_urls)}}")
    for url in force_urls:
        print(f"FORCED_URL {{url}}")

if dry_run:
    print("DRY_RUN")
else:
    enqueued = 0
    skipped = 0
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT url FROM urls WHERE url = ANY(" + ph + ")",
            (force_urls or [""],),
        )
        existing_force_urls = set(row[0] for row in cur.fetchall())
        cur.close()
    finally:
        conn.close()

    for url in ordered_urls:
        if url in force_urls and url not in existing_force_urls:
            url_ledger.record_discovered_url(url)
        inserted = store.enqueue_url_for_crawl(url)
        if inserted:
            enqueued += 1
            print(f"ENQUEUED {{url}}")
        else:
            skipped += 1
            print(f"SKIPPED {{url}}")
    print(f"SUMMARY enqueued={{enqueued}} skipped={{skipped}}")
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enqueue URLs previously blocked by robots.txt on the PRD crawler."
    )
    parser.add_argument("environment", choices=ENVIRONMENTS)
    parser.add_argument(
        "--server",
        help="SSH target. Defaults to the environment-specific host.",
    )
    parser.add_argument(
        "--url",
        action="append",
        dest="urls",
        default=[],
        help="Restrict blocked-url selection to an exact URL. Repeatable.",
    )
    parser.add_argument(
        "--domain",
        action="append",
        dest="domains",
        default=[],
        help="Restrict blocked-url selection to a domain. Repeatable.",
    )
    parser.add_argument(
        "--force-url",
        action="append",
        dest="force_urls",
        default=[],
        help="Enqueue an exact URL even if it is not in the blocked-url candidate set.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum blocked-url candidates to select (default: 20).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matching URLs without enqueueing them.",
    )
    parser.add_argument(
        "--all-candidates",
        action="store_true",
        help="Scan the latest blocked robots candidates without a URL/domain filter.",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit must be greater than zero")
    if not args.all_candidates and not (args.urls or args.domains or args.force_urls):
        parser.error(
            "Provide --url/--domain/--force-url, or explicitly allow a broad scan with --all-candidates"
        )

    server = args.server or os.environ.get("WEB_SEARCH_PRD_SERVER")
    if not server:
        parser.error("Set WEB_SEARCH_PRD_SERVER or pass --server")
    project_name = os.environ.get("WEB_SEARCH_PRD_PROJECT", DEFAULT_PROJECT)
    container = _resolve_crawler_container(server, project_name)
    payload = {
        "limit": args.limit,
        "dry_run": args.dry_run,
        "urls": args.urls,
        "domains": args.domains,
        "force_urls": args.force_urls,
        "scan_candidates": args.all_candidates or bool(args.urls or args.domains),
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
