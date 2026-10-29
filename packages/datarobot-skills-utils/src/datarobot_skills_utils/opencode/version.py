# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Which opencode release `dr opencode` runs.

`dr opencode` starts whichever opencode is installed. opencode 2.x changed the
`run` flags, protects its server with a password and moved its health route,
so the worker and server code ask once per process and build commands to match.
"""

from __future__ import annotations

import functools
import re
import subprocess
from dataclasses import dataclass

DR_OPENCODE = [
    "dr",
    "--skip-plugin-update-check",
    "--plugin-discovery-timeout",
    "30s",
    "opencode",
]

# opencode 1.x prints `1.17.11`, 2.x prints `opencode v2.1.3`; `dr` adds lines of its own.
_VERSION_LINE = re.compile(
    r"(?:opencode\s+)?v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9a-z.+-]*)?", re.IGNORECASE
)
_DETECT_TIMEOUT = 60


def parse_version(output: str) -> tuple[int, int, int] | None:
    """The version on the last line of `output` that holds nothing else."""
    for line in reversed(output.splitlines()):
        match = _VERSION_LINE.fullmatch(line.strip())
        if match:
            return int(match[1]), int(match[2]), int(match[3])
    return None


def _last_line(output: str, limit: int = 200) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""


@dataclass(frozen=True)
class OpenCodeVersion:
    """What `dr opencode --version` reported."""

    release: tuple[int, int, int] | None
    output: str = ""  # its last output line, for error messages

    @property
    def major(self) -> int:
        """The command set to use: 2 for opencode 2.x and later, else 1.

        An unreadable version keeps the 1.x commands, which this package has
        always sent.
        """
        return 2 if self.release is not None and self.release[0] >= 2 else 1

    def describe(self) -> str:
        """Which opencode was found and, when unknown, what to do about it."""
        if self.release is not None:
            return "opencode " + ".".join(str(n) for n in self.release)
        return (
            "opencode version unknown: `dr opencode --version` printed "
            f"{self.output!r}, so the opencode 1.x commands were used. This "
            "package supports opencode 1.x and 2.x; check that "
            "`dr opencode --version` prints one"
        )


@functools.cache
def opencode_version() -> OpenCodeVersion:
    """The opencode that `dr opencode` runs, asked once per process.

    The answer takes a few seconds, since `dr` refreshes its model list on
    every launch.
    """
    try:
        result = subprocess.run(
            [*DR_OPENCODE, "--version"],
            capture_output=True,
            text=True,
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=_DETECT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return OpenCodeVersion(None, f"{type(e).__name__}: {e}"[:200])
    # On success the version is the last stdout line; on failure stderr says why.
    shown = result.stdout if result.returncode == 0 else result.stderr
    return OpenCodeVersion(
        parse_version(result.stdout), _last_line(shown or result.stdout)
    )
