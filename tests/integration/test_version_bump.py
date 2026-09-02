# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise scripts/version_bump.py end to end against a scratch fixture repo,
so the real bump/rename/commit logic is tested, not a reimplementation of it."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

version_bump = importlib.import_module("version_bump")

VERSION_FILE_FIXTURES = {
    "package.json": {"name": "example-plugin", "version": "1.0.0"},
    ".claude-plugin/plugin.json": {"name": "example-plugin", "version": "1.0.0"},
    ".claude-plugin/marketplace.json": {
        "plugins": [{"name": "example-plugin", "version": "1.0.0"}]
    },
    ".cursor-plugin/plugin.json": {"name": "example-plugin", "version": "1.0.0"},
    "gemini-extension.json": {"name": "example-plugin", "version": "1.0.0"},
}

CHANGELOG_WITH_ENTRY = """# Changelog

## [Unreleased]

### Fixed
- `datarobot-example`: fixed a thing.

## [1.0.0] - 2026-01-01

### Added
- Initial release.
"""

CHANGELOG_EMPTY_UNRELEASED = """# Changelog

## [Unreleased]

## [1.0.0] - 2026-01-01

### Added
- Initial release.
"""


def _write_fixture_repo(tmp_path: Path, changelog_text: str) -> Path:
    for relative_path, content in VERSION_FILE_FIXTURES.items():
        file_path = tmp_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(content, indent=2) + "\n")
    (tmp_path / "CHANGELOG.md").write_text(changelog_text)
    pyproject = tmp_path / version_bump.PYPROJECT_FILE
    pyproject.parent.mkdir(parents=True, exist_ok=True)
    pyproject.write_text(
        '[project]\nname = "datarobot-skills-utils"\nversion = "1.0.0"\n'
    )

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial fixture"], cwd=tmp_path, check=True
    )
    return tmp_path


def _read_version(tmp_path: Path, relative_path: str, jq_path: str) -> str:
    result = subprocess.run(
        ["jq", "-r", jq_path, str(tmp_path / relative_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_bump_updates_all_tracked_files_to_the_same_version(tmp_path: Path) -> None:
    repo = _write_fixture_repo(tmp_path, CHANGELOG_WITH_ENTRY)

    exit_code = version_bump.main(["--repo-root", str(repo), "--bump", "minor"])

    assert exit_code == 0
    for relative_path, jq_path in version_bump.VERSION_FILES:
        assert _read_version(repo, relative_path, jq_path) == "1.1.0"
    pyproject_text = (repo / version_bump.PYPROJECT_FILE).read_text()
    assert 'version = "1.1.0"' in pyproject_text


def test_bump_renames_unreleased_section_with_fresh_empty_one(tmp_path: Path) -> None:
    repo = _write_fixture_repo(tmp_path, CHANGELOG_WITH_ENTRY)

    version_bump.main(["--repo-root", str(repo), "--bump", "minor"])

    changelog_text = (repo / "CHANGELOG.md").read_text()
    assert changelog_text.startswith("# Changelog\n\n## [Unreleased]\n\n## [1.1.0] -")
    assert "`datarobot-example`: fixed a thing." in changelog_text
    assert version_bump.extract_unreleased_body(changelog_text) == ""


def test_bump_commits_the_change(tmp_path: Path) -> None:
    repo = _write_fixture_repo(tmp_path, CHANGELOG_WITH_ENTRY)

    version_bump.main(["--repo-root", str(repo), "--bump", "minor"])

    log = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip() == "chore: release v1.1.0"


def test_patch_and_major_bumps(tmp_path: Path) -> None:
    repo = _write_fixture_repo(tmp_path, CHANGELOG_WITH_ENTRY)
    version_bump.main(["--repo-root", str(repo), "--bump", "patch"])
    assert _read_version(repo, "package.json", ".version") == "1.0.1"

    repo2 = _write_fixture_repo(tmp_path / "major", CHANGELOG_WITH_ENTRY)
    version_bump.main(["--repo-root", str(repo2), "--bump", "major"])
    assert _read_version(repo2, "package.json", ".version") == "2.0.0"


def test_empty_unreleased_section_fails_without_changing_anything(
    tmp_path: Path,
) -> None:
    repo = _write_fixture_repo(tmp_path, CHANGELOG_EMPTY_UNRELEASED)
    original_changelog = (repo / "CHANGELOG.md").read_text()

    exit_code = version_bump.main(["--repo-root", str(repo), "--bump", "minor"])

    assert exit_code == 1
    assert (repo / "CHANGELOG.md").read_text() == original_changelog
    assert _read_version(repo, "package.json", ".version") == "1.0.0"


@pytest.mark.parametrize(
    ("current", "bump", "expected"),
    [
        ("1.5.1", "patch", "1.5.2"),
        ("1.5.1", "minor", "1.6.0"),
        ("1.5.1", "major", "2.0.0"),
        ("1.9.9", "minor", "1.10.0"),
    ],
)
def test_bump_version_arithmetic(current: str, bump: str, expected: str) -> None:
    assert version_bump.bump_version(current, bump) == expected
