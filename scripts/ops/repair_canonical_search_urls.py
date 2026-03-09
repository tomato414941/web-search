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

DEFAULT_URLS = (
    "https://fastapi.tiangolo.com/",
    "https://fastapi.tiangolo.com/tutorial/background-tasks/",
    "https://platform.openai.com/docs/overview",
    "https://platform.openai.com/docs/api-reference/introduction",
    "https://www.postgresql.org/docs/current/datatype-json.html",
    "https://docs.docker.com/reference/cli/docker/compose/up/",
)


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


def _resolve_container(server: str, prefix: str, app_uuid: str) -> str:
    result = _run(
        [
            "ssh",
            server,
            (
                "docker ps --format '{{.Names}}' "
                f"| grep '^{prefix}-{app_uuid}-' | head -n1"
            ),
        ]
    )
    if result.returncode != 0 or not result.stdout.strip():
        stderr = result.stderr.strip()
        raise RuntimeError(
            f"Failed to resolve {prefix} container for {app_uuid}: "
            f"{stderr or 'not found'}"
        )
    return result.stdout.strip()


def _build_remote_script(urls: Sequence[str]) -> str:
    payload = json.dumps(list(urls), ensure_ascii=True)
    return f"""
import asyncio
import json

import aiohttp

from app.core.config import settings
from app.services.indexer import submit_page_to_indexer
from app.utils.parser import parse_page

urls = json.loads({payload!r})
headers = {{"User-Agent": "PaleBlueSearchBot/1.0"}}


async def repair_url(session: aiohttp.ClientSession, url: str) -> None:
    try:
        async with session.get(url, allow_redirects=True) as response:
            body = await response.text(errors="ignore")
            print(f"URL {{url}}")
            print(f"  status={{response.status}}")
            print(f"  final_url={{response.url}}")
            if response.status != 200:
                print("  result=fetch_failed")
                return

            parsed = parse_page(body, str(response.url))
            print(f"  title_len={{len(parsed.title)}}")
            print(f"  content_len={{len(parsed.content)}}")
            submit_result = await submit_page_to_indexer(
                session,
                settings.INDEXER_API_URL,
                settings.INDEXER_API_KEY,
                str(response.url),
                parsed.title,
                parsed.content,
                outlinks=parsed.outlinks,
                published_at=parsed.published_at,
                updated_at=parsed.updated_at,
                author=parsed.author,
                organization=parsed.organization,
            )
            print(
                "  submit="
                f"ok={{submit_result.ok}} "
                f"status={{submit_result.status_code}} "
                f"job_id={{submit_result.job_id}} "
                f"detail={{submit_result.detail}}"
            )
    except Exception as exc:
        print(f"URL {{url}}")
        print(f"  result=error type={{type(exc).__name__}} detail={{exc}}")


async def main() -> None:
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for url in urls:
            await repair_url(session, url)


asyncio.run(main())
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and resubmit canonical search URLs on STG/PRD."
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
        help="Canonical URL to repair. Repeatable.",
    )
    args = parser.parse_args()

    urls = tuple(args.urls) or DEFAULT_URLS
    crawler = _resolve_container(args.server, "crawler", APP_UUIDS[args.environment])
    result = _run(
        ["ssh", args.server, "docker", "exec", "-i", crawler, "python", "-"],
        input_text=_build_remote_script(urls),
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
