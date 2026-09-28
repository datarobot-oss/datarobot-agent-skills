# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLMClient adapter over the datarobot-skills-utils opencode runtime."""

from __future__ import annotations

from ._bootstrap import ensure_skills_utils
from .settings import DEFAULT_MODEL, DEFAULT_WORKER_TIMEOUT

ensure_skills_utils()

from datarobot_skills_utils.opencode import (  # noqa: E402  (path must be set up first)
    OpenCodeServer,
    UsageMeter,
    dr_available,
    run_worker,
)


__all__ = ["OpenCodeServer", "OpenCodeWorkerClient", "dr_available"]


class OpenCodeWorkerClient:
    """LLMClient backed by `dr opencode run --attach <server>` subprocesses.

    Each complete() call is its own session on the shared server, so calls
    are independent and safe to issue from multiple threads. `cwd` should be
    a directory without opencode project context (the server's workdir); see
    OpenCodeServer.
    """

    def __init__(
        self,
        server_url: str,
        model: str = DEFAULT_MODEL,
        cwd: str | None = None,
        reasoning_effort: str | None = None,
        timeout: int = DEFAULT_WORKER_TIMEOUT,
    ):
        self.server_url = server_url
        self.model = model
        self.cwd = cwd
        self.timeout = timeout
        self.usage = UsageMeter(self.model, reasoning_effort)

    def complete(self, system: str, user: str) -> str:
        text, meta = run_worker(
            f"{system}\n\n{user}",
            self.model,
            server_url=self.server_url,
            cwd=self.cwd,
            timeout=self.timeout,
        )
        self.usage.record(meta)
        return text
