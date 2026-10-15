# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic checks on skill markdown, code samples and scripts.

Everything here runs offline and without an LLM, so it can gate a skill before
the paid evaluation (the LLM judge in tests/e2e or `claude plugin eval`).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
SCRIPT_CALL_RE = re.compile(r"(?:python3?|bash|sh)\s+([^\s\"'`<>$|;&]+\.(?:py|sh))\b")
SHELL_LANGS = {"bash", "sh", "shell"}
PYTHON_LANGS = {"python", "py"}

# The repository is public, so skills must not carry internal hosts, employee
# addresses, private network addresses or credentials.
SENSITIVE_PATTERNS = {
    "internal host": re.compile(
        r"atlassian\.net|slack\.com|staging\.datarobot\.com", re.IGNORECASE
    ),
    "employee email": re.compile(r"[\w.+-]+@datarobot\.com", re.IGNORECASE),
    "private IP address": re.compile(
        r"(?<![\d.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?![\d.])"
    ),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "hardcoded credential": re.compile(
        r"""(?:api[_-]?key|token|secret|password)["']?\s*[:=]\s*["'][A-Za-z0-9_-]{16,}["']""",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class Fence:
    lang: str
    code: str
    line: int


def iter_fences(markdown: str) -> Iterator[Fence]:
    """Yield each fenced code block with its language and opening line number."""
    lang, buf, start, ticks = "", [], 0, 0
    for number, raw in enumerate(markdown.splitlines(), 1):
        stripped = raw.strip()
        if not ticks:
            match = re.match(r"(`{3,})\s*(\w*)", stripped)
            if match:
                ticks, lang, start, buf = (
                    len(match.group(1)),
                    match.group(2).lower(),
                    number,
                    [],
                )
        elif re.fullmatch(rf"`{{{ticks},}}", stripped):
            yield Fence(lang, "\n".join(buf), start)
            ticks = 0
        else:
            buf.append(raw)


def python_syntax_error(code: str) -> str | None:
    """Return the syntax error of a Python sample, or None if it parses.

    A sample may be a fragment, such as a dict entry or an indented list item,
    so a dedented copy and a copy wrapped in braces count as valid too.
    """
    body = textwrap.dedent(code)
    first_error: str | None = None
    for candidate in (body, "{\n" + body + "\n}"):
        try:
            ast.parse(candidate)
            return None
        except SyntaxError as exc:
            first_error = first_error or f"{exc.msg} (line {exc.lineno})"
    return first_error


def shell_syntax_error(code: str) -> str | None:
    """Return the `bash -n` error of a shell sample, or None if it parses.

    Angle-bracket placeholders such as `<workload_id>` are replaced first,
    because bash would read them as redirections.
    """
    result = subprocess.run(
        ["bash", "-n"],
        input=PLACEHOLDER_RE.sub("PLACEHOLDER", code),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return None
    return (result.stderr.strip().splitlines() or ["syntax error"])[-1]


def broken_references(markdown: str, md_path: Path, skill_dir: Path) -> list[str]:
    """Return relative links and script paths in shell samples that do not exist.

    A script path counts as found when it resolves from the markdown file's
    directory or from the skill root.
    """
    missing: list[str] = []
    for target in LINK_RE.findall(markdown):
        target = target.split("#", 1)[0]
        if not target or re.match(r"[a-z][a-z0-9+.-]*:", target) or "<" in target:
            continue
        if not (md_path.parent / target).exists():
            missing.append(target)
    for fence in iter_fences(markdown):
        if fence.lang not in SHELL_LANGS:
            continue
        for target in SCRIPT_CALL_RE.findall(fence.code):
            if "<" in target or target.startswith(("/", "~")):
                continue
            if (
                not (md_path.parent / target).exists()
                and not (skill_dir / target).exists()
            ):
                missing.append(target)
    return missing


def sensitive_findings(text: str) -> list[str]:
    """Return "<label> at line N" for each internal or secret-like string in text.

    The matched text is left out so a real credential never reaches a CI log.
    """
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(line):
                findings.append(f"{label} at line {number}")
    return findings


def script_help_failure(script: Path, workdir: Path) -> str | None:
    """Run `script --help` and return its last stderr line on failure, or None.

    Runs in `workdir` so scripts that write relative paths at import time do
    not litter the repository.
    """
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode == 0:
        return None
    return (result.stderr.strip().splitlines() or [f"exit code {result.returncode}"])[
        -1
    ]
