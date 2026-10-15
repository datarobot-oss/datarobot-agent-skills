# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic checks on skill markdown, code samples and scripts.

Everything here runs offline and without an LLM, so it can gate a skill before
the paid evaluation (the LLM judge in tests/e2e or `claude plugin eval`).
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

# A placeholder is an identifier in angle brackets. `<<EOF` and `cmd < in > out` are not.
PLACEHOLDER_RE = re.compile(r"(?<!<)<[A-Za-z][\w-]*>")
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
SCRIPT_CALL_RE = re.compile(r"(?:python3?|bash|sh)\s+([^\s\"'`<>$|;&]+\.(?:py|sh))\b")
SHELL_LANGS = {"bash", "sh", "shell"}
PYTHON_LANGS = {"python", "py"}
HELP_TIMEOUT_SECONDS = 30

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

# The repository is public, so skills must not carry internal hosts, employee
# addresses, private network addresses or credentials.
_PLACEHOLDER_WORDS = r"(?:your|example|placeholder|changeme|x{4,}|here)"
_SECRET_VALUE = r"[A-Za-z0-9_+/=.-]{16,}"
SENSITIVE_PATTERNS = {
    "internal host": re.compile(
        r"datarobot\.atlassian\.net|datarobot(?:\.enterprise)?\.slack\.com|staging\.datarobot\.com",
        re.IGNORECASE,
    ),
    "employee email": re.compile(
        r"(?<![\w.+-])(?!(?:support|security|info|noreply|no-reply)@)[\w.+-]+@datarobot\.com",
        re.IGNORECASE,
    ),
    "private IP address": re.compile(
        r"(?<![\d.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?!\d|\.\d)"
    ),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "hardcoded credential": re.compile(
        rf"""(?:api[_-]?key|token|secret|password)["']?\s*[:=]\s*(?!["']?[^\s"']*{_PLACEHOLDER_WORDS})"""
        rf"""(?:["']{_SECRET_VALUE}["']|(?=[^\s"']*\d){_SECRET_VALUE}(?=\s|$))""",
        re.IGNORECASE,
    ),
    "bearer token": re.compile(
        rf"Bearer\s+(?!{_PLACEHOLDER_WORDS}){_SECRET_VALUE}", re.IGNORECASE
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


def prose_outside_fences(markdown: str) -> str:
    """Return the markdown with every fenced block, fences included, blanked out."""
    lines = markdown.splitlines()
    for fence in iter_fences(markdown):
        end = fence.line + len(fence.code.splitlines()) + 1
        for index in range(fence.line - 1, min(end, len(lines))):
            lines[index] = ""
    return "\n".join(lines)


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
            first_error = first_error or f"{exc.msg} (sample line {exc.lineno})"
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
    for target in LINK_RE.findall(prose_outside_fences(markdown)):
        target = target.split("#", 1)[0]
        if not target or re.match(r"[a-z][a-z0-9+.-]*:", target) or "<" in target:
            continue
        if not (md_path.parent / target).exists():
            missing.append(target)
    for fence in iter_fences(markdown):
        if fence.lang not in SHELL_LANGS:
            continue
        for target in SCRIPT_CALL_RE.findall(fence.code):
            if target.startswith(("/", "~")):
                continue
            if (
                not (md_path.parent / target).exists()
                and not (skill_dir / target).exists()
            ):
                missing.append(target)
    return missing


def frontmatter_findings(metadata: Mapping[str, object], path: str) -> list[str]:
    """Return violations of the agentskills.io frontmatter rules, each prefixed with path."""
    findings: list[str] = []
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


def is_package_module(script: Path) -> bool:
    """Return True for a module inside a Python package, which cannot run as a script."""
    return (script.parent / "__init__.py").exists()


def sensitive_findings(text: str) -> list[str]:
    """Return "<label> at line N" for each internal or secret-like string in text.

    The matched text is left out so a real credential never reaches a CI log.
    """
    findings: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        for label, pattern in SENSITIVE_PATTERNS.items():
            if pattern.search(line):
                findings.append(f"{label} at line {number}")
    return findings


def script_help_failure(script: Path, workdir: Path) -> str | None:
    """Run `script --help` and return its last stderr line on failure, or None.

    Runs in `workdir` without DATAROBOT_* variables, so a script that does work
    before argparse cannot reach a real environment, and scripts that write
    relative paths at import time do not litter the repository.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("DATAROBOT_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=HELP_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"timed out after {HELP_TIMEOUT_SECONDS}s"
    if result.returncode == 0:
        return None
    return (result.stderr.strip().splitlines() or [f"exit code {result.returncode}"])[
        -1
    ]
