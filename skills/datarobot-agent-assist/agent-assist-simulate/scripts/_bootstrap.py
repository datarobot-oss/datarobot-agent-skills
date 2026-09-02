# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Locate datarobot-skills-utils: a sibling `packages/` checkout (found by
walking up from this file) wins, then an installed distribution, then a
one-time install from PyPI into the running interpreter.

Run directly (`python3 _bootstrap.py`) to resolve it ahead of time."""

from __future__ import annotations

import importlib
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

SKILLS_UTILS_REQUIREMENT = "datarobot-skills-utils"

INSTALL_HINT = (
    "datarobot-skills-utils not found: run `python3 -m pip install "
    f"{SKILLS_UTILS_REQUIREMENT}`, or run from a checkout that contains "
    "packages/datarobot-skills-utils"
)


def _sibling_src() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        src = parent / "packages" / "datarobot-skills-utils" / "src"
        if (src / "datarobot_skills_utils").is_dir():
            return src
    return None


def _importable() -> bool:
    importlib.invalidate_caches()
    return importlib.util.find_spec("datarobot_skills_utils") is not None


def _install_command() -> list[str] | None:
    if importlib.util.find_spec("pip") is not None:
        return [sys.executable, "-m", "pip", "install", SKILLS_UTILS_REQUIREMENT]
    uv = shutil.which("uv")
    if uv is not None:
        return [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            SKILLS_UTILS_REQUIREMENT,
        ]
    return None


def ensure_skills_utils() -> None:
    src = _sibling_src()
    if src is not None:
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        return
    if _importable():
        return
    cmd = _install_command()
    if cmd is None:
        raise ImportError(f"{INSTALL_HINT} (neither pip nor uv is available)")
    print(
        "datarobot-skills-utils is not installed; installing from PyPI ...",
        file=sys.stderr,
    )
    result = subprocess.run(cmd, check=False, stdout=sys.stderr)
    if result.returncode != 0 or not _importable():
        raise ImportError(INSTALL_HINT)


def main() -> int:
    try:
        ensure_skills_utils()
    except ImportError as exc:
        print(exc, file=sys.stderr)
        return 1
    import datarobot_skills_utils

    print(f"datarobot-skills-utils: {Path(datarobot_skills_utils.__file__).parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
