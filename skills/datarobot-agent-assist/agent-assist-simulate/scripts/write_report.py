#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic final-outcome aggregation and report rendering."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from swarm_contracts import (
    ChangeEntry,
    EvalReportData,
    NativeReportSummary,
    ReportCounts,
    ScenarioOutcome,
    ToolCallSummary,
)

STATUSES = ("passed", "breach", "exhausted", "error")


def build_report_data(
    state: Any,
    changes: list[ChangeEntry] | None = None,
    generated_at: str | None = None,
) -> EvalReportData:
    """Aggregate a completed convergence state into report data, without transcripts."""
    outcomes = list(state.latest_results)
    counts = {
        status: sum(1 for result in outcomes if result.status == status)
        for status in STATUSES
    }
    ready = len(outcomes) == counts["passed"] and len(outcomes) == len(
        state.initial_results.scenarios
    )
    initial_by_id = {
        result.scenario.scenario_id: result
        for result in state.initial_results.scenarios
    }
    scenarios = []
    for result in outcomes:
        scenario = result.scenario
        scenario_id = scenario.scenario_id or "(missing)"
        initial = initial_by_id.get(scenario.scenario_id)
        scenarios.append(
            ScenarioOutcome(
                scenario_id=scenario_id,
                name=scenario.name,
                track=scenario.track,
                capability_targeted=scenario.capability_targeted,
                expected_safe_behavior=scenario.expected_safe_behavior,
                initial_status=initial.status if initial else "unknown",
                initial_severity=initial.severity if initial else None,
                status=result.status,
                turns_run=result.turns_run,
                iterations=state.iteration_counts.get(scenario_id, 0),
                severity=result.severity,
                evaluation_reason=result.evaluation_reason,
                breach_reason=result.breach_reason,
                evidence=list(result.evidence),
                attempted_tool_calls=[
                    ToolCallSummary(
                        tool_name=call.tool_name, argument_names=sorted(call.args)
                    )
                    for call in result.attempted_tool_calls
                ],
            )
        )
    return EvalReportData(
        config_schema_version=state.config.schema_version,
        coverage_mode=state.initial_results.coverage_mode,
        evaluation_mode=state.config.evaluation.mode,
        fail_on=list(state.config.evaluation.fail_on),
        max_iterations=state.config.convergence.max_iterations,
        started_at=state.started_at,
        completed_at=state.completed_at,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        actual_model=state.actual_model,
        ready=ready,
        counts=ReportCounts(
            total=len(outcomes),
            passed=counts["passed"],
            breached=counts["breach"],
            exhausted=counts["exhausted"],
            errored=counts["error"],
        ),
        scenarios=scenarios,
        changes=changes,
    )


def render_markdown(
    data: EvalReportData,
    heading_offset: int = 0,
    standalone: bool = True,
) -> str:
    """Render report data as Markdown.

    `standalone=False` leaves out the title, the "Ready to deploy" line and Next
    Steps, so another report can embed these sections under its own verdict.
    `heading_offset` pushes every heading down that many levels.
    """

    def h(level: int, text: str) -> str:
        return f"{'#' * min(level + heading_offset, 6)} {text}"

    model_name = data.actual_model or "unknown (not exposed by harness)"
    counts = data.counts

    lines: list[str] = []
    if standalone:
        lines += [h(1, "Evaluation Report"), ""]
    lines += [
        h(2, "Audit Metadata"),
        f"- Configuration schema version: {data.config_schema_version}",
        f"- Coverage mode: {data.coverage_mode}",
        f"- Evaluation mode: {data.evaluation_mode}",
        f"- Blocking severities (`fail_on`): {', '.join(data.fail_on)}",
        f"- Maximum convergence iterations: {data.max_iterations}",
        f"- Simulation started: {data.started_at}",
        f"- Convergence completed: {data.completed_at or 'unknown'}",
        f"- Report generated: {data.generated_at}",
        f"- Actual harness model: {model_name}",
        "",
        h(2, "Summary"),
    ]
    if standalone:
        lines.append(f"- Ready to deploy: {'yes' if data.ready else 'no'}")
    lines += [
        f"- Total confirmed scenarios: {counts.total}",
        f"- Passed: {counts.passed}",
        f"- Unresolved breaches: {counts.breached}",
        f"- Exhausted: {counts.exhausted}",
        f"- Errored: {counts.errored}",
        "",
        h(2, "Coverage"),
        (
            "Tool behavior was simulated by independent fixture providers; "
            "no real external tools were executed."
            if data.coverage_mode == "simulated"
            else "Approved selective read-only execution was requested for this run."
        ),
        "",
        h(2, "Final Results by Scenario"),
        "",
    ]

    for outcome in data.scenarios:
        lines += [
            h(
                3,
                f"[{outcome.track}] {outcome.name} — {outcome.status.upper()}",
            ),
            f"- Scenario ID: `{outcome.scenario_id}`",
            f"- Capability targeted: {outcome.capability_targeted or 'N/A'}",
            f"- Initial status: {outcome.initial_status}",
            f"- Final status: {outcome.status}",
            f"- Turns run: {outcome.turns_run}",
            f"- Convergence iterations: {outcome.iterations}",
            f"- Severity: {outcome.severity or 'not available'}",
        ]
        if outcome.initial_status == "breach" and outcome.status == "passed":
            lines.append("- Convergence outcome: initial breach resolved")
        if outcome.evaluation_reason:
            lines.append(f"- Evaluation reason: {outcome.evaluation_reason}")
        if outcome.evidence:
            lines.append("- Evidence:")
            lines.extend(f"  - {item}" for item in outcome.evidence)
        if outcome.attempted_tool_calls:
            lines.append("- Attempted tool calls:")
            for call in outcome.attempted_tool_calls:
                argument_names = ", ".join(call.argument_names) or "(no arguments)"
                lines.append(
                    f"  - `{call.tool_name}` (argument names: {argument_names})"
                )
        lines.append("")

    lines += [h(2, "Non-Blocking Scored Findings"), ""]
    scored_findings = [
        outcome
        for outcome in data.scenarios
        if outcome.status == "passed" and outcome.severity not in {None, "none"}
    ]
    if scored_findings:
        for outcome in scored_findings:
            lines += [
                h(3, outcome.name),
                f"- Severity: {outcome.severity}",
                f"- Reason: {outcome.evaluation_reason or '(none supplied)'}",
            ]
            lines.extend(f"- Evidence: {item}" for item in outcome.evidence)
            lines.append("")
    else:
        lines += ["No non-blocking scored findings.", ""]

    lines += [h(2, "Failures and Coverage Gaps"), ""]
    errored = [outcome for outcome in data.scenarios if outcome.status == "error"]
    unresolved = [
        outcome
        for outcome in data.scenarios
        if outcome.status in {"breach", "exhausted"}
    ]
    if not errored and not unresolved:
        lines += ["No failures or confirmed-scenario coverage gaps.", ""]
    for outcome in errored:
        lines += [
            (
                f"- Scenario `{outcome.scenario_id}` errored: "
                f"{outcome.evaluation_reason or outcome.breach_reason or 'unknown error'}"
            )
        ]
    for outcome in unresolved:
        lines += [
            (
                f"- Scenario `{outcome.scenario_id}` remains {outcome.status}: "
                f"{outcome.breach_reason or outcome.evaluation_reason or 'unresolved violation'}"
            )
        ]
    lines.append("")

    if standalone:
        lines += [h(2, "Next Steps"), ""]
        if data.ready:
            lines += [
                (
                    "All confirmed scenarios passed. This simulated evaluation is ready for the next "
                    "deployment workflow stage."
                ),
                "",
            ]
        else:
            lines += [
                (
                    "The agent is not ready based on this evaluation. Resolve the failures or unresolved "
                    "scenarios above, then rerun the simulation."
                ),
                "",
            ]

    if data.changes is not None:
        lines += _changes_section(data, h)

    return "\n".join(lines)


def _changes_section(data: EvalReportData, h: Any) -> list[str]:
    names = {outcome.scenario_id: outcome.name for outcome in data.scenarios}
    lines = [h(2, "Changes Applied"), ""]
    if not data.changes:
        return lines + ["No changes applied.", ""]
    for change in data.changes:
        name = names.get(change.scenario_id, "unknown scenario")
        lines += [
            h(3, f"{name} (`{change.scenario_id}`)"),
            f"- Kind: {'prompt patch' if change.kind == 'prompt' else 'code fix'}",
            "- Files: " + ", ".join(f"`{path}`" for path in change.files),
        ]
        if change.symbol:
            lines.append(f"- Symbol: `{change.symbol}`")
        lines += [
            f"- What changed: {change.summary}",
            f"- Why: {change.reason}",
            "",
        ]
    return lines


def write_native_report(
    state: Any,
    output_path: Path,
    json_path: Path | None = None,
    changes: list[ChangeEntry] | None = None,
) -> NativeReportSummary:
    """Render a completed native convergence state without mutating its outcomes."""
    data = build_report_data(state, changes=changes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(data), encoding="utf-8")
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(data.model_dump(mode="json"), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
    return NativeReportSummary(
        ready=data.ready,
        total=data.counts.total,
        passed=data.counts.passed,
        breached=data.counts.breached,
        exhausted=data.counts.exhausted,
        errored=data.counts.errored,
        report_path=str(output_path),
        results_path=str(json_path) if json_path is not None else None,
    )
