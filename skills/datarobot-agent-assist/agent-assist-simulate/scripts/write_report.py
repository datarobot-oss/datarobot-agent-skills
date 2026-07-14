#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic final-outcome aggregation and report rendering."""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from contracts import (
    ConvergenceFailure,
    ConvergenceResult,
    NativeReportSummary,
    PromptPatchRecord,
    ScenarioResult,
    SimulationConfig,
    StructuralDiagnosis,
    SwarmResults,
)


class NativeReportState(Protocol):
    """Minimal completed-convergence state required by the native renderer."""

    started_at: str
    completed_at: str | None
    initial_spec_hash: str
    expected_spec_hash: str
    current_system_prompt: str
    actual_model: str | None
    config: SimulationConfig
    initial_results: SwarmResults
    latest_results: list[ScenarioResult]
    iteration_counts: dict[str, int]
    patches_applied: list[PromptPatchRecord]
    failures: list[ConvergenceFailure]


def format_structural_diagnosis(diagnosis: StructuralDiagnosis) -> str:
    """Render structured diagnosis in the legacy report's recommendation format."""
    hint = (
        f" Function to fix: {diagnosis.function_hint}"
        if diagnosis.function_hint
        else ""
    )
    return (
        f"Remaining risk: {diagnosis.remaining_risk} "
        f"Structural fix: {diagnosis.structural_recommendation}{hint}"
    )


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
                lines.append(f"> {turn.role.capitalize()}: {turn.content}")
        elif outcome.breach_reason:
            reason_label = (
                "Execution error"
                if outcome.status == "error"
                else "Final breach reason"
            )
            lines.append(f"**{reason_label}:** {outcome.breach_reason}")
            lines.append("**Transcript:**")
            for turn in outcome.transcript:
                lines.append(f"> {turn.role.capitalize()}: {turn.content}")
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
            diagnosis = (
                format_structural_diagnosis(scenario_result.structural_diagnosis)
                if scenario_result.structural_diagnosis
                else (
                    "Structural redesign required — prompt patching could not resolve this "
                    f"in {max_iterations} iteration(s)."
                )
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


def write_native_report(
    state: NativeReportState,
    spec_text: str,
    output_path: Path,
) -> NativeReportSummary:
    """Render a completed native convergence state without mutating its outcomes."""
    final_spec_hash = hashlib.sha256(spec_text.encode()).hexdigest()
    prompt_hash = hashlib.sha256(state.current_system_prompt.encode()).hexdigest()
    outcomes = list(state.latest_results)
    counts = {
        status: sum(1 for result in outcomes if result.status == status)
        for status in ("passed", "breach", "exhausted", "error")
    }
    ready = (
        len(outcomes) == counts["passed"]
        and not state.failures
        and len(outcomes) == len(state.initial_results.scenarios)
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    model_name = state.actual_model or "unknown (not exposed by harness)"
    fail_on = ", ".join(state.config.evaluation.fail_on)
    initial_by_id = {
        result.scenario.scenario_id: result for result in state.initial_results.scenarios
    }

    lines: list[str] = [
        "# Evaluation Report",
        "",
        "## Audit Metadata",
        f"- Configuration schema version: {state.config.schema_version}",
        f"- Coverage mode: {state.initial_results.coverage_mode}",
        f"- Evaluation mode: {state.config.evaluation.mode}",
        f"- Blocking severities (`fail_on`): {fail_on}",
        f"- Maximum convergence iterations: {state.config.convergence.max_iterations}",
        f"- Simulation started: {state.started_at}",
        f"- Convergence completed: {state.completed_at or 'unknown'}",
        f"- Report generated: {generated_at}",
        f"- Actual harness model: {model_name}",
        f"- Initial spec hash: `{state.initial_spec_hash}`",
        f"- Final spec hash: `{final_spec_hash}`",
        f"- Final system-prompt hash: `{prompt_hash}`",
        "",
        "## Summary",
        f"- Ready to deploy: {'yes' if ready else 'no'}",
        f"- Total confirmed scenarios: {len(outcomes)}",
        f"- Passed: {counts['passed']}",
        f"- Unresolved breaches: {counts['breach']}",
        f"- Exhausted: {counts['exhausted']}",
        f"- Errored: {counts['error']}",
        f"- Convergence worker failures: {len(state.failures)}",
        f"- Prompt patches applied: {len(state.patches_applied)}",
        "",
        "## Coverage",
        (
            "Tool behavior was simulated by independent fixture providers; "
            "no real external tools were executed."
            if state.initial_results.coverage_mode == "simulated"
            else "Approved selective read-only execution was requested for this run."
        ),
        "",
        "## Final Results by Scenario",
        "",
    ]

    for result in outcomes:
        scenario = result.scenario
        scenario_id = scenario.scenario_id or "(missing)"
        initial = initial_by_id.get(scenario.scenario_id)
        initial_status = initial.status if initial else "unknown"
        lines += [
            f"### [{scenario.track}] {scenario.name} — {result.status.upper()}",
            f"- Scenario ID: `{scenario_id}`",
            f"- Capability targeted: {scenario.capability_targeted or 'N/A'}",
            f"- Initial status: {initial_status}",
            f"- Final status: {result.status}",
            f"- Turns run: {result.turns_run}",
            f"- Convergence iterations: {state.iteration_counts.get(scenario_id, 0)}",
            f"- Severity: {result.severity or 'not available'}",
        ]
        if initial_status == "breach" and result.status == "passed":
            lines.append("- Convergence outcome: initial breach resolved")
        if result.evaluation_reason:
            lines.append(f"- Evaluation reason: {result.evaluation_reason}")
        if result.evidence:
            lines.append("- Evidence:")
            lines.extend(f"  - {item}" for item in result.evidence)
        if result.attempted_tool_calls:
            lines.append("- Attempted tool calls:")
            for call in result.attempted_tool_calls:
                argument_names = ", ".join(sorted(call.args)) or "(no arguments)"
                lines.append(f"  - `{call.tool_name}` (argument names: {argument_names})")
        lines.append("")

    lines += ["## Non-Blocking Scored Findings", ""]
    scored_findings = [
        result
        for result in outcomes
        if result.status == "passed" and result.severity not in {None, "none"}
    ]
    if scored_findings:
        for result in scored_findings:
            lines += [
                f"### {result.scenario.name}",
                f"- Severity: {result.severity}",
                f"- Reason: {result.evaluation_reason or '(none supplied)'}",
            ]
            lines.extend(f"- Evidence: {item}" for item in result.evidence)
            lines.append("")
    else:
        lines += ["No non-blocking scored findings.", ""]

    lines += ["## Prompt Patch Audit", ""]
    if state.patches_applied:
        for patch in state.patches_applied:
            lines += [
                f"### Iteration {patch.iteration}: {patch.description}",
                f"- Timestamp: {patch.timestamp}",
                f"- Addresses: {', '.join(patch.addresses_scenarios)}",
                f"- Reasoning: {patch.reasoning}",
                f"- Prompt hash before: `{patch.prompt_hash_before}`",
                f"- Prompt hash after: `{patch.prompt_hash_after}`",
                "- Appended system-prompt text:",
                "```text",
                patch.system_prompt_patch,
                "```",
                "",
            ]
    else:
        lines += ["No prompt patches applied.", ""]

    lines += ["## Structural Recommendations", ""]
    diagnosed = [
        result for result in outcomes if result.structural_diagnosis is not None
    ]
    if diagnosed:
        for result in diagnosed:
            diagnosis = result.structural_diagnosis
            if diagnosis is None:
                continue
            lines += [
                f"### {result.scenario.name}",
                f"- Remaining risk: {diagnosis.remaining_risk}",
                f"- Recommended structural change: {diagnosis.structural_recommendation}",
                f"- Function hint: {diagnosis.function_hint or 'not identified'}",
                "- Implementation changes require explicit user approval.",
                "",
            ]
    else:
        lines += ["No structural recommendations.", ""]

    lines += ["## Failures and Coverage Gaps", ""]
    error_results = [result for result in outcomes if result.status == "error"]
    unresolved = [
        result for result in outcomes if result.status in {"breach", "exhausted"}
    ]
    if not error_results and not state.failures and not unresolved:
        lines += ["No failures or confirmed-scenario coverage gaps.", ""]
    for result in error_results:
        lines += [
            f"- Scenario `{result.scenario.scenario_id}` errored: "
            f"{result.evaluation_reason or result.breach_reason or 'unknown error'}"
        ]
    for result in unresolved:
        lines += [
            f"- Scenario `{result.scenario.scenario_id}` remains {result.status}: "
            f"{result.breach_reason or result.evaluation_reason or 'unresolved violation'}"
        ]
    for failure in state.failures:
        lines += [
            f"- {failure.role} task `{failure.task_id}` failed for "
            f"{', '.join(failure.scenario_ids)}: {failure.reason}"
        ]
    lines.append("")

    lines += ["## Next Steps", ""]
    if ready:
        lines += [
            "All confirmed scenarios passed. This simulated evaluation is ready for the next "
            "deployment workflow stage.",
            "",
        ]
    else:
        lines += [
            "The agent is not ready based on this evaluation. Resolve the failures or unresolved "
            "scenarios above, then rerun the simulation.",
            "",
        ]

    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    temporary_path.write_text(content, encoding="utf-8")
    _archive_previous_report(output_path, final_spec_hash)
    temporary_path.replace(output_path)
    return NativeReportSummary(
        ready=ready,
        total=len(outcomes),
        passed=counts["passed"],
        breached=counts["breach"],
        exhausted=counts["exhausted"],
        errored=counts["error"],
        convergence_failures=len(state.failures),
        patches_applied=len(state.patches_applied),
        report_path=str(output_path),
    )


def _archive_previous_report(report_path: Path, final_spec_hash: str) -> None:
    if not report_path.is_file():
        return
    existing = report_path.read_text(encoding="utf-8")
    match = re.search(
        r"(?:\*\*Spec hash:\*\*|- Final spec hash:)\s*`?([0-9a-f]+)",
        existing,
    )
    if not match or match.group(1) == final_spec_hash:
        return
    archive = report_path.with_name(
        f"{report_path.stem}_{match.group(1)[:12]}{report_path.suffix}"
    )
    if archive.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        archive = report_path.with_name(
            f"{report_path.stem}_{match.group(1)[:12]}_{timestamp}{report_path.suffix}"
        )
    report_path.replace(archive)
