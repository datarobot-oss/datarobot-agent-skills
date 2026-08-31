#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic dress-rehearsal report rendering."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROMPT_PREVIEW_LEN = 500
REHEARSAL_REPORT_DIR = "rehearsal_report"
REHEARSAL_REPORT_FILENAME = "rehearsal_report.md"


@dataclass(frozen=True)
class RehearsalReportSummary:
    report_path: str
    archive_path: str
    turn_count: int
    tool_invocation_count: int


def default_report_path(target_dir: Path) -> Path:
    return target_dir / REHEARSAL_REPORT_DIR / REHEARSAL_REPORT_FILENAME


def load_notes(session_dir: Path) -> list[dict[str, str]]:
    notes_file = session_dir / "notes.json"
    if not notes_file.exists():
        return []
    with notes_file.open() as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _format_model(config: dict[str, Any]) -> str:
    display = config.get("display") or config.get("id") or "unknown"
    source = config.get("source", "gateway")
    if source == "deployed":
        deployment_id = config.get("deployment_id") or config.get("id") or "unknown"
        return f"{display} (deployed: {deployment_id})"
    return f"{display} (gateway)"


def _prompt_preview(system_prompt: str) -> str:
    if len(system_prompt) <= PROMPT_PREVIEW_LEN:
        return system_prompt
    return system_prompt[:PROMPT_PREVIEW_LEN] + "…"


def _parse_tool_call(call: dict[str, Any]) -> tuple[str, list[str]]:
    function = call.get("function") or {}
    name = str(function.get("name") or "unknown")
    raw_args = function.get("arguments") or "{}"
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        return name, []
    if isinstance(args, dict):
        return name, sorted(str(key) for key in args.keys())
    return name, []


@dataclass
class TurnSummary:
    user_message: str
    final_reply: str
    tool_calls: list[tuple[str, list[str]]]
    tool_returns: list[tuple[str, str]]


def _summarize_turns(messages: list[dict[str, Any]]) -> list[TurnSummary]:
    turns: list[TurnSummary] = []
    current: TurnSummary | None = None

    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "user":
            if current is not None:
                turns.append(current)
            current = TurnSummary(
                user_message=str(message.get("content") or ""),
                final_reply="",
                tool_calls=[],
                tool_returns=[],
            )
            continue
        if current is None:
            continue
        if role == "assistant":
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                for call in tool_calls:
                    current.tool_calls.append(_parse_tool_call(call))
            content = message.get("content")
            if content:
                current.final_reply = str(content)
            continue
        if role == "tool":
            content = str(message.get("content") or "")
            tool_name = "unknown"
            return_index = len(current.tool_returns)
            if return_index < len(current.tool_calls):
                tool_name = current.tool_calls[return_index][0]
            current.tool_returns.append((tool_name, content))

    if current is not None:
        turns.append(current)
    return turns


def _tool_activity(turns: list[TurnSummary]) -> list[tuple[str, int, list[str]]]:
    counts: Counter[str] = Counter()
    arg_keys: dict[str, set[str]] = {}
    for turn in turns:
        for name, keys in turn.tool_calls:
            counts[name] += 1
            arg_keys.setdefault(name, set()).update(keys)
    return [
        (name, counts[name], sorted(arg_keys.get(name, set())))
        for name in sorted(counts)
    ]


def _render_conversation_summary(turns: list[TurnSummary]) -> list[str]:
    lines: list[str] = []
    for index, turn in enumerate(turns, start=1):
        lines.extend(
            [
                f"### Turn {index}",
                "",
                "**User**",
                "",
                turn.user_message or "(empty)",
                "",
            ]
        )
        if turn.tool_calls:
            tool_names = ", ".join(name for name, _ in turn.tool_calls)
            lines.extend([f"**Tools invoked:** {tool_names}", ""])
        lines.extend(
            [
                "**Agent (final reply)**",
                "",
                turn.final_reply or "(no final reply recorded)",
                "",
            ]
        )
    if not turns:
        lines.append("_No user turns were recorded._")
        lines.append("")
    return lines


def _render_conversation_full(turns: list[TurnSummary]) -> list[str]:
    lines: list[str] = []
    for index, turn in enumerate(turns, start=1):
        lines.extend(
            [
                f"### Turn {index}",
                "",
                "**User**",
                "",
                turn.user_message or "(empty)",
                "",
            ]
        )
        for call_index, (name, keys) in enumerate(turn.tool_calls, start=1):
            key_text = ", ".join(keys) if keys else "(none)"
            lines.extend(
                [
                    f"**Tool call {call_index}: `{name}`**",
                    "",
                    f"- Argument keys: {key_text}",
                    "",
                ]
            )
        for call_index, (name, payload) in enumerate(turn.tool_returns, start=1):
            lines.extend(
                [
                    f"**Simulated return {call_index}: `{name}`**",
                    "",
                    "```json",
                    payload,
                    "```",
                    "",
                ]
            )
        lines.extend(
            [
                "**Agent (final reply)**",
                "",
                turn.final_reply or "(no final reply recorded)",
                "",
            ]
        )
    if not turns:
        lines.append("_No user turns were recorded._")
        lines.append("")
    return lines


def write_rehearsal_report(
    session_dir: Path,
    output_path: Path,
    *,
    transcript_mode: str = "summary",
) -> RehearsalReportSummary:
    """Render a completed rehearsal session to Markdown."""
    config_file = session_dir / "config.json"
    messages_file = session_dir / "messages.json"
    if not config_file.exists() or not messages_file.exists():
        raise FileNotFoundError(
            f"Session not found at {session_dir}. Run rehearsal --init first."
        )

    with config_file.open() as handle:
        config = json.load(handle)
    with messages_file.open() as handle:
        messages = json.load(handle)

    target_dir = Path(str(config.get("target_dir") or ".")).resolve()
    spec_path = str(config.get("spec_path") or "agent_spec.md")
    started_at = str(config.get("started_at") or "unknown")
    ended_at = datetime.now(timezone.utc).isoformat()
    config["ended_at"] = ended_at
    tmp_config = config_file.with_suffix(".json.tmp")
    with tmp_config.open("w") as handle:
        json.dump(config, handle)
    tmp_config.replace(config_file)

    system_prompt = str(config.get("system_prompt") or "")
    examples = config.get("examples") or []
    spec_tools = config.get("spec_tools") or []
    agent_model = config.get("model") or {}
    simulation_model = config.get("simulation_model") or {}
    requested_model = str(config.get("requested_model") or "unknown")
    requested_deployment_id = str(config.get("requested_deployment_id") or "")
    model_substituted = bool(config.get("model_substituted"))
    simulation_substituted = bool(config.get("simulation_substituted"))

    turns = _summarize_turns(messages)
    tool_activity = _tool_activity(turns)
    defined_tools = [str(tool.get("function_name") or "unknown") for tool in spec_tools]
    exercised_tools = sorted({name for name, _, _ in tool_activity})
    unused_tools = sorted(set(defined_tools) - set(exercised_tools))

    notes = load_notes(session_dir)
    generated_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        "# Dress Rehearsal Report",
        "",
        "> **Sharing notice:** This report may contain test inputs you typed during "
        "rehearsal. Review before sharing externally.",
        "",
        "## Audit Metadata",
        f"- Spec file: `{spec_path}`",
        f"- Project directory: `{target_dir}`",
        f"- Session ID: `{config.get('session_id', session_dir.name)}`",
        f"- Session directory: `{session_dir}`",
        f"- Session started: {started_at}",
        f"- Session ended: {ended_at}",
        f"- Report generated: {generated_at}",
        f"- Transcript mode: {transcript_mode}",
        f"- Agent model: {_format_model(agent_model)}",
        f"- Simulation model: {_format_model(simulation_model)}",
        f"- Requested model: `{requested_deployment_id or requested_model}`",
        f"- Agent model substituted: {'yes' if model_substituted else 'no'}",
        f"- Simulation model substituted: {'yes' if simulation_substituted else 'no'}",
        f"- User turns: {len(turns)}",
        f"- Tool invocations: {sum(count for _, count, _ in tool_activity)}",
        "",
        "## Agent Design Snapshot",
        f"- Tools defined: {len(defined_tools)}",
        f"- Tools exercised: {len(exercised_tools)}",
        *(
            [
                f"- Tools not exercised: {', '.join(f'`{name}`' for name in unused_tools)}"
            ]
            if unused_tools
            else []
        ),
        "",
        "**System prompt preview**",
        "",
        "```",
        _prompt_preview(system_prompt),
        "```",
        "",
        f"Full prompt: see `{spec_path}`.",
        "",
        "**Example prompts in spec**",
        "",
    ]

    if examples:
        lines.extend(f"- {example}" for example in examples)
    else:
        lines.append("- (none)")
    lines.append("")

    lines.extend(["## Session Notes", ""])
    if notes:
        for entry in notes:
            text = str(entry.get("text") or "").strip()
            recorded_at = str(entry.get("recorded_at") or "unknown")
            if text:
                lines.append(f"- ({recorded_at}) {text}")
    else:
        lines.append("_No NOTE: entries were recorded._")
    lines.append("")

    if transcript_mode == "full":
        lines.extend(["## Conversation Transcript (full)", ""])
        lines.extend(_render_conversation_full(turns))
    else:
        lines.extend(["## Conversation Summary", ""])
        lines.extend(_render_conversation_summary(turns))

    lines.extend(["## Tool Activity", ""])
    if tool_activity:
        for name, count, keys in tool_activity:
            key_text = ", ".join(f"`{key}`" for key in keys) if keys else "(none)"
            lines.append(
                f"- `{name}`: {count} invocation(s); argument keys: {key_text}"
            )
    else:
        lines.append("_No tool calls were recorded._")
    lines.append("")

    lines.extend(
        [
            "## Limitations",
            "- Tool return values were simulated; no real external APIs were called.",
            "- Agent responses used the rehearsal harness, not your deployed application.",
            "- This report validates design choices before coding; it is not a production readiness sign-off.",
            "- After coding, run swarm battle-testing to produce `eval_report.md`.",
            "",
            "## Suggested Changes",
            "",
            "_Pending agent review — append actionable recommendations here._",
            "",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    archive_path = session_dir / REHEARSAL_REPORT_FILENAME
    archive_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")

    return RehearsalReportSummary(
        report_path=str(output_path),
        archive_path=str(archive_path),
        turn_count=len(turns),
        tool_invocation_count=sum(count for _, count, _ in tool_activity),
    )
