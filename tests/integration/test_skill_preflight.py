# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Free preflight checks to run before a skill reaches the paid LLM evaluation.

The e2e judge reads SKILL.md text only. It cannot tell that a linked file is
missing, that a sample does not parse, or that a script crashes on import.
These tests check exactly that, offline.

Every finding is formatted as "<path relative to skills/>: <message>".
"""

from __future__ import annotations

import re
from pathlib import Path

import frontmatter
import pytest
import skill_checks as sc

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

# https://agentskills.io/specification, plus the keys this repo already uses.
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 1024
MAX_COMPATIBILITY_CHARS = 500
ALLOWED_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
    "context-tokens",
}


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists())


def markdown_files(skill_dir: Path) -> list[Path]:
    return sorted(skill_dir.rglob("*.md"))


def relative(path: Path) -> str:
    return path.relative_to(SKILLS_DIR).as_posix()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "skill_dir" in metafunc.fixturenames:
        dirs = skill_dirs()
        metafunc.parametrize("skill_dir", dirs, ids=[d.name for d in dirs])


def frontmatter_findings(skill_dir: Path) -> list[str]:
    metadata = frontmatter.load(skill_dir / "SKILL.md").metadata
    path = relative(skill_dir / "SKILL.md")
    findings = []
    name = str(metadata.get("name", ""))
    if len(name) > MAX_NAME_CHARS or not NAME_RE.match(name):
        findings.append(
            f"{path}: name {name!r} must be lowercase words joined by single hyphens, at most {MAX_NAME_CHARS} characters"
        )
    description = str(metadata.get("description", ""))
    if len(description) > MAX_DESCRIPTION_CHARS:
        findings.append(
            f"{path}: description has {len(description)} characters, the limit is {MAX_DESCRIPTION_CHARS}"
        )
    compatibility = metadata.get("compatibility")
    if (
        compatibility is not None
        and not 0 < len(str(compatibility).strip()) <= MAX_COMPATIBILITY_CHARS
    ):
        findings.append(
            f"{path}: compatibility must be 1 to {MAX_COMPATIBILITY_CHARS} characters"
        )
    for key in sorted(set(metadata) - ALLOWED_FRONTMATTER_KEYS):
        findings.append(f"{path}: unknown frontmatter key {key!r}")
    return findings


def reference_findings(skill_dir: Path) -> list[str]:
    findings = []
    for md in markdown_files(skill_dir):
        for target in sc.broken_references(
            md.read_text(encoding="utf-8"), md, skill_dir
        ):
            findings.append(f"{relative(md)}: missing file {target}")
    return findings


def python_sample_findings(skill_dir: Path) -> list[str]:
    findings = []
    for md in markdown_files(skill_dir):
        for fence in sc.iter_fences(md.read_text(encoding="utf-8")):
            if fence.lang in sc.PYTHON_LANGS and (
                error := sc.python_syntax_error(fence.code)
            ):
                findings.append(
                    f"{relative(md)}: python sample at line {fence.line}: {error}"
                )
    return findings


def shell_sample_findings(skill_dir: Path) -> list[str]:
    findings = []
    for md in markdown_files(skill_dir):
        for fence in sc.iter_fences(md.read_text(encoding="utf-8")):
            if fence.lang in sc.SHELL_LANGS and (
                error := sc.shell_syntax_error(fence.code)
            ):
                findings.append(
                    f"{relative(md)}: shell sample at line {fence.line}: {error}"
                )
    return findings


def script_findings(skill_dir: Path, workdir: Path) -> list[str]:
    findings = []
    for script in sorted(skill_dir.rglob("*.py")):
        if "argparse" not in script.read_text(encoding="utf-8"):
            continue
        if error := sc.script_help_failure(script, workdir):
            findings.append(f"{relative(script)}: {error}")
    return findings


def test_frontmatter_follows_agentskills_spec(skill_dir: Path) -> None:
    assert frontmatter_findings(skill_dir) == []


def test_linked_files_and_script_paths_exist(skill_dir: Path) -> None:
    assert reference_findings(skill_dir) == []


def test_python_samples_parse(skill_dir: Path) -> None:
    assert python_sample_findings(skill_dir) == []


def test_shell_samples_parse(skill_dir: Path) -> None:
    assert shell_sample_findings(skill_dir) == []


def test_scripts_start_with_help(skill_dir: Path, tmp_path: Path) -> None:
    assert script_findings(skill_dir, tmp_path) == []
