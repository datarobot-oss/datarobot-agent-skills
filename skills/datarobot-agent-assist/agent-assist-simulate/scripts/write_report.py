#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic final-outcome aggregation and report rendering."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts import NativeReportSummary


def write_native_report(
    state: Any,
    output_path: Path,
) -> NativeReportSummary:
    """Render a completed native convergence state without mutating its outcomes."""
    outcomes = list(state.latest_results)
    counts = {
        status: sum(1 for result in outcomes if result.status == status)
        for status in ("passed", "breach", "exhausted", "error")
    }
    ready = len(outcomes) == counts["passed"] and len(outcomes) == len(
        state.initial_results.scenarios
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    model_name = state.actual_model or "unknown (not exposed by harness)"
    fail_on = ", ".join(state.config.evaluation.fail_on)
    initial_by_id = {
        result.scenario.scenario_id: result
        for result in state.initial_results.scenarios
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
        "",
        "## Summary",
        f"- Ready to deploy: {'yes' if ready else 'no'}",
        f"- Total confirmed scenarios: {len(outcomes)}",
        f"- Passed: {counts['passed']}",
        f"- Unresolved breaches: {counts['breach']}",
        f"- Exhausted: {counts['exhausted']}",
        f"- Errored: {counts['error']}",
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
                lines.append(
                    f"  - `{call.tool_name}` (argument names: {argument_names})"
                )
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

    lines += ["## Failures and Coverage Gaps", ""]
    error_results = [result for result in outcomes if result.status == "error"]
    unresolved = [
        result for result in outcomes if result.status in {"breach", "exhausted"}
    ]
    if not error_results and not unresolved:
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
    output_path.write_text(content, encoding="utf-8")
    return NativeReportSummary(
        ready=ready,
        total=len(outcomes),
        passed=counts["passed"],
        breached=counts["breach"],
        exhausted=counts["exhausted"],
        errored=counts["error"],
        report_path=str(output_path),
    )
