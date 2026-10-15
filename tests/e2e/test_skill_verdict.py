# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Offline tests for the verdict parser, run with the e2e suite."""

from __future__ import annotations

import pytest
from skill_verdict import parse_verdict

# Captured from CI run 38711299677: the judge rated the skill NEEDS WORK under a
# `##` heading, and the prose of the report contains the word "incomplete".
JUDGE_REPORT_WITH_H2 = """\
# Skill Evaluation Report

### What is unclear or missing
An install that fails midway leaves the workspace incomplete, and the skill does not say what to do.

## Overall Verdict

**NEEDS WORK** — The skill is architecturally sound with strong state management, but has several concrete gaps (missing-file fallbacks, empty model list handling) that would cause two agents to behave differently.
"""


def test_h2_heading_with_needs_work_is_not_read_as_incomplete() -> None:
    assert parse_verdict(JUDGE_REPORT_WITH_H2) == "NEEDS WORK"


@pytest.mark.parametrize(
    ("heading", "verdict_line", "expected"),
    [
        ("### Overall verdict", "**GOOD** — minor tweaks only.", "GOOD"),
        (
            "### Overall verdict",
            "INCOMPLETE — an agent would produce inconsistent results.",
            "INCOMPLETE",
        ),
        ("#### Overall Verdict", "NEEDS WORK — several gaps.", "NEEDS WORK"),
        ("# Overall verdict", "**NEEDS-WORK** — several gaps.", "NEEDS WORK"),
        ("## Overall Verdict", "GOOD (minor tweaks only)", "GOOD"),
    ],
)
def test_reads_the_label_at_any_heading_level(
    heading: str, verdict_line: str, expected: str
) -> None:
    assert parse_verdict(f"intro\n\n{heading}\n\n{verdict_line}\n") == expected


def test_reads_a_verdict_on_the_heading_line() -> None:
    assert parse_verdict("## Overall verdict: GOOD — fine.") == "GOOD"


def test_reads_a_bold_label_line() -> None:
    assert parse_verdict("**Overall verdict:** NEEDS WORK — gaps.") == "NEEDS WORK"


def test_label_wins_over_words_in_the_explanation() -> None:
    report = "### Overall verdict\n**NEEDS WORK** — the Windows guards are incomplete, and the rest is good."
    assert parse_verdict(report) == "NEEDS WORK"


def test_last_verdict_section_wins() -> None:
    report = "### Overall verdict\nGOOD\n\nrevised below\n\n### Overall verdict\nINCOMPLETE — broken."
    assert parse_verdict(report) == "INCOMPLETE"


def test_report_without_a_verdict_section_is_unknown_even_if_prose_says_incomplete() -> (
    None
):
    assert parse_verdict("The skill looks incomplete to me and has gaps.") == "UNKNOWN"


def test_verdict_section_without_a_known_label_is_unknown() -> None:
    assert parse_verdict("### Overall verdict\n\nHard to say.") == "UNKNOWN"


def test_empty_report_is_unknown() -> None:
    assert parse_verdict("") == "UNKNOWN"


def test_gate_uses_the_local_parser() -> None:
    import test_skills_e2e  # noqa: F401  # importing it applies the replacement
    from dr_agents_tester import pytest_plugin

    assert pytest_plugin.verdict_passes(JUDGE_REPORT_WITH_H2)
    assert not pytest_plugin.verdict_passes("### Overall verdict\nINCOMPLETE — broken.")
