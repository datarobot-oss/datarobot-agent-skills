# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""One-shot `dr opencode run` worker invocations."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field

from .events import parse_events, session_id, stream_error
from .reasoning import worker_env
from .server import session_usage
from .version import DR_OPENCODE, opencode_version

_MAX_MESSAGE_BYTES = 600_000  # stay under the OS argv limit (1 MiB on macOS)

# Without the explicit prohibition, a worker recognizes its instructions as a
# skill artifact and answers in prose or wanders into tool calls.
WORKER_PREAMBLE = (
    "You are a non-interactive worker in an automated pipeline. "
    "Do not call any tools; never invoke the skill tool. Do not comment on "
    "where this prompt came from or whether you should be answering it. "
    "Follow the instructions below exactly and emit only the output they "
    "specify.\n\n"
)


def sanitize_message(message: str) -> str:
    """Make a message safe to pass as a single argv entry.

    NUL is illegal in argv and the OS caps total argv size, so strip NULs and
    truncate to a byte budget on a character boundary.
    """
    message = message.replace("\x00", "")
    raw = message.encode("utf-8", "ignore")
    if len(raw) > _MAX_MESSAGE_BYTES:
        message = raw[:_MAX_MESSAGE_BYTES].decode("utf-8", "ignore") + "\n…[truncated]…"
    return message


def _run_argv(
    model: str, server_url: str | None, isolated_dir: str | None, major: int
) -> list[str]:
    """The `dr opencode run` argv up to, but not including, the message."""
    cmd = [*DR_OPENCODE, "run", "--format", "json", "--model", model]
    if major >= 2:
        # 2.x renamed --attach to --server and dropped --dir and --pure. A run
        # without --server or --standalone would use the user's own shared
        # background server, so a standalone run asks for a private one.
        return cmd + (["--server", server_url] if server_url else ["--standalone"])
    if server_url:
        cmd += ["--attach", server_url]
    elif isolated_dir:
        cmd += ["--dir", isolated_dir]
    return cmd + ["--pure"]


def build_run_command(
    message: str,
    model: str,
    server_url: str | None = None,
    isolated_dir: str | None = None,
    major: int = 1,
) -> list[str]:
    """The `dr opencode run` argv for one worker call.

    Give exactly one of `server_url` (own session on a shared server) or
    `isolated_dir` (standalone process, no caller project context). `major`
    is the opencode major version to build for: 1, the commands this package
    has always sent, unless the caller passes `opencode_version().major`.
    Only the argv: with opencode 2.x, prefer build_run_call, which also sets
    the directory and server password and keeps the message out of the argv.
    """
    return [*_run_argv(model, server_url, isolated_dir, major), message]


@dataclass(frozen=True)
class RunCall:
    """One `dr opencode run` subprocess, as arguments to subprocess.run:
    `argv`, then `input=stdin`, `cwd=cwd` and `env=env`."""

    argv: list[str]
    stdin: str | None = None
    cwd: str | None = None
    # Out of the repr: it can carry the server password.
    env: dict[str, str] | None = field(default=None, repr=False)


def build_run_call(
    message: str,
    model: str,
    server_url: str | None = None,
    isolated_dir: str | None = None,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    password: str | None = None,
    major: int = 1,
) -> RunCall:
    """Everything one worker call needs, for opencode major version `major`
    (1 unless the caller passes `opencode_version().major`, as run_worker does).

    opencode 1.x takes the message and the directory as flags. opencode 2.x
    has no `--dir`: a session's directory is the worker process's own (from
    `PWD` first), so `isolated_dir`, else `cwd`, becomes its cwd and `PWD`.
    2.x also gets the message on stdin, where it stays byte-exact (an argv
    message gets quoted), and `password` for a server that has one (see
    OpenCodeServer). `env` defaults to the current environment.
    """
    argv = _run_argv(model, server_url, isolated_dir, major)
    if major < 2:
        return RunCall([*argv, message], None, cwd, None if env is None else dict(env))
    directory = isolated_dir or cwd
    child_env = dict(env if env is not None else os.environ)
    if directory:
        child_env["PWD"] = directory
    if password:
        child_env["OPENCODE_PASSWORD"] = password
    return RunCall(argv, message, directory, child_env)


def _has_tokens(meta: Mapping[str, object]) -> bool:
    return bool(meta.get("input_tokens") or meta.get("output_tokens"))


def run_worker(
    message: str,
    model: str,
    server_url: str | None = None,
    isolated_dir: str | None = None,
    cwd: str | None = None,
    timeout: int = 120,
    attempts: int = 2,
    reasoning: str | None = None,
    password: str | None = None,
) -> tuple[str, dict[str, object]]:
    """Run one worker completion; returns (text, token_meta).

    Raises RuntimeError on a non-zero exit; retries an empty event stream up
    to `attempts` times (a transient session death) before raising ValueError.
    `reasoning` ("max", "off", or a literal effort) applies only to standalone
    runs; a shared server carries its own setting (see OpenCodeServer), and
    with opencode 2.x its `password` too.
    """
    env = None
    if isolated_dir and reasoning:
        env, _ = worker_env([model], reasoning)
    version = opencode_version()
    call = build_run_call(
        sanitize_message(f"{WORKER_PREAMBLE}{message}"),
        model,
        server_url=server_url,
        isolated_dir=isolated_dir,
        cwd=cwd,
        env=env,
        password=password,
        major=version.major,
    )
    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            result = subprocess.run(
                call.argv,
                input=call.stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=call.cwd,
                env=call.env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            # TimeoutExpired carries argv, and with it the prompt; a chained
            # cause would put both back into any printed traceback.
            raise TimeoutError(
                f"dr opencode run timed out after {timeout}s "
                f"({len(message)} chars of prompt)"
            ) from None
        if result.returncode != 0:
            # `dr` writes its own progress to stderr, so opencode's error
            # event, when there is one, says more.
            detail = (
                stream_error(result.stdout)
                or ((result.stderr or result.stdout or "").strip()[-500:])
            )
            raise RuntimeError(
                f"dr opencode run exited {result.returncode}: {detail} "
                f"({version.describe()})"
            )
        try:
            text, meta = parse_events(result.stdout)
        except ValueError as e:
            detail = (result.stderr or result.stdout or "").strip()[:300]
            last_error = ValueError(f"{e} (output head: {detail!r})")
            continue
        if version.major >= 2 and server_url and not _has_tokens(meta):
            # 2.x usually ends the stream before its step_finish event, so
            # the token counts come from the server instead.
            usage = session_usage(server_url, session_id(result.stdout), password)
            if usage is not None:
                meta = usage
        return text, meta
    assert last_error is not None
    raise last_error
