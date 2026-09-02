#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bump the shared plugin version across all tracked files and rename
CHANGELOG.md's ``[Unreleased]`` section, committing the result.

The version is shared across ``package.json``, ``.claude-plugin/plugin.json``,
``.claude-plugin/marketplace.json``, ``.cursor-plugin/plugin.json``, and
``gemini-extension.json``. This script bumps all five to the same new value,
renames CHANGELOG.md's ``[Unreleased]`` heading to that version with today's
date, adds a fresh empty ``[Unreleased]`` section, and commits the change.

It never pushes, tags, or creates a GitHub Release — a caller (normally a
GitHub Actions workflow) decides whether to run this at all and is
responsible for everything past the local commit.

Usage:
    uv run scripts/version_bump.py                    # minor bump (default)
    uv run scripts/version_bump.py --bump patch
    uv run scripts/version_bump.py --repo-root /path/to/checkout
"""

import argparse
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

CHANGELOG_HEADING = "## [Unreleased]"

VERSION_FILES = (
    ("package.json", ".version"),
    (".claude-plugin/plugin.json", ".version"),
    (".claude-plugin/marketplace.json", ".plugins[0].version"),
    (".cursor-plugin/plugin.json", ".version"),
    ("gemini-extension.json", ".version"),
)


def bump_version(current_version: str, bump: str) -> str:
    major, minor, patch = (int(part) for part in current_version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def read_version(package_json: Path) -> str:
    result = subprocess.run(
        ["jq", "-r", ".version", str(package_json)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def bump_json_version(
    repo_root: Path, relative_path: str, jq_path: str, new_version: str
) -> None:
    file_path = repo_root / relative_path
    result = subprocess.run(
        ["jq", "--arg", "v", new_version, f"{jq_path} = $v", str(file_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    file_path.write_text(result.stdout)


def extract_unreleased_body(changelog_text: str) -> str:
    start = changelog_text.index(CHANGELOG_HEADING) + len(CHANGELOG_HEADING)
    rest = changelog_text[start:]
    next_heading = rest.find("\n## [")
    body = rest if next_heading == -1 else rest[:next_heading]
    return body.strip()


def rename_unreleased_section(
    changelog_text: str, new_version: str, today: date
) -> str:
    replacement = f"{CHANGELOG_HEADING}\n\n## [{new_version}] - {today.isoformat()}"
    return changelog_text.replace(CHANGELOG_HEADING, replacement, 1)


def commit_release(repo_root: Path, new_version: str) -> None:
    changed_files = [relative_path for relative_path, _ in VERSION_FILES] + [
        "CHANGELOG.md"
    ]
    subprocess.run(["git", "add", *changed_files], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: release v{new_version}"],
        cwd=repo_root,
        check=True,
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bump", choices=("patch", "minor", "major"), default="minor")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root to operate on (defaults to the current directory).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else Path.cwd()

    changelog_path = repo_root / "CHANGELOG.md"
    changelog_text = changelog_path.read_text()
    unreleased_body = extract_unreleased_body(changelog_text)

    if not unreleased_body:
        print(
            "Nothing under [Unreleased] in CHANGELOG.md — add an entry before releasing.",
            file=sys.stderr,
        )
        return 1

    current_version = read_version(repo_root / "package.json")
    new_version = bump_version(current_version, args.bump)

    for relative_path, jq_path in VERSION_FILES:
        bump_json_version(repo_root, relative_path, jq_path, new_version)

    changelog_path.write_text(
        rename_unreleased_section(changelog_text, new_version, date.today())
    )

    commit_release(repo_root, new_version)

    print(new_version)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"version={new_version}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
