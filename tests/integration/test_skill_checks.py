# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the checkers in skill_checks.py, run against inline samples."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
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


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("see https://datarobot.atlassian.net/browse/APP-1", "internal host"),
        ("ask in datarobot.slack.com", "internal host"),
        ("endpoint = https://staging.datarobot.com/api/v2", "internal host"),
        ("contact jane.doe@datarobot.com", "employee email"),
        ("host = 10.20.30.40", "private IP address"),
        ("host = 192.168.1.5", "private IP address"),
        ("host = 172.16.0.9", "private IP address"),
        ("-----BEGIN RSA PRIVATE KEY-----", "private key"),
        ("key = AKIAABCDEFGHIJKLMNOP", "AWS access key id"),
        ('api_key = "abcd1234efgh5678ijkl"', "hardcoded credential"),
        ('"token": "abcd1234efgh5678ijkl"', "hardcoded credential"),
    ],
)
def test_sensitive_findings_flags_internal_and_secret_strings(
    text: str, label: str
) -> None:
    assert sc.sensitive_findings(text) == [f"{label} at line 1"]


def test_sensitive_findings_accepts_public_text_and_placeholders() -> None:
    text = "\n".join(  # noqa: FLY002 - one fixture line per item
        [
            "endpoint = https://app.datarobot.com/api/v2",
            'api_key = "<your-api-key>"',
            "token = os.environ['DATAROBOT_API_TOKEN']",
            "contact support@example.com",
            "Python 3.10.12 and template 11.12.4",
            "host = 172.32.0.1",
        ]
    )
    assert sc.sensitive_findings(text) == []


def test_sensitive_findings_reports_line_number_without_the_secret() -> None:
    findings = sc.sensitive_findings('ok\napi_key = "abcd1234efgh5678ijkl"')
    assert findings == ["hardcoded credential at line 2"]
    assert "abcd1234" not in findings[0]


def test_shell_syntax_error_accepts_heredoc_body() -> None:
    assert sc.shell_syntax_error('cat <<EOF > out.json\n{"a": (1)}\nEOF') is None


def test_shell_syntax_error_still_sees_errors_next_to_redirections() -> None:
    assert (
        sc.shell_syntax_error('wc -l < input.txt > out.txt "unterminated') is not None
    )


def test_prose_outside_fences_blanks_code_and_keeps_text() -> None:
    markdown = "see [a](a.md)\n```python\nhandlers[name](event)\n```\nand [b](b.md)\n"
    prose = sc.prose_outside_fences(markdown)
    assert "[a](a.md)" in prose
    assert "[b](b.md)" in prose
    assert "handlers" not in prose


def test_broken_references_ignores_call_syntax_inside_code_fences(
    tmp_path: Path,
) -> None:
    md = "```python\nhandlers[name](event)\n```\n"
    assert sc.broken_references(md, tmp_path / "SKILL.md", tmp_path) == []


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("export DATAROBOT_API_TOKEN=Nj1234567890abcdefghij", "hardcoded credential"),
        ('secret = "dGhpcy1pcy1hLXNlY3JldC12YWx1ZQ=="', "hardcoded credential"),
        ('"token": "eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJl"', "hardcoded credential"),
        ("Authorization: Bearer abcdEFGH1234ijklMNOP5678", "bearer token"),
        ("key = ASIAABCDEFGHIJKLMNOP", "AWS access key id"),
        ("see datarobot.enterprise.slack.com", "internal host"),
    ],
)
def test_sensitive_findings_flags_unquoted_and_encoded_secrets(
    text: str, label: str
) -> None:
    assert sc.sensitive_findings(text) == [f"{label} at line 1"]


def test_sensitive_findings_accepts_public_hosts_role_mailboxes_and_calls() -> None:
    text = "\n".join(  # noqa: FLY002 - one fixture line per item
        [
            "https://your-company.atlassian.net/browse/X-1",
            "https://hooks.slack.com/services/T000/B000/xxxx",
            "write to support@datarobot.com",
            "api_token = read_credentials(target_dir)",
            "DATAROBOT_API_TOKEN=your-api-token-here-12345",
            "Authorization: Bearer $DATAROBOT_API_TOKEN",
            "host 10.0.0.1.",
        ]
    )
    assert sc.sensitive_findings(text) == ["private IP address at line 7"]


def valid_metadata() -> dict[str, object]:
    return {"name": "datarobot-x", "description": "Use when testing.", "license": "x"}


def test_frontmatter_findings_accepts_valid_metadata() -> None:
    assert sc.frontmatter_findings(valid_metadata(), "datarobot-x/SKILL.md") == []


@pytest.mark.parametrize(
    "name", ["Datarobot-X", "datarobot--x", "-x", "x_y", "a" * 65, ""]
)
def test_frontmatter_findings_rejects_bad_name(name: str) -> None:
    metadata = {**valid_metadata(), "name": name}
    findings = sc.frontmatter_findings(metadata, "p/SKILL.md")
    assert len(findings) == 1
    assert "name" in findings[0]


def test_frontmatter_findings_rejects_long_description() -> None:
    metadata = {**valid_metadata(), "description": "d" * 1025}
    assert "1025 characters" in sc.frontmatter_findings(metadata, "p/SKILL.md")[0]


def test_frontmatter_findings_accepts_description_at_the_limit() -> None:
    metadata = {**valid_metadata(), "description": "d" * 1024}
    assert sc.frontmatter_findings(metadata, "p/SKILL.md") == []


@pytest.mark.parametrize("compatibility", ["", "   ", "c" * 501])
def test_frontmatter_findings_rejects_bad_compatibility(compatibility: str) -> None:
    metadata = {**valid_metadata(), "compatibility": compatibility}
    findings = sc.frontmatter_findings(metadata, "p/SKILL.md")
    assert len(findings) == 1
    assert "compatibility" in findings[0]


def test_frontmatter_findings_rejects_unknown_key() -> None:
    metadata = {**valid_metadata(), "version": "1"}
    assert sc.frontmatter_findings(metadata, "p/SKILL.md") == [
        "p/SKILL.md: unknown frontmatter key 'version'"
    ]


def test_is_package_module_true_beside_init_file(tmp_path: Path) -> None:
    (tmp_path / "__init__.py").write_text("")
    module = tmp_path / "cli.py"
    module.write_text("")
    assert sc.is_package_module(module)


def test_is_package_module_false_for_plain_script(tmp_path: Path) -> None:
    script = tmp_path / "run.py"
    script.write_text("")
    assert not sc.is_package_module(script)


def test_script_help_failure_reports_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sc, "HELP_TIMEOUT_SECONDS", 1)
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(5)\n")
    assert sc.script_help_failure(script, tmp_path) == "timed out after 1s"


def test_script_help_failure_hides_datarobot_credentials_from_the_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATAROBOT_API_TOKEN", "secret-value")
    script = tmp_path / "env_check.py"
    script.write_text(
        "import os, sys\nsys.exit(1 if 'DATAROBOT_API_TOKEN' in os.environ else 0)\n"
    )
    assert sc.script_help_failure(script, tmp_path) is None
