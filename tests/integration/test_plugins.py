# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Validate plugin/marketplace definitions for Gemini, Claude, Codex, and Cursor:
- Gemini: runs `gemini extensions validate .` plus structural checks
- Claude: runs `claude plugin validate .` (official CLI)
- Codex: structural checks on .codex-plugin/plugin.json and optional `codex plugin validate .`
- Cursor: structural checks on .cursor-plugin/plugin.json
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
CODEX_PLUGIN_FILE = REPO_ROOT / ".codex-plugin" / "plugin.json"
CURSOR_PLUGIN_FILE = REPO_ROOT / ".cursor-plugin" / "plugin.json"
_CODEX_REQUIRED_FIELDS = {"name", "description", "version", "license"}
_CURSOR_REQUIRED_FIELDS = {"name", "description", "version", "skills_directory"}


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
        check=False,
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
        check=False,
    )
    assert result.returncode == 0, (
        f"`claude plugin validate .` failed:\n{result.stdout}\n{result.stderr}"
    )


@pytest.fixture(scope="module")
def codex_plugin() -> dict:
    """Load and return the parsed .codex-plugin/plugin.json manifest."""
    assert CODEX_PLUGIN_FILE.exists(), (
        f".codex-plugin/plugin.json not found at {CODEX_PLUGIN_FILE}"
    )
    with open(CODEX_PLUGIN_FILE, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("field", sorted(_CODEX_REQUIRED_FIELDS))
def test_codex_plugin_has_required_field(codex_plugin: dict, field: str) -> None:
    assert field in codex_plugin, (
        f".codex-plugin/plugin.json is missing required field '{field}'"
    )


def test_codex_plugin_name_prefix(codex_plugin: dict) -> None:
    name = codex_plugin.get("name", "")
    assert name.startswith("datarobot-"), (
        f".codex-plugin/plugin.json name '{name}' does not start with 'datarobot-'"
    )


def test_codex_plugin_version_matches_package_json(codex_plugin: dict) -> None:
    with open(REPO_ROOT / "package.json", encoding="utf-8") as f:
        package = json.load(f)
    assert codex_plugin.get("version") == package.get("version"), (
        ".codex-plugin/plugin.json version does not match package.json version"
    )


def test_codex_cli_supports_plugin_commands_if_available() -> None:
    """Check that the installed Codex CLI exposes plugin management commands."""
    codex_path = shutil.which("codex")
    if codex_path is None:
        pytest.skip("codex CLI not installed in test environment")

    result = subprocess.run(
        [codex_path, "plugin", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"`codex plugin --help` failed:\n{result.stdout}\n{result.stderr}"
    )
    assert (
        "add" in result.stdout and "list" in result.stdout and "remove" in result.stdout
    ), "Installed Codex CLI does not expose the expected plugin subcommands"


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
    """Assert that all plugin manifests (Claude, Codex, Cursor, Gemini) declare the same version."""
    claude_plugin_file = REPO_ROOT / ".claude-plugin" / "plugin.json"
    claude_marketplace_file = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    codex_plugin_file = REPO_ROOT / ".codex-plugin" / "plugin.json"
    cursor_plugin_file = REPO_ROOT / ".cursor-plugin" / "plugin.json"
    gemini_file = REPO_ROOT / "gemini-extension.json"

    with open(claude_plugin_file, encoding="utf-8") as f:
        claude_plugin_version = json.load(f)["version"]
    with open(claude_marketplace_file, encoding="utf-8") as f:
        claude_marketplace_version = json.load(f)["plugins"][0]["version"]
    with open(codex_plugin_file, encoding="utf-8") as f:
        codex_version = json.load(f)["version"]
    with open(cursor_plugin_file, encoding="utf-8") as f:
        cursor_version = json.load(f)["version"]
    with open(gemini_file, encoding="utf-8") as f:
        gemini_version = json.load(f)["version"]

    versions = {
        ".claude-plugin/plugin.json": claude_plugin_version,
        ".claude-plugin/marketplace.json (plugins[0])": claude_marketplace_version,
        ".codex-plugin/plugin.json": codex_version,
        ".cursor-plugin/plugin.json": cursor_version,
        "gemini-extension.json": gemini_version,
    }
    unique_versions = set(versions.values())
    assert len(unique_versions) == 1, "Plugin versions are out of sync:\n" + "\n".join(
        f"  {name}: {ver}" for name, ver in versions.items()
    )
