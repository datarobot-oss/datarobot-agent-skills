# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run options, resolved once from CLI flags and passed down explicitly.

Every option here used to be read from a GAP_* environment variable at the
point of use, in eight different modules. Reading them once keeps the engine a
function of its arguments, lets the report state what produced it, and lets a
test construct a run without touching the environment. The environment
variables remain as defaults for the flags, one read per option, in `from_env`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any

DEFAULT_MODEL = "datarobot/anthropic/claude-sonnet-4-6"
DEFAULT_EFFORT = "max"
DEFAULT_WORKERS = 4
DEFAULT_WORKER_TIMEOUT = 600


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.lower() not in ("off", "0", "false", "no")


@dataclass(frozen=True)
class Settings:
    use_llm: bool = True
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT  # max | off | a literal provider value
    verify: bool = True
    workers: int = DEFAULT_WORKERS
    worker_timeout: int = DEFAULT_WORKER_TIMEOUT
    # One switch for every live catalog the engine would otherwise fetch: the
    # LLM Gateway model list, the docs index, and the agent template flavors.
    offline: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        """Defaults for the CLI flags: each GAP_* variable read exactly once."""
        return cls(
            use_llm=not os.environ.get("GAP_DISABLE_LLM"),
            model=os.environ.get("GAP_LLM_MODEL", DEFAULT_MODEL),
            effort=os.environ.get("GAP_LLM_EFFORT", DEFAULT_EFFORT),
            verify=_flag("GAP_VERIFY", True),
            workers=int(os.environ.get("GAP_WORKERS", str(DEFAULT_WORKERS))),
            worker_timeout=int(
                os.environ.get("GAP_OPENCODE_TIMEOUT", str(DEFAULT_WORKER_TIMEOUT))
            ),
            offline=os.environ.get("GAP_OFFLINE", "").lower()
            in ("1", "on", "true", "yes"),
        )

    def with_(self, **changes: Any) -> Settings:
        return replace(self, **changes)


DEFAULTS = Settings()
