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

payload = json.loads({payload_literal!r})
dry_run = bool(payload["dry_run"])
urls = payload["urls"]

ordered_urls = []
seen = set()
for url in urls:
    if url in seen:
        continue
    ordered_urls.append(url)
    seen.add(url)

print(f"URLS {{len(ordered_urls)}}")
for url in ordered_urls:
    print(f"URL {{url}}")

if dry_run:
    print("DRY_RUN")
else:
    store = CrawlerRuntimeStore(settings.CRAWLER_DB_PATH)
    url_ledger = UrlLedgerRepository(
        load_url_admission_policy(settings.URL_ADMISSION_RULES_PATH),
    )

    recorded = url_ledger.record_discovered_urls(ordered_urls)
    enqueued = 0
    skipped = 0
    for url in ordered_urls:
        inserted = store.enqueue_url_for_crawl(url)
        if inserted:
            enqueued += 1
            print(f"ENQUEUED {{url}}")
        else:
            skipped += 1
            print(f"SKIPPED {{url}}")
    print(f"SUMMARY recorded={{recorded}} enqueued={{enqueued}} skipped={{skipped}}")
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record URLs in the URL ledger and enqueue them for PRD crawling."
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
        required=True,
        help="URL to record and enqueue. Repeatable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print URLs without recording or enqueueing them.",
    )
    args = parser.parse_args()

    server = args.server or os.environ.get("WEB_SEARCH_PRD_SERVER")
    if not server:
        parser.error("Set WEB_SEARCH_PRD_SERVER or pass --server")
    project_name = os.environ.get("WEB_SEARCH_PRD_PROJECT", DEFAULT_PROJECT)
    container = _resolve_crawler_container(server, project_name)
    payload = {
        "dry_run": args.dry_run,
        "urls": args.urls,
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
