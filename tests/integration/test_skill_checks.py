# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the checkers in skill_checks.py, run against inline samples."""

from __future__ import annotations

import textwrap
from pathlib import Path

import skill_checks as sc


def test_iter_fences_returns_language_code_and_line() -> None:
    markdown = "intro\n\n```python\nx = 1\n```\n\ntext\n```bash\nls\n```\n"
    fences = list(sc.iter_fences(markdown))
    assert [(f.lang, f.code, f.line) for f in fences] == [
        ("python", "x = 1", 3),
        ("bash", "ls", 8),
    ]


def test_iter_fences_ignores_unclosed_block() -> None:
    assert list(sc.iter_fences("```python\nx = 1\n")) == []


def test_iter_fences_keeps_shorter_fence_inside_longer_one() -> None:
    markdown = "````markdown\n```python\nx = 1\n```\n````\n"
    fences = list(sc.iter_fences(markdown))
    assert len(fences) == 1
    assert "```python" in fences[0].code


def test_python_syntax_error_accepts_valid_code() -> None:
    assert sc.python_syntax_error("x = 1\nprint(x)") is None


def test_python_syntax_error_accepts_indented_fragment() -> None:
    assert sc.python_syntax_error("    from a import b\n    b()") is None


def test_python_syntax_error_accepts_dict_entry_fragment() -> None:
    assert sc.python_syntax_error('"env": [{"name": "A", "value": "b"}]') is None


def test_python_syntax_error_reports_broken_code() -> None:
    error = sc.python_syntax_error("def broken(:\n    pass")
    assert error is not None
    assert "line 1" in error


def test_shell_syntax_error_accepts_placeholders() -> None:
    assert sc.shell_syntax_error("python scripts/x.py --id <workload_id>") is None


def test_shell_syntax_error_reports_unclosed_quote() -> None:
    assert sc.shell_syntax_error('echo "unterminated') is not None


def test_broken_references_passes_when_targets_exist(tmp_path: Path) -> None:
    (tmp_path / "references").mkdir()
    (tmp_path / "references/a.md").write_text("a")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run.py").write_text("")
    md = "[a](references/a.md#top) and [site](https://example.com)\n```bash\npython scripts/run.py --x <y>\n```\n"
    assert sc.broken_references(md, tmp_path / "SKILL.md", tmp_path) == []


def test_broken_references_reports_missing_link_and_script(tmp_path: Path) -> None:
    md = "[a](references/gone.md)\n```bash\npython scripts/gone.py\n```\n"
    assert sc.broken_references(md, tmp_path / "SKILL.md", tmp_path) == [
        "references/gone.md",
        "scripts/gone.py",
    ]


def test_broken_references_skips_placeholder_and_absolute_paths(tmp_path: Path) -> None:
    md = "```bash\npython <skill_dir>/x.py\npython /opt/tool/x.py\n```\n"
    assert sc.broken_references(md, tmp_path / "SKILL.md", tmp_path) == []


def test_script_help_failure_returns_none_for_working_script(tmp_path: Path) -> None:
    script = tmp_path / "ok.py"
    script.write_text("import argparse\nargparse.ArgumentParser().parse_args()\n")
    assert sc.script_help_failure(script, tmp_path) is None


def test_script_help_failure_reports_import_error(tmp_path: Path) -> None:
    script = tmp_path / "bad.py"
    script.write_text("import no_such_module_xyz\n")
    error = sc.script_help_failure(script, tmp_path)
    assert error is not None
    assert "no_such_module_xyz" in error


def test_script_help_failure_runs_in_given_workdir(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    script = tmp_path / "side_effect.py"
    script.write_text(
        textwrap.dedent(
            """\
            import argparse
            from pathlib import Path
            Path("marker").write_text("x")
            argparse.ArgumentParser().parse_args()
            """
        )
    )
    assert sc.script_help_failure(script, work) is None
    assert (work / "marker").exists()
    assert not (tmp_path / "marker").exists()
