# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM execution through the DataRobot CLI's opencode runtime.

One `dr opencode serve` process is started for a whole run and every LLM call
attaches to it as a short-lived `dr opencode run` subprocess. Attaching to a
shared server (rather than one opencode process per call) avoids opencode's
SQLite lock contention under parallelism. Auth rides on the CLI's own login.
"""

from .events import parse_events, strip_code_fences
from .server import OpenCodeServer, dr_available
from .worker import WORKER_PREAMBLE, build_run_command, run_worker, sanitize_message

__all__ = [
    "OpenCodeServer",
    "WORKER_PREAMBLE",
    "build_run_command",
    "dr_available",
    "parse_events",
    "run_worker",
    "sanitize_message",
    "strip_code_fences",
]
