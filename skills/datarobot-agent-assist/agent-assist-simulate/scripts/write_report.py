#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic final-outcome aggregation and report rendering."""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from contracts import ConvergenceResult, ScenarioResult


def final_results(
    initial_results: list[ScenarioResult],
    convergence: ConvergenceResult,
) -> list[ScenarioResult]:
    """Return one authoritative final result per scenario in initial-run order."""
    replacements = {
        result.scenario.name: result
        for result in convergence.resolved + convergence.errors
    }
    replacements.update(
        {
            result.scenario.name: result.model_copy(update={"status": "exhausted"})
            for result in convergence.exhausted
        }
    )
    return [
        replacements.get(result.scenario.name, result) for result in initial_results
    ]


def write_report(
    results: list[ScenarioResult],
    convergence: ConvergenceResult,
    spec_text: str,
    max_iterations: int,
) -> Path:
    """Render and persist the authoritative evaluation report."""
    spec_hash = hashlib.sha256(spec_text.encode()).hexdigest()[:12]
    prompt_hash = hashlib.sha256(convergence.final_system_prompt.encode()).hexdigest()[
        :12
    ]
    report_path = Path.cwd() / "eval_report.md"

    if report_path.exists():
        existing = report_path.read_text(encoding="utf-8")
        for line in existing.splitlines()[:10]:
            match = re.search(r"\*\*Spec hash:\*\*\s*([0-9a-f]+)", line)
            if match and match.group(1) != spec_hash:
                archive = Path.cwd() / f"eval_report_{match.group(1)}.md"
                report_path.rename(archive)
                break

    outcomes = final_results(results, convergence)
    passed = sum(1 for result in outcomes if result.status == "passed")
    unresolved = sum(
        1 for result in outcomes if result.status in {"breach", "exhausted"}
    )
    errored = sum(1 for result in outcomes if result.status == "error")
    outcome_by_name = {result.scenario.name: result for result in outcomes}
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: list[str] = [
        "# Evaluation Report",
        f"**Date:** {timestamp}",
        f"**Spec hash:** {spec_hash}",
        f"**System prompt hash:** {prompt_hash}",
        "",
        "## Summary",
        f"- Total scenarios: {len(results)}",
        f"- Passed: {passed}",
        f"- Unresolved breaches: {unresolved}",
        f"- Errored: {errored}",
        f"- Patches applied: {len(convergence.patches_applied)}",
        "",
        "## Results by Scenario",
        "",
    ]

    for scenario_result in results:
        track = scenario_result.scenario.track
        name = scenario_result.scenario.name
        capability = scenario_result.scenario.capability_targeted or "N/A"
        outcome = outcome_by_name[name]
        lines.append(f"### [{track}] {name} — {outcome.status.upper()}")
        lines.append(f"**Capability targeted:** {capability}")
        lines.append(f"**Turns run:** {outcome.turns_run}")
        if scenario_result.status == "breach" and outcome.status == "passed":
            lines.append("**Initial result:** Breach resolved during convergence")
            lines.append(
                f"**Initial breach reason:** {scenario_result.breach_reason or '(none)'}"
            )
            lines.append("**Initial breach transcript:**")
            for turn in scenario_result.transcript:
                lines.append(f"> {turn['role'].capitalize()}: {turn['content']}")
        elif outcome.breach_reason:
            reason_label = (
                "Execution error"
                if outcome.status == "error"
                else "Final breach reason"
            )
            lines.append(f"**{reason_label}:** {outcome.breach_reason}")
            lines.append("**Transcript:**")
            for turn in outcome.transcript:
                lines.append(f"> {turn['role'].capitalize()}: {turn['content']}")
        lines.append("")

    lines += ["## Patches Applied", ""]
    if convergence.patches_applied:
        for fix in convergence.patches_applied:
            addresses = ", ".join(fix.addresses_scenarios) or fix.scenario_name
            lines += [
                f"### {fix.description}",
                f"**Addresses:** {addresses}",
                f"**Reasoning:** {fix.reasoning}",
                "**Added to system prompt:**",
                "```",
                fix.system_prompt_patch,
                "```",
                "",
            ]
    else:
        lines += ["No patches applied.", ""]

    lines += ["## Unresolved Scenarios", ""]
    if convergence.exhausted:
        for scenario_result in convergence.exhausted:
            diagnosis = scenario_result.structural_diagnosis or (
                "Structural redesign required — prompt patching could not resolve this "
                f"in {max_iterations} iteration(s)."
            )
            lines += [
                f"### {scenario_result.scenario.name}",
                f"**Track:** {scenario_result.scenario.track}",
                f"**Breach reason:** {scenario_result.breach_reason or '(none)'}",
                f"**Recommendation:** {diagnosis}",
                "",
            ]
    else:
        lines += ["No unresolved scenarios.", ""]

    lines += ["## Next Steps", ""]
    error_results = [result for result in outcomes if result.status == "error"]
    if error_results:
        names = ", ".join(result.scenario.name for result in error_results)
        lines += [
            f"Evaluation incomplete — the following scenarios errored: {names}",
            "Review the execution errors and rerun them before relying on this evaluation.",
            "",
        ]
        if convergence.exhausted:
            unresolved_names = ", ".join(
                result.scenario.name for result in convergence.exhausted
            )
            lines += [
                f"These scenarios also require structural changes: {unresolved_names}",
                "",
            ]
    elif convergence.exhausted:
        names = ", ".join(
            scenario_result.scenario.name for scenario_result in convergence.exhausted
        )
        lines += [
            f"The following require structural changes beyond system prompt patching: {names}",
            "Consider revising tool scope or access control logic for the affected capabilities.",
            "",
        ]
    else:
        lines += ["All scenarios passed. Your agent is ready to deploy.", ""]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
