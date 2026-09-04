# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared datarobot-skills-utils package (pure functions)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / "packages"
        / "datarobot-skills-utils"
        / "src"
    ),
)

from datarobot_skills_utils.opencode import (  # noqa: E402
    WORKER_PREAMBLE,
    build_run_command,
    parse_events,
    sanitize_message,
    strip_code_fences,
)


def _event(kind: str, part: dict) -> str:
    return json.dumps({"type": kind, "part": part})


def test_parse_events_concatenates_text_and_accumulates_meta():
    stdout = "\n".join(
        [
            _event("step_start", {}),
            _event("text", {"text": '{"a": '}),
            _event("text", {"text": "1}"}),
            _event(
                "step_finish",
                {
                    "tokens": {
                        "input": 10,
                        "output": 5,
                        "cache": {"read": 2, "write": 1},
                    },
                    "cost": 0.5,
                },
            ),
            "not json at all",
        ]
    )
    text, meta = parse_events(stdout)
    assert text == '{"a": 1}'
    assert meta["input_tokens"] == 10
    assert meta["output_tokens"] == 5
    assert meta["cache_read_tokens"] == 2
    assert meta["cost"] == 0.5


def test_parse_events_raises_on_empty_stream():
    with pytest.raises(ValueError, match="no text events"):
        parse_events(_event("step_start", {}))


def test_strip_code_fences():
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fences("plain") == "plain"
    with pytest.raises(ValueError, match="empty code block"):
        strip_code_fences("```\n```")


def test_sanitize_message_strips_nul_and_caps_bytes():
    assert sanitize_message("a\x00b") == "ab"
    big = "é" * 700_000
    out = sanitize_message(big)
    assert out.endswith("…[truncated]…")
    assert len(out.encode("utf-8")) < 700_000


def test_build_run_command_attach_vs_isolated():
    attach = build_run_command("msg", "m", server_url="http://x")
    assert "--attach" in attach and "--dir" not in attach
    assert attach[-1] == "msg" and attach[-2] == "--pure"
    isolated = build_run_command("msg", "m", isolated_dir="/tmp/x")
    assert "--dir" in isolated and "--attach" not in isolated


def test_preamble_forbids_tools():
    assert "never invoke the skill tool" in WORKER_PREAMBLE


def test_terminate_process_tree_kills_grandchildren() -> None:
    import os
    import subprocess
    import time

    from datarobot_skills_utils.opencode.server import terminate_process_tree

    proc = subprocess.Popen(
        ["sh", "-c", "sleep 300 & sleep 300 & wait"], start_new_session=True
    )
    time.sleep(0.3)
    pgid = os.getpgid(proc.pid)

    terminate_process_tree(proc, timeout=2)

    with pytest.raises(ProcessLookupError):
        os.killpg(pgid, 0)
