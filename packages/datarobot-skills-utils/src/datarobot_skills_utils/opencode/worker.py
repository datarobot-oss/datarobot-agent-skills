# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""One-shot `dr opencode run` worker invocations."""

from __future__ import annotations

import subprocess

from .events import parse_events

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


def build_run_command(
    message: str,
    model: str,
    server_url: str | None = None,
    isolated_dir: str | None = None,
) -> list[str]:
    """The `dr opencode run` argv for one worker call.

    Give exactly one of `server_url` (own session on a shared server) or
    `isolated_dir` (standalone process, no caller project context).
    """
    cmd = [
        "dr",
        "--skip-plugin-update-check",
        "--plugin-discovery-timeout",
        "30s",
        "opencode",
        "run",
        "--format",
        "json",
        "--model",
        model,
    ]
    if server_url:
        cmd += ["--attach", server_url]
    elif isolated_dir:
        cmd += ["--dir", isolated_dir]
    cmd += ["--pure", message]
    return cmd


def run_worker(
    message: str,
    model: str,
    server_url: str | None = None,
    isolated_dir: str | None = None,
    cwd: str | None = None,
    timeout: int = 120,
    attempts: int = 2,
) -> tuple[str, dict[str, object]]:
    """Run one worker completion; returns (text, token_meta).

    Raises RuntimeError on a non-zero exit; retries an empty event stream up
    to `attempts` times (a transient session death) before raising ValueError.
    """
    cmd = build_run_command(
        sanitize_message(f"{WORKER_PREAMBLE}{message}"),
        model,
        server_url=server_url,
        isolated_dir=isolated_dir,
    )
    last_error: Exception | None = None
    for _ in range(max(1, attempts)):
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[-500:]
            raise RuntimeError(f"dr opencode run exited {result.returncode}: {detail}")
        try:
            return parse_events(result.stdout)
        except ValueError as e:
            detail = (result.stderr or result.stdout or "").strip()[:300]
            last_error = ValueError(f"{e} (output head: {detail!r})")
    assert last_error is not None
    raise last_error
