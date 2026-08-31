#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / (
    "skills/datarobot-agent-assist/agent-assist-build/scripts"
)
REHEARSAL_SCRIPT = SCRIPTS_DIR / "rehearsal.py"
sys.path.insert(0, str(SCRIPTS_DIR))

from write_rehearsal_report import (  # noqa: E402
    _summarize_turns,
    default_report_path,
    write_rehearsal_report,
)


@pytest.fixture()
def rehearsal_session(tmp_path: Path) -> Path:
    session_dir = tmp_path / ".datarobot" / "rehearsal" / "20260824T120000Z_abcd1234"
    session_dir.mkdir(parents=True)

    config = {
        "session_id": "20260824T120000Z_abcd1234",
        "started_at": "2026-08-24T12:00:00+00:00",
        "spec_path": str(tmp_path / "agent_spec.md"),
        "requested_model": "bedrock/anthropic.claude-sonnet-4-6",
        "requested_deployment_id": "",
        "model_substituted": False,
        "simulation_substituted": True,
        "target_dir": str(tmp_path),
        "system_prompt": "You are a helpful assistant." * 40,
        "examples": ["Summarize my account activity"],
        "spec_tools": [
            {"function_name": "lookup_account", "inputs": [], "out": []},
            {"function_name": "send_email", "inputs": [], "out": []},
        ],
        "model": {
            "source": "gateway",
            "id": "bedrock/anthropic.claude-sonnet-4-6",
            "api_model": "bedrock/anthropic.claude-sonnet-4-6",
            "deployment_id": "",
            "display": "bedrock/anthropic.claude-sonnet-4-6",
        },
        "simulation_model": {
            "source": "gateway",
            "id": "bedrock/anthropic.claude-sonnet-4-6",
            "api_model": "bedrock/anthropic.claude-sonnet-4-6",
            "deployment_id": "",
            "display": "bedrock/anthropic.claude-sonnet-4-6",
        },
    }
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Look up account 123"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "lookup_account",
                        "arguments": json.dumps({"account_id": "123"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": json.dumps({"status": "active"}),
        },
        {"role": "assistant", "content": "Account 123 is active."},
    ]
    notes = [
        {
            "text": "Agent should confirm account ownership before lookup.",
            "recorded_at": "2026-08-24T12:01:00+00:00",
        }
    ]

    (session_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (session_dir / "messages.json").write_text(json.dumps(messages), encoding="utf-8")
    (session_dir / "notes.json").write_text(json.dumps(notes), encoding="utf-8")
    return session_dir


def test_default_report_path() -> None:
    target = Path("/tmp/project")
    assert (
        default_report_path(target)
        == target / "rehearsal_report" / "rehearsal_report.md"
    )


def test_write_rehearsal_report_summary(
    rehearsal_session: Path, tmp_path: Path
) -> None:
    output_path = default_report_path(tmp_path)
    summary = write_rehearsal_report(
        rehearsal_session,
        output_path,
        transcript_mode="summary",
    )

    assert summary.turn_count == 1
    assert summary.tool_invocation_count == 1
    assert output_path.exists()
    assert Path(summary.archive_path).exists()

    content = output_path.read_text(encoding="utf-8")
    assert "# Dress Rehearsal Report" in content
    assert "Sharing notice" in content
    assert "lookup_account" in content
    assert "`send_email`" in content
    assert "Agent should confirm account ownership" in content
    assert "Account 123 is active." in content
    assert "## Suggested Changes" in content
    assert "eval_report.md" in content


def test_write_rehearsal_report_full_transcript(
    rehearsal_session: Path, tmp_path: Path
) -> None:
    output_path = default_report_path(tmp_path)
    write_rehearsal_report(
        rehearsal_session,
        output_path,
        transcript_mode="full",
    )

    content = output_path.read_text(encoding="utf-8")
    assert "## Conversation Transcript (full)" in content
    assert '"status": "active"' in content


def test_parallel_tool_returns_match_call_order() -> None:
    messages = [
        {"role": "user", "content": "Look up account and send email"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "lookup_account",
                        "arguments": json.dumps({"account_id": "123"}),
                    },
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "send_email",
                        "arguments": json.dumps({"to": "user@example.com"}),
                    },
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": json.dumps({"status": "active"}),
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": json.dumps({"sent": True}),
        },
        {"role": "assistant", "content": "Done."},
    ]

    turns = _summarize_turns(messages)
    assert [name for name, _ in turns[0].tool_returns] == [
        "lookup_account",
        "send_email",
    ]


def test_done_message_generates_report(rehearsal_session: Path, tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REHEARSAL_SCRIPT),
            "--session",
            str(rehearsal_session),
            "DONE",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "report=" in result.stdout

    output_path = default_report_path(tmp_path)
    assert output_path.exists()
    assert "# Dress Rehearsal Report" in output_path.read_text(encoding="utf-8")
