# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Validate plugin/marketplace definitions for Gemini, Claude, and Cursor:
- Gemini: structural checks on gemini-extension.json entries
- Claude: runs `claude plugin validate .` (official CLI)
- Cursor: structural checks on .cursor-plugin/plugin.json
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "gemini_entry" in metafunc.fixturenames:
        gemini_file = REPO_ROOT / "gemini-extension.json"
        if gemini_file.exists():
            with open(gemini_file, encoding="utf-8") as f:
                config = json.load(f)
            entries = config.get("skills", [])
        else:
            entries = []
        metafunc.parametrize(
            "gemini_entry",
            entries,
            ids=[e.get("name", str(i)) for i, e in enumerate(entries)],
        )


def test_gemini_entry_name_prefix(gemini_entry: dict) -> None:
    name = gemini_entry.get("name", "")
    assert name.startswith("datarobot-"), (
        f"gemini-extension.json skill name '{name}' does not start with 'datarobot-'"
    )


def test_gemini_entry_path_exists(gemini_entry: dict) -> None:
    path = gemini_entry.get("path", "")
    assert (REPO_ROOT / path).exists(), (
        f"gemini-extension.json path '{path}' does not exist on disk"
    )


def test_gemini_entry_name_matches_folder(gemini_entry: dict) -> None:
    name = gemini_entry.get("name", "")
    path = gemini_entry.get("path", "")
    parts = Path(path).parts
    folder_from_path = (
        parts[1]
        if len(parts) > 1 and parts[0] == "skills"
        else (parts[0] if parts else "")
    )
    assert name == folder_from_path, (
        f"gemini-extension.json skill name '{name}' does not match "
        f"folder '{folder_from_path}' in path '{path}'"
    )


def test_gemini_all_skills_included() -> None:
    """Assert that every skills/ subfolder is listed in gemini-extension.json."""
    skills_root = REPO_ROOT / "skills"
    skill_folders = {p.name for p in skills_root.iterdir() if p.is_dir()}

    gemini_file = REPO_ROOT / "gemini-extension.json"
    with open(gemini_file, encoding="utf-8") as f:
        config = json.load(f)
    listed_names = {e.get("name") for e in config.get("skills", [])}

    missing = skill_folders - listed_names
    assert not missing, (
        f"Skills present on disk but missing from gemini-extension.json: {sorted(missing)}"
    )


def test_gemini_extension_validate() -> None:
    """Validate the Gemini extension using the official `gemini extensions validate` CLI."""
    result = subprocess.run(
        ["gemini", "extensions", "validate", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`gemini extensions validate .` failed:\n{result.stdout}\n{result.stderr}"
    )


def test_claude_plugin_validate() -> None:
    """Validate the Claude plugin using the official `claude plugin validate` CLI."""
    result = subprocess.run(
        ["claude", "plugin", "validate", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`claude plugin validate .` failed:\n{result.stdout}\n{result.stderr}"
    )


CURSOR_PLUGIN_FILE = REPO_ROOT / ".cursor-plugin" / "plugin.json"
_CURSOR_REQUIRED_FIELDS = {"name", "description", "version", "skills_directory"}


@pytest.fixture(scope="module")
def cursor_plugin() -> dict:
    """Load and return the parsed .cursor-plugin/plugin.json manifest."""
    assert CURSOR_PLUGIN_FILE.exists(), (
        f".cursor-plugin/plugin.json not found at {CURSOR_PLUGIN_FILE}"
    )
    with open(CURSOR_PLUGIN_FILE, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("field", sorted(_CURSOR_REQUIRED_FIELDS))
def test_cursor_plugin_has_required_field(cursor_plugin: dict, field: str) -> None:
    assert field in cursor_plugin, (
        f".cursor-plugin/plugin.json is missing required field '{field}'"
    )


def test_cursor_plugin_name_prefix(cursor_plugin: dict) -> None:
    name = cursor_plugin.get("name", "")
    assert name.startswith("datarobot-"), (
        f".cursor-plugin/plugin.json name '{name}' does not start with 'datarobot-'"
    )


def test_cursor_plugin_skills_directory_exists(cursor_plugin: dict) -> None:
    skills_dir = cursor_plugin.get("skills_directory", "")
    assert (REPO_ROOT / skills_dir).is_dir(), (
        f".cursor-plugin/plugin.json skills_directory '{skills_dir}' does not exist"
    )


def test_all_plugin_versions_match() -> None:
    """Assert that all plugin manifests (Claude, Cursor, Gemini) declare the same version."""
    claude_plugin_file = REPO_ROOT / ".claude-plugin" / "plugin.json"
    claude_marketplace_file = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    cursor_plugin_file = REPO_ROOT / ".cursor-plugin" / "plugin.json"
    gemini_file = REPO_ROOT / "gemini-extension.json"

    with open(claude_plugin_file, encoding="utf-8") as f:
        claude_plugin_version = json.load(f)["version"]
    with open(claude_marketplace_file, encoding="utf-8") as f:
        claude_marketplace_version = json.load(f)["plugins"][0]["version"]
    with open(cursor_plugin_file, encoding="utf-8") as f:
        cursor_version = json.load(f)["version"]
    with open(gemini_file, encoding="utf-8") as f:
        gemini_version = json.load(f)["version"]

    versions = {
        ".claude-plugin/plugin.json": claude_plugin_version,
        ".claude-plugin/marketplace.json (plugins[0])": claude_marketplace_version,
        ".cursor-plugin/plugin.json": cursor_version,
        "gemini-extension.json": gemini_version,
    }
    unique_versions = set(versions.values())
    assert len(unique_versions) == 1, "Plugin versions are out of sync:\n" + "\n".join(
        f"  {name}: {ver}" for name, ver in versions.items()
    )
