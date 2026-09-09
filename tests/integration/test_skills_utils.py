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


def test_max_reasoning_effort_follows_gateway_accepted_values():
    from datarobot_skills_utils.opencode import max_reasoning_effort, resolve_effort

    assert (
        max_reasoning_effort("datarobot/bedrock/anthropic.claude-sonnet-4-6") == "max"
    )
    assert max_reasoning_effort("datarobot/anthropic/claude-opus-4-8") == "max"
    assert (
        max_reasoning_effort("datarobot/anthropic/claude-haiku-4-5-20251001") == "high"
    )
    assert max_reasoning_effort("datarobot/azure/gpt-5-4-mini-2026-03-17") == "xhigh"
    assert max_reasoning_effort("datarobot/azure/gpt-5-codex-2025-09-15") is None
    assert max_reasoning_effort("datarobot/bedrock/openai.gpt-oss-20b-1:0") == "high"
    assert max_reasoning_effort("datarobot/vertex_ai/gemini-3.5-flash") == "high"
    assert (
        max_reasoning_effort("datarobot/bedrock/meta.llama3-3-70b-instruct-v1:0")
        is None
    )
    assert max_reasoning_effort("datarobot/bedrock/deepseek.r1-v1:0") is None

    model = "datarobot/bedrock/anthropic.claude-sonnet-4-6"
    assert resolve_effort(model, "max") == "max"
    assert resolve_effort(model, "off") is None
    assert resolve_effort(model, None) is None
    assert resolve_effort(model, "low") == "low"
    assert (
        resolve_effort("datarobot/bedrock/meta.llama3-8b-instruct-v1:0", "max") is None
    )


def test_worker_env_injects_reasoning_effort_into_opencode_config():
    from datarobot_skills_utils.opencode import worker_env

    base = {
        "PATH": "/bin",
        "OPENCODE_CONFIG_CONTENT": json.dumps(
            {"provider": {"datarobot": {"options": {"baseURL": "http://x"}}}}
        ),
    }
    env, efforts = worker_env(
        [
            "datarobot/bedrock/anthropic.claude-sonnet-4-6",
            "datarobot/bedrock/meta.llama3-8b-instruct-v1:0",
        ],
        "max",
        base,
    )
    assert efforts == {"datarobot/bedrock/anthropic.claude-sonnet-4-6": "max"}
    cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert cfg["provider"]["datarobot"]["options"]["baseURL"] == "http://x", (
        "existing content is merged, not replaced"
    )
    assert cfg["provider"]["datarobot"]["models"][
        "bedrock/anthropic.claude-sonnet-4-6"
    ]["options"] == {"reasoningEffort": "max"}
    assert "meta.llama3-8b-instruct-v1:0" not in json.dumps(cfg)
    assert env["PATH"] == "/bin" and base.get("PATH") == "/bin"

    untouched, none = worker_env(
        ["datarobot/bedrock/meta.llama3-8b-instruct-v1:0"], "max", {"A": "1"}
    )
    assert none == {} and untouched == {"A": "1"}
    off, _ = worker_env(["datarobot/anthropic/claude-opus-4-8"], "off", {"A": "1"})
    assert "OPENCODE_CONFIG_CONTENT" not in off
