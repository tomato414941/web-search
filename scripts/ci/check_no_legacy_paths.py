#!/usr/bin/env python3

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_TOP_LEVEL = ("frontend", "crawler", "indexer", "shared", "mcp")
LEGACY_WORKSPACE_DIRS = ("packages/shared",)
LEGACY_PACKAGE_DIRS = (
    "apps/frontend/src/frontend",
    "apps/crawler/src/app",
    "apps/indexer/src/app",
)
EXCLUDED_FILES = {"scripts/ci/check_no_legacy_paths.py"}
PATH_PATTERN = re.compile(
    r"(?<!apps/)(?<!packages/)(?<![A-Za-z0-9_./-])(?:frontend|crawler|indexer|shared|mcp)/(?![A-Za-z0-9_./-])"
)
JOIN_PATTERN = re.compile(
    r"""(?<!/[\"']apps[\"'])(?<!/[\"']packages[\"'])/[\"'](?:frontend|crawler|indexer|shared|mcp)[\"'](?:/|$)"""
)
IMPORT_PATTERN = re.compile(
    r"^\s*(?:from (?:app|frontend|shared)(?:\.|\s)|import (?:app|frontend|shared)(?:\s|$|\.))"
)
MODULE_PATTERN = re.compile(r"(?<!web_search_)frontend\.(?:api|services|core|i18n)")
WORKSPACE_PATTERN = re.compile(r"packages/shared(?:/|\b)")


def _iter_tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    entries = result.stdout.decode("utf-8").split("\0")
    return [REPO_ROOT / entry for entry in entries if entry]


def _find_legacy_entries() -> list[str]:
    errors: list[str] = []

    for name in LEGACY_TOP_LEVEL:
        path = REPO_ROOT / name
        if path.exists() or path.is_symlink():
            errors.append(f"legacy top-level path still exists: {name}")

    for name in LEGACY_PACKAGE_DIRS:
        path = REPO_ROOT / name
        if path.exists() or path.is_symlink():
            errors.append(f"legacy package path still exists: {name}")

    for name in LEGACY_WORKSPACE_DIRS:
        path = REPO_ROOT / name
        if path.exists() or path.is_symlink():
            errors.append(f"legacy workspace path still exists: {name}")

    for path in _iter_tracked_files():
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        if rel_path in EXCLUDED_FILES or path.is_symlink() or not path.exists():
            continue

        data = path.read_bytes()
        if b"\0" in data:
            continue

        text = data.decode("utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if PATH_PATTERN.search(line):
                errors.append(
                    f"{rel_path}:{lineno}: legacy path reference: {line.strip()}"
                )
            if IMPORT_PATTERN.search(line) or MODULE_PATTERN.search(line):
                errors.append(
                    f"{rel_path}:{lineno}: legacy import reference: {line.strip()}"
                )
            if WORKSPACE_PATTERN.search(line):
                errors.append(
                    f"{rel_path}:{lineno}: legacy workspace path reference: {line.strip()}"
                )

        normalized = re.sub(r"\s+", "", text)
        if JOIN_PATTERN.search(normalized):
            errors.append(f"{rel_path}: legacy root path join detected")

    return errors


def main() -> int:
    errors = _find_legacy_entries()
    if not errors:
        print("No legacy top-level paths found.")
        return 0

    print("Legacy path cleanup required:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
