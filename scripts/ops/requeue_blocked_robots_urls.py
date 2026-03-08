#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from typing import Sequence


DEFAULT_SERVER = "root@5.223.74.201"

APP_UUIDS = {
    "stg": "y0ckcsw84wckcs4g0co8oswo",
    "prd": "i8gkcwc00s488g8c4oo84csk",
}


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


def _resolve_crawler_container(server: str, app_uuid: str) -> str:
    result = _run(
        [
            "ssh",
            server,
            f"docker ps --format '{{{{.Names}}}}' | grep '^crawler-{app_uuid}-' | head -n1",
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"Failed to resolve crawler container for {app_uuid}: {stderr or 'not found'}"
        )
    return result.stdout.strip()


def _build_remote_script(payload: dict[str, object]) -> str:
    payload_literal = json.dumps(payload, ensure_ascii=True)
    return f"""
import json

from app.core.config import settings
from app.db.url_store import UrlStore
from shared.postgres.search import get_connection, sql_placeholder

payload = json.loads({payload_literal!r})
limit = int(payload["limit"])
dry_run = bool(payload["dry_run"])
urls = payload["urls"]
domains = payload["domains"]
force_urls = payload["force_urls"]
scan_candidates = bool(payload["scan_candidates"])

store = UrlStore(
    settings.CRAWLER_DB_PATH,
    recrawl_after_days=settings.CRAWL_RECRAWL_AFTER_DAYS,
    max_pending_per_domain=settings.MAX_PENDING_PER_DOMAIN,
)

ph = sql_placeholder()
candidates = []
if scan_candidates:
    where = [
        f"latest.status = {{ph}}",
        f"latest.error_message = {{ph}}",
        "d.url IS NULL",
        "q.url IS NULL",
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
    LEFT JOIN crawl_queue q ON q.url = u.url
    WHERE {{' AND '.join(where)}}
    ORDER BY latest.created_at DESC
    LIMIT {{ph}}
    \"\"\"
    params.append(limit)

    conn = get_connection(settings.CRAWLER_DB_PATH)
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
    requeued = 0
    skipped = 0
    conn = get_connection(settings.CRAWLER_DB_PATH)
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
            inserted = store.add(url)
        else:
            inserted = store.requeue(url)
        if inserted:
            requeued += 1
            print(f"REQUEUED {{url}}")
        else:
            skipped += 1
            print(f"SKIPPED {{url}}")
    print(f"SUMMARY requeued={{requeued}} skipped={{skipped}}")
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Requeue URLs previously blocked by robots.txt on STG/PRD crawler."
    )
    parser.add_argument("environment", choices=sorted(APP_UUIDS))
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help=f"SSH target (default: {DEFAULT_SERVER})",
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
        help="Requeue an exact URL even if it is not in the blocked-url candidate set.",
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
        help="Print matching URLs without requeueing them.",
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

    container = _resolve_crawler_container(args.server, APP_UUIDS[args.environment])
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
        ["ssh", args.server, "docker", "exec", "-i", container, "python", "-"],
        input_text=remote_script,
    )

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
