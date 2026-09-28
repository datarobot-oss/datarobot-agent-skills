# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A self-contained prompt per finding for the user's own coding agent.

The report cannot ship file contents, so the prompt carries the citation,
the evidence, the reasoning and the guardrails; the receiving agent has the
repository and can read, edit and run tests the way a one-shot edit cannot.
"""

from __future__ import annotations

from . import paths
from .models import Finding

_RAILS = (
    "Work on a new branch. Read the cited file and its call sites before editing. "
    "Make the smallest change that closes the gap, keep the existing style, and run "
    "the test suite. Do not push or open a pull request; stop and show me the diff."
)


def _guidance(f: Finding) -> str:
    """The condition's fix guidance from its prompt file, when it has one."""
    if not f.fix_strategy or not str(f.fix_strategy).endswith(".md"):
        return ""
    try:
        text = paths.resolve(f.fix_strategy).read_text()
    except (OSError, ValueError):
        return ""
    body = [
        line
        for line in text.splitlines()
        if line.strip() and not line.startswith("#") and "_fix_contract" not in line
    ]
    return " ".join(line.strip() for line in body)


def agent_prompt(f: Finding, repo: str = "") -> str:
    where = f.file or "repo-wide"
    if f.file and f.line:
        where = f"{f.file}:{f.line}"
    lines = [
        f"In the repository at {repo or '<repo>'}, fix this gap-analysis finding.",
        "",
        f"Finding: {f.condition_id}, {f.title} (severity {f.severity.value}).",
        f"Where: {where}",
        f"Evidence: {f.evidence or 'see the file'}",
    ]
    if f.explanation:
        lines.append(f"Why it matters: {f.explanation}")
    if f.verification:
        lines.append(f"A verification pass noted: {f.verification}")
    if f.remediation:
        lines.append(f"Expected fix: {f.remediation}")
    guidance = _guidance(f)
    if guidance:
        lines.append(f"Guidance: {guidance}")
    if f.steps:
        lines.append("Steps:")
        lines.extend(f"  {i}. {step}" for i, step in enumerate(f.steps, 1))
    if f.prerequisite:
        lines.append(f"Prerequisite: {f.prerequisite}")
    if f.docs_url:
        lines.append(f"Docs: {f.docs_url}")
    if f.fix_risk == "business_logic":
        lines.append(
            "This touches business logic: preserve behaviour and add or extend a test "
            "that proves the gap is closed."
        )
    lines += ["", _RAILS]
    return "\n".join(lines)
