# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Free preflight checks to run before a skill reaches the paid LLM evaluation.

The e2e judge reads SKILL.md text only. It cannot tell that a linked file is
missing, that a sample does not parse, or that a script crashes on import.
These tests check exactly that, offline.

Every finding is formatted as "<path relative to skills/>: <message>".
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest
import skill_checks as sc

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

IGNORED_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf"}


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
    findings: list[str] = []
    for skill_md in sorted(skill_dir.rglob("SKILL.md")):
        metadata = frontmatter.load(skill_md).metadata
        findings.extend(sc.frontmatter_findings(metadata, relative(skill_md)))
    return findings


def reference_findings(skill_dir: Path) -> list[str]:
    findings: list[str] = []
    for md in markdown_files(skill_dir):
        for target in sc.broken_references(
            md.read_text(encoding="utf-8"), md, skill_dir
        ):
            findings.append(f"{relative(md)}: missing file {target}")
    return findings


def python_sample_findings(skill_dir: Path) -> list[str]:
    findings: list[str] = []
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
    findings: list[str] = []
    for md in markdown_files(skill_dir):
        for fence in sc.iter_fences(md.read_text(encoding="utf-8")):
            if fence.lang in sc.SHELL_LANGS and (
                error := sc.shell_syntax_error(fence.code)
            ):
                findings.append(
                    f"{relative(md)}: shell sample at line {fence.line}: {error}"
                )
    return findings


def sensitive_file_findings(skill_dir: Path) -> list[str]:
    findings: list[str] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.suffix in IGNORED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(f"{relative(path)}: {f}" for f in sc.sensitive_findings(text))
    return findings


def script_findings(skill_dir: Path, workdir: Path) -> list[str]:
    findings: list[str] = []
    for script in sorted(skill_dir.rglob("*.py")):
        if sc.is_package_module(script):
            continue
        if "argparse" not in script.read_text(encoding="utf-8"):
            continue
        if error := sc.script_help_failure(script, workdir):
            findings.append(f"{relative(script)}: {error}")
    return findings


def test_script_findings_skips_modules_inside_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(globals(), "SKILLS_DIR", tmp_path)
    package = tmp_path / "scripts" / "tool"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cli.py").write_text("import argparse\nfrom . import helpers\n")
    assert script_findings(tmp_path, tmp_path) == []


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


def test_skill_files_hold_no_internal_or_secret_strings(skill_dir: Path) -> None:
    assert sensitive_file_findings(skill_dir) == []
