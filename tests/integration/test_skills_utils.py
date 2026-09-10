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
    sonnet = cfg["provider"]["datarobot"]["models"][
        "bedrock/anthropic.claude-sonnet-4-6"
    ]
    assert sonnet["options"] == {"reasoningEffort": "max"}
    assert sonnet["limit"] == {"context": 200_000, "output": 64_000}, (
        "the provider config caps output at 8k, which a long JSON reply exceeds"
    )
    assert "meta.llama3-8b-instruct-v1:0" not in json.dumps(cfg)
    assert env["PATH"] == "/bin" and base.get("PATH") == "/bin"

    untouched, none = worker_env(
        ["datarobot/bedrock/meta.llama3-8b-instruct-v1:0"], "max", {"A": "1"}
    )
    assert none == {} and untouched == {"A": "1"}
    off, none = worker_env(["datarobot/anthropic/claude-opus-4-8"], "off", {"A": "1"})
    opus = json.loads(off["OPENCODE_CONFIG_CONTENT"])["provider"]["datarobot"][
        "models"
    ]["anthropic/claude-opus-4-8"]
    assert none == {} and "options" not in opus and opus["limit"]["output"] == 64_000


def test_usage_meter_sums_per_phase_and_total():
    from datarobot_skills_utils.opencode import UsageMeter

    meter = UsageMeter("datarobot/bedrock/anthropic.claude-sonnet-4-6", "max")
    meter.phase = "Layer 2"
    meter.record(
        {
            "input_tokens": 1000,
            "output_tokens": 50,
            "reasoning_tokens": 20,
            "cost": 0.001,
        }
    )
    meter.record({"input_tokens": 500, "output_tokens": 10, "cache_read_tokens": 300})
    meter.phase = "Layer 4"
    meter.record({"input_tokens": 200, "output_tokens": 5})
    meter.record(None)

    snap = meter.snapshot()
    assert (
        snap["model"].endswith("claude-sonnet-4-6")
        and snap["reasoning_effort"] == "max"
    )
    assert list(snap["phases"]) == ["Layer 2", "Layer 4"]
    assert snap["phases"]["Layer 2"] == {
        "calls": 2,
        "input_tokens": 1500,
        "output_tokens": 60,
        "cache_read_tokens": 300,
        "cache_write_tokens": 0,
        "reasoning_tokens": 20,
        "cost": 0.001,
    }
    assert snap["total"]["calls"] == 3 and snap["total"]["input_tokens"] == 1700
    assert snap["total"]["reasoning_tokens"] == 20


def test_parse_events_reports_reasoning_tokens():
    stream = "\n".join(
        [
            json.dumps({"type": "text", "part": {"text": "391"}}),
            json.dumps(
                {
                    "type": "step_finish",
                    "part": {
                        "tokens": {
                            "input": 12,
                            "output": 30,
                            "reasoning": 25,
                            "cache": {"read": 0, "write": 0},
                        },
                        "cost": 0,
                    },
                }
            ),
        ]
    )
    text, meta = parse_events(stream)
    assert (
        text == "391" and meta["reasoning_tokens"] == 25 and meta["output_tokens"] == 30
    )


def test_parse_events_tolerates_null_sub_objects_and_non_object_lines():
    stream = "\n".join(
        [
            json.dumps({"type": "text", "part": None}),
            json.dumps({"type": "step_finish", "part": {"tokens": None}}),
            json.dumps({"type": "step_finish", "part": {"tokens": {"cache": None}}}),
            json.dumps(["not", "an", "event"]),
            json.dumps("nor this"),
            _event("text", {"text": "ok"}),
        ]
    )

    text, meta = parse_events(stream)

    assert text == "ok"
    assert meta["input_tokens"] == 0 and meta["cache_read_tokens"] == 0


def test_run_worker_timeout_keeps_the_prompt_out_of_the_traceback(monkeypatch):
    import subprocess
    import traceback

    from datarobot_skills_utils.opencode import worker

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(worker.subprocess, "run", fake_run)

    # Built at run time so the marker never appears on a source line that the
    # traceback itself would print.
    marker = "PROMPT-BODY-" + "MARKER"
    with pytest.raises(TimeoutError) as info:
        worker.run_worker(marker, "m", isolated_dir="/tmp/x", timeout=1)

    rendered = "".join(traceback.format_exception(info.value))
    assert info.value.__cause__ is None
    assert marker not in rendered
    assert "timed out after 1s" in rendered


def test_server_start_reports_stderr_tail_without_a_pipe(monkeypatch):
    import subprocess

    from datarobot_skills_utils.opencode import server

    seen: dict[str, object] = {}
    real_popen = subprocess.Popen

    def fake_popen(cmd, **kwargs):
        seen["stderr"] = kwargs.get("stderr")
        return real_popen(["sh", "-c", "echo boom >&2; exit 3"], **kwargs)

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    srv = server.OpenCodeServer()

    with pytest.raises(RuntimeError, match="exited 3: boom"):
        srv.start()

    assert seen["stderr"] is not subprocess.PIPE
    assert srv.workdir is None and srv.url is None


def test_bootstrap_copies_stay_identical():
    root = Path(__file__).resolve().parents[2] / "skills"
    copies = sorted(root.rglob("_bootstrap.py"))
    assert len(copies) >= 2, copies
    contents = {p.read_text() for p in copies}
    assert len(contents) == 1, [str(p) for p in copies]


def test_parse_events_names_an_output_cut_at_the_token_limit():
    stream = "\n".join(
        [
            _event("step_start", {}),
            _event(
                "step_finish",
                {
                    "tokens": {"input": 59761, "output": 5179, "reasoning": 3013},
                    "reason": "length",
                },
            ),
        ]
    )
    with pytest.raises(
        ValueError, match="cut at its max output tokens.*5179 output tokens, 3013"
    ):
        parse_events(stream)
