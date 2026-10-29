# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLMClient adapter over the datarobot-skills-utils opencode runtime."""

from __future__ import annotations

import subprocess

from ._bootstrap import ensure_skills_utils
from .settings import DEFAULT_MODEL, DEFAULT_WORKER_TIMEOUT

ensure_skills_utils()

from datarobot_skills_utils.opencode import (
    OpenCodeServer,
    UsageMeter,
    dr_available,
    run_worker,
)
from datarobot_skills_utils.opencode.version import DR_OPENCODE

__all__ = [
    "OpenCodeServer",
    "OpenCodeWorkerClient",
    "dr_available",
    "list_models",
    "pick_model",
]


def list_models() -> list[str]:
    """The models `dr opencode` offers, or none without the `dr` CLI."""
    if not dr_available():
        return []
    listing = subprocess.run(
        [*DR_OPENCODE, "models"],
        capture_output=True,
        text=True,
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=120,
        check=False,
    ).stdout
    return [line.strip() for line in listing.splitlines()]


def pick_model(models: list[str]) -> str:
    """The default model if listed, else any DataRobot sonnet, else the default."""
    suffix = "/" + DEFAULT_MODEL.removeprefix("datarobot/")
    for match in (lambda m: m.endswith(suffix), lambda m: "sonnet" in m):
        found = next(
            (m for m in models if m.startswith("datarobot") and match(m)), None
        )
        if found:
            return found
    return DEFAULT_MODEL


class OpenCodeWorkerClient:
    """LLMClient backed by `dr opencode run` subprocesses attached to a server.

    Each complete() call is its own session on the shared server, so calls
    are independent and safe to issue from multiple threads. `cwd` should be
    a directory without opencode project context (the server's workdir) and
    `password` the server's own (opencode 2.x); see OpenCodeServer.
    """

    def __init__(
        self,
        server_url: str,
        model: str = DEFAULT_MODEL,
        cwd: str | None = None,
        reasoning_effort: str | None = None,
        timeout: int = DEFAULT_WORKER_TIMEOUT,
        password: str | None = None,
    ):
        self.server_url = server_url
        self.model = model
        self.cwd = cwd
        self.timeout = timeout
        self.password = password
        self.usage = UsageMeter(self.model, reasoning_effort)

    def complete(self, system: str, user: str) -> str:
        text, meta = run_worker(
            f"{system}\n\n{user}",
            self.model,
            server_url=self.server_url,
            cwd=self.cwd,
            timeout=self.timeout,
            password=self.password,
        )
        self.usage.record(meta)
        return text
