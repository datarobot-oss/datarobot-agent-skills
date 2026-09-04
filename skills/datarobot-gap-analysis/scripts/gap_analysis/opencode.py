# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLMClient adapter over the datarobot-skills-utils opencode runtime."""

from __future__ import annotations

import os

from ._bootstrap import ensure_skills_utils

ensure_skills_utils()

from datarobot_skills_utils.opencode import (  # noqa: E402  (path must be set up first)
    OpenCodeServer,
    dr_available,
    run_worker,
)

_DEFAULT_MODEL = "datarobot/anthropic/claude-sonnet-4-6"
_WORKER_TIMEOUT_SECONDS = int(os.environ.get("GAP_OPENCODE_TIMEOUT", "120"))

__all__ = ["OpenCodeServer", "OpenCodeWorkerClient", "dr_available"]


class OpenCodeWorkerClient:
    """LLMClient backed by `dr opencode run --attach <server>` subprocesses.

    Each complete() call is its own session on the shared server, so calls
    are independent and safe to issue from multiple threads. `cwd` should be
    a directory without opencode project context (the server's workdir); see
    OpenCodeServer.
    """

    def __init__(
        self, server_url: str, model: str | None = None, cwd: str | None = None
    ):
        self.server_url = server_url
        self.model = model or os.environ.get("GAP_LLM_MODEL", _DEFAULT_MODEL)
        self.cwd = cwd

    def complete(self, system: str, user: str) -> str:
        text, _meta = run_worker(
            f"{system}\n\n{user}",
            self.model,
            server_url=self.server_url,
            cwd=self.cwd,
            timeout=_WORKER_TIMEOUT_SECONDS,
        )
        return text
