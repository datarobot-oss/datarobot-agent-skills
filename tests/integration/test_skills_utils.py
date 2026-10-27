# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the shared datarobot-skills-utils package (pure functions)."""

import base64
import http.server
import json
import sys
import threading
from pathlib import Path
from subprocess import CompletedProcess, Popen
from typing import ClassVar

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

from datarobot_skills_utils.opencode import (
    WORKER_PREAMBLE,
    OpenCodeVersion,
    build_run_call,
    build_run_command,
    parse_events,
    sanitize_message,
    strip_code_fences,
)
from datarobot_skills_utils.opencode import server as opencode_server
from datarobot_skills_utils.opencode import version as opencode_version_module
from datarobot_skills_utils.opencode import worker as opencode_worker
from datarobot_skills_utils.opencode.events import session_id, stream_error
from datarobot_skills_utils.opencode.version import parse_version

V1 = OpenCodeVersion((1, 17, 11), "1.17.11")
V2 = OpenCodeVersion((2, 1, 3), "opencode v2.1.3")
PASSWORD = "test-server-password"
RUN_PREFIX = [
    "dr",
    "--skip-plugin-update-check",
    "--plugin-discovery-timeout",
    "30s",
    "opencode",
    "run",
    "--format",
    "json",
    "--model",
    "m",
]


@pytest.fixture(autouse=True)
def _opencode_1x(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the detected opencode to 1.x so no test runs the real `dr`; the
    2.x tests override it."""
    monkeypatch.setattr(opencode_worker, "opencode_version", lambda: V1)
    monkeypatch.setattr(opencode_server, "opencode_version", lambda: V1)


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


def test_bootstrap_pin_matches_package_version():
    from datarobot_skills_utils import __version__

    root = Path(__file__).resolve().parents[2]
    expected = f'SKILLS_UTILS_REQUIREMENT = "datarobot-skills-utils=={__version__}"'
    for copy in sorted((root / "skills").rglob("_bootstrap.py")):
        assert expected in copy.read_text(), str(copy)


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


# Real `dr opencode run --format json` output from opencode 2.1.3, IDs replaced.
# `dr` prints a banner line of its own first, and 2.x ended both streams before
# any step_finish event.
STREAM_2X = (
    "\N{ELECTRIC PLUG} Running plugin: opencode\n"
    '{"type":"step_start","timestamp":1793114244856,"sessionID":"ses_test","part":{"id":"prt_1","sessionID":"ses_test","messageID":"msg_test","type":"step-start","snapshot":"4b825dc642cb6eb9a060e54bf8d69288fbee4904"}}\n'
    '{"type":"text","timestamp":1793114245529,"sessionID":"ses_test","part":{"id":"prt_2","sessionID":"ses_test","messageID":"msg_test","type":"text","text":"```json\\n{\\"answer\\": 391, \\"why\\": \\"17 * 23\\"}\\n```","time":{"start":1793114245354,"end":1793114245529}}}\n'
)
ERROR_2X = (
    "\N{ELECTRIC PLUG} Running plugin: opencode\n"
    '{"type":"error","timestamp":1793114240082,"sessionID":"ses_test","error":{"type":"provider.no-route","message":"Model unavailable: datarobot/anthropic/claude-sonnet-4-6"}}\n'
)
# opencode 1.17.11 writes the same envelope (cli/cmd/run.ts, emit()), closes
# each step with step_finish, and shapes errors as {name, data: {message}}.
STREAM_1X = "\n".join(
    json.dumps(event)
    for event in [
        {"type": "step_start", "timestamp": 1, "sessionID": "ses_test", "part": {}},
        {
            "type": "text",
            "timestamp": 2,
            "sessionID": "ses_test",
            "part": {"type": "text", "text": "ok", "time": {"start": 1, "end": 2}},
        },
        {
            "type": "step_finish",
            "timestamp": 3,
            "sessionID": "ses_test",
            "part": {
                "type": "step-finish",
                "reason": "stop",
                "cost": 0,
                "tokens": {
                    "input": 12449,
                    "output": 4,
                    "reasoning": 0,
                    "cache": {"read": 0, "write": 0},
                },
            },
        },
    ]
)
# A real assistant message from an opencode 2.1.3 server's
# GET /api/session/<id>/message?type=assistant, IDs replaced and the
# provider's own response IDs left out.
MESSAGES_2X = {
    "data": [
        {
            "agent": "build",
            "content": [{"type": "text", "text": "ok"}],
            "cost": 0,
            "finish": "stop",
            "id": "msg_test",
            "model": {
                "id": "anthropic/claude-sonnet-4-6",
                "providerID": "datarobot-responses",
                "variant": "default",
            },
            "snapshot": {
                "start": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                "end": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                "files": [],
            },
            "time": {
                "created": 1793115343941,
                "streamed": 1793115346116,
                "completed": 1793115346125,
            },
            "tokens": {
                "input": 12449,
                "output": 4,
                "reasoning": 0,
                "cache": {"read": 0, "write": 0},
            },
            "type": "assistant",
        }
    ],
    "cursor": {},
}
USAGE = {
    "input_tokens": 12449,
    "output_tokens": 4,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
    "reasoning_tokens": 0,
    "cost": 0.0,
}


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("1.17.11\n", (1, 17, 11)),
        ("\N{ELECTRIC PLUG} Running plugin: opencode\n1.17.11\n", (1, 17, 11)),
        ("\N{ELECTRIC PLUG} Running plugin: opencode\nopencode v2.1.3\n", (2, 1, 3)),
        ("opencode v2.1.3-beta.1", (2, 1, 3)),
        ("v3.0.0", (3, 0, 0)),
        ("", None),
        ("garbage\n", None),
        ("1.17\n", None),
        ('dr 0.1.14\nError: unknown command "opencode"\n', None),
    ],
)
def test_parse_version_reads_both_formats_and_rejects_garbage(output, expected):
    assert parse_version(output) == expected


def test_opencode_version_asks_dr_once_per_process(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        stdout = "\N{ELECTRIC PLUG} Running plugin: opencode\nopencode v2.1.3\n"
        return CompletedProcess(cmd, 0, stdout=stdout, stderr="Fetching... Done.\n")

    detect = opencode_version_module.opencode_version
    detect.cache_clear()
    monkeypatch.setattr(opencode_version_module.subprocess, "run", fake_run)
    try:
        first, second = detect(), detect()
    finally:
        detect.cache_clear()

    assert calls == [[*RUN_PREFIX[:5], "--version"]]
    assert first is second and first.major == 2
    assert first.describe() == "opencode 2.1.3"


def test_unreadable_opencode_version_keeps_1x_and_says_what_to_do(monkeypatch):
    def missing(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "dr")

    def unknown_format(cmd, **kwargs):
        stdout = "\N{ELECTRIC PLUG} Running plugin: opencode\nOpenCode build 7\n"
        return CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    detect = opencode_version_module.opencode_version
    found = []
    for fake in (missing, unknown_format):
        detect.cache_clear()
        monkeypatch.setattr(opencode_version_module.subprocess, "run", fake)
        try:
            found.append(detect())
        finally:
            detect.cache_clear()

    for version in found:
        assert version.release is None and version.major == 1
        assert "dr opencode --version" in version.describe()
        assert "opencode 1.x and 2.x" in version.describe()
    assert "FileNotFoundError" in found[0].output
    assert found[1].output == "OpenCode build 7"


def test_build_run_command_for_1x_is_unchanged():
    assert build_run_command("msg", "m", server_url="http://x", major=1) == [
        *RUN_PREFIX,
        "--attach",
        "http://x",
        "--pure",
        "msg",
    ]
    assert build_run_command("msg", "m", isolated_dir="/tmp/x", major=1) == [
        *RUN_PREFIX,
        "--dir",
        "/tmp/x",
        "--pure",
        "msg",
    ]
    assert build_run_command("msg", "m", major=1) == [*RUN_PREFIX, "--pure", "msg"]
    # The detected version is used by default (pinned to 1.x in these tests).
    assert build_run_command("msg", "m", server_url="http://x") == (
        build_run_command("msg", "m", server_url="http://x", major=1)
    )


def test_build_run_command_for_2x_uses_server_or_standalone():
    assert build_run_command("msg", "m", server_url="http://x", major=2) == [
        *RUN_PREFIX,
        "--server",
        "http://x",
        "msg",
    ]
    for kwargs in ({"isolated_dir": "/tmp/x"}, {}):
        assert build_run_command("msg", "m", major=2, **kwargs) == [
            *RUN_PREFIX,
            "--standalone",
            "msg",
        ], "a 2.x run without --server would use the user's background server"


def test_build_run_call_for_2x_sets_directory_password_and_stdin():
    base_env = {"PATH": "/bin"}
    call = build_run_call(
        "msg",
        "m",
        server_url="http://x",
        cwd="/tmp/work",
        env=base_env,
        password=PASSWORD,
        major=2,
    )
    assert call.argv == [*RUN_PREFIX, "--server", "http://x"]
    assert call.stdin == "msg" and call.cwd == "/tmp/work"
    assert call.env == {
        "PATH": "/bin",
        "PWD": "/tmp/work",
        "OPENCODE_PASSWORD": PASSWORD,
    }
    assert base_env == {"PATH": "/bin"}, "the caller's mapping is copied"
    assert PASSWORD not in repr(call)

    standalone = build_run_call(
        "msg", "m", isolated_dir="/tmp/iso", cwd="/tmp/other", env=base_env, major=2
    )
    assert standalone.argv == [*RUN_PREFIX, "--standalone"]
    assert standalone.cwd == "/tmp/iso"
    assert standalone.env == {"PATH": "/bin", "PWD": "/tmp/iso"}


def test_build_run_call_for_1x_passes_cwd_and_env_through():
    call = build_run_call(
        "msg", "m", server_url="http://x", cwd="/tmp/work", password=PASSWORD, major=1
    )
    assert call.argv == build_run_command("msg", "m", server_url="http://x", major=1)
    assert call.stdin is None and call.cwd == "/tmp/work" and call.env is None

    env = {"A": "1"}
    isolated = build_run_call("msg", "m", isolated_dir="/tmp/x", env=env, major=1)
    assert isolated.cwd is None and isolated.env == env


def test_parse_events_reads_1x_and_2x_streams():
    text, meta = parse_events(STREAM_2X)
    assert strip_code_fences(text) == '{"answer": 391, "why": "17 * 23"}'
    assert meta["input_tokens"] == 0, "2.x left step_finish out of this stream"
    assert session_id(STREAM_2X) == "ses_test"

    text, meta = parse_events(STREAM_1X)
    assert text == "ok"
    assert meta == USAGE, "1.x step_finish parts and 2.x messages sum alike"
    assert session_id(STREAM_1X) == "ses_test"


def test_parse_events_reports_opencode_error_events():
    with pytest.raises(
        ValueError,
        match="opencode reported an error: Model unavailable: datarobot/anthropic",
    ):
        parse_events(ERROR_2X)

    error_1x = {"name": "APIError", "data": {"message": "Bad Request"}}
    named_only = {"name": "UnknownError", "data": {}}
    stream = "\n".join(
        json.dumps({"type": "error", "sessionID": "ses_test", "error": error})
        for error in (error_1x, named_only)
    )
    assert stream_error(stream) == "Bad Request; UnknownError"
    assert stream_error(STREAM_2X) == ""


class _MessagesHandler(http.server.BaseHTTPRequestHandler):
    """Answers like an opencode 2.x server: basic auth or 401."""

    paths: ClassVar[list[str]] = []

    def do_GET(self) -> None:
        self.paths.append(self.path)
        token = base64.b64encode(f"opencode:{PASSWORD}".encode()).decode()
        if self.headers.get("Authorization") != f"Basic {token}":
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(MESSAGES_2X).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_session_usage_reads_a_2x_server_with_its_password():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MessagesHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    _MessagesHandler.paths.clear()
    try:
        usage = opencode_server.session_usage(url, "ses_test", PASSWORD)
        refused = opencode_server.session_usage(url, "ses_test", "wrong")
        unknown = opencode_server.session_usage(url, None, PASSWORD)
    finally:
        httpd.shutdown()
        httpd.server_close()

    assert usage == USAGE
    assert refused is None and unknown is None, "usage is optional: no raise"
    assert _MessagesHandler.paths[0] == (
        "/api/session/ses_test/message?type=assistant&limit=200"
    )


def test_run_worker_2x_sends_stdin_and_password_and_reads_usage(monkeypatch):
    monkeypatch.setattr(opencode_worker, "opencode_version", lambda: V2)
    seen: dict[str, object] = {}
    asked = []

    def fake_run(cmd, **kwargs):
        seen.update(kwargs, cmd=cmd)
        return CompletedProcess(cmd, 0, stdout=STREAM_2X, stderr="")

    def fake_usage(url, session, password):
        asked.append((url, session, password))
        return dict(USAGE)

    monkeypatch.setattr(opencode_worker.subprocess, "run", fake_run)
    monkeypatch.setattr(opencode_worker, "session_usage", fake_usage)

    text, meta = opencode_worker.run_worker(
        "Do it.", "m", server_url="http://x", cwd="/tmp/work", password=PASSWORD
    )

    assert seen["cmd"] == [*RUN_PREFIX, "--server", "http://x"]
    assert seen["input"] == f"{WORKER_PREAMBLE}Do it."
    assert seen["cwd"] == "/tmp/work"
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["PWD"] == "/tmp/work" and env["OPENCODE_PASSWORD"] == PASSWORD
    assert asked == [("http://x", "ses_test", PASSWORD)]
    assert text.startswith("```json") and meta == USAGE


def test_run_worker_failure_names_opencodes_error_and_version(monkeypatch):
    monkeypatch.setattr(opencode_worker, "opencode_version", lambda: V2)

    def fake_run(cmd, **kwargs):
        stderr = "Fetching models... Done.\nerror: opencode exited: exit status 1\n"
        return CompletedProcess(cmd, 1, stdout=ERROR_2X, stderr=stderr)

    monkeypatch.setattr(opencode_worker.subprocess, "run", fake_run)

    with pytest.raises(
        RuntimeError,
        match=r"exited 1: Model unavailable: \S+ \(opencode 2\.1\.3\)",
    ):
        opencode_worker.run_worker("Say hi.", "m", server_url="http://x")


def _serve_stand_in(monkeypatch):
    """Run `sleep` in place of `dr opencode serve` and record what it got."""
    seen: dict[str, object] = {}
    probes = []

    def fake_popen(cmd, **kwargs):
        if cmd[:3] != ["dr", "opencode", "serve"]:
            return Popen(cmd, **kwargs)
        seen.update(kwargs, cmd=cmd)
        return Popen(["sleep", "30"], **kwargs)

    def fake_get(url, password=None, timeout=10):
        probes.append((url, password))
        return b"{}"

    monkeypatch.setattr(opencode_server.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(opencode_server, "_get", fake_get)
    return seen, probes


def test_server_for_2x_sets_a_password_and_probes_the_api(monkeypatch):
    monkeypatch.setattr(opencode_server, "opencode_version", lambda: V2)
    seen, probes = _serve_stand_in(monkeypatch)
    srv = opencode_server.OpenCodeServer()
    try:
        url = srv.start()
        password, workdir = srv.password, srv.workdir
    finally:
        srv.stop()

    assert seen["cmd"][:4] == ["dr", "opencode", "serve", "--port"]
    env = seen["env"]
    assert isinstance(env, dict) and password
    assert env["OPENCODE_PASSWORD"] == password
    assert env["PWD"] == workdir == seen["cwd"]
    assert probes == [(f"{url}/api/info", password)]
    assert srv.password is None and srv.url is None


def test_server_for_1x_keeps_its_command_env_and_health_route(monkeypatch):
    seen, probes = _serve_stand_in(monkeypatch)
    srv = opencode_server.OpenCodeServer()
    try:
        url = srv.start()
        password = srv.password
    finally:
        srv.stop()

    cmd = seen["cmd"]
    assert isinstance(cmd, list)
    assert cmd == ["dr", "opencode", "serve", "--port", cmd[4]]
    assert seen["env"] is srv.env and password is None
    assert probes == [(f"{url}/global/health", None)]
