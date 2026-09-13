"""Operate the link archive using runtime environment settings."""

import argparse
from dataclasses import asdict
import json
import sys

from web_search_web_model.archive.outbox import status
from web_search_web_model.archive.store import ObjectStore, read_current
from web_search_web_model.archive.snapshots import compact, iter_latest
from web_search_web_model.archive.worker import flush_once, healthy, run
from web_search_web_model.archive.legacy import export_legacy


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload and read page link observations in R2"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "health", "status", "flush", "compact", "export-legacy"):
        subparsers.add_parser(name)
    get = subparsers.add_parser("get", help="Read a page's latest archived observation")
    get.add_argument("url")
    get.add_argument(
        "--manifest", help="Read this frozen snapshot instead of latest state"
    )
    args = parser.parse_args()
    if args.command == "health":
        return 0 if healthy() else 1
    if args.command == "run":
        run()
        return 0
    store = ObjectStore.from_env()
    if args.command == "status":
        result = status()
        result["current_snapshot"] = read_current(store)[0]
    elif args.command == "flush":
        result = {"uploaded_pages": flush_once(store, force=True)}
    elif args.command == "compact":
        result = compact(store)
    elif args.command == "export-legacy":
        result = export_legacy(store)
    else:
        result = [
            asdict(record)
            for record in iter_latest(store, src=args.url, manifest_key=args.manifest)
        ]
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
