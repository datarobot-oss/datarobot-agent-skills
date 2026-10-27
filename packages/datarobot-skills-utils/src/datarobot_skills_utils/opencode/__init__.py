# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM execution through the DataRobot CLI's opencode runtime.

One `dr opencode serve` process is started for a whole run and every LLM call
attaches to it as a short-lived `dr opencode run` subprocess. Attaching to a
shared server (rather than one opencode process per call) avoids opencode's
SQLite lock contention under parallelism. Auth rides on the CLI's own login.
Works with opencode 1.x and 2.x: the commands follow the version `dr opencode`
reports (see version.py).
"""

from .events import parse_events, strip_code_fences
from .reasoning import max_reasoning_effort, resolve_effort, token_limits, worker_env
from .server import OpenCodeServer, dr_available
from .usage import UsageMeter
from .version import OpenCodeVersion, opencode_version
from .worker import (
    WORKER_PREAMBLE,
    RunCall,
    build_run_call,
    build_run_command,
    run_worker,
    sanitize_message,
)

__all__ = [
    "WORKER_PREAMBLE",
    "OpenCodeServer",
    "OpenCodeVersion",
    "RunCall",
    "UsageMeter",
    "build_run_call",
    "build_run_command",
    "dr_available",
    "max_reasoning_effort",
    "opencode_version",
    "parse_events",
    "resolve_effort",
    "run_worker",
    "sanitize_message",
    "strip_code_fences",
    "token_limits",
    "worker_env",
]
