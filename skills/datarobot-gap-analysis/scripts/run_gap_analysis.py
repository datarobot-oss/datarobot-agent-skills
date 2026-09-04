#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# /// script
# requires-python = ">=3.11"
# dependencies = ["PyYAML>=6.0"]
# ///

"""Thin launcher for the vendored gap_analysis engine (datarobot-gap-analysis skill).

Points the engine at the data files (taxonomy.yaml, policy/, prompts/) vendored
alongside this script, then delegates to the engine's own CLI. Run with `uv run`
so the PyYAML dependency above is resolved automatically, with no install step
(the shared datarobot-skills-utils package is located by gap_analysis/_bootstrap.py:
a repo checkout, an installed copy, or a one-time install from PyPI):

  uv run <skill_scripts_dir>/run_gap_analysis.py <repo-url-or-path> [options]

Layer-2/4 LLM reasoning runs through the `dr` CLI's opencode runtime when `dr`
is installed (parallel workers, no extra Python deps, auth via `dr auth`).
Without `dr` (or with GAP_LLM_BACKEND=litellm), add `--with litellm` for direct
gateway calls. For deeper Layer-1 scanning, add the scanner extras:

  uv run --with pip-audit --with semgrep \\
    <skill_scripts_dir>/run_gap_analysis.py <repo-url-or-path> [options]

All CLI options are documented in gap_analysis.cli (`--help`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent

os.environ.setdefault("GAP_DATA_DIR", str(_SCRIPTS_DIR))
sys.path.insert(0, str(_SCRIPTS_DIR))

from gap_analysis.cli import main  # noqa: E402  (path must be set up first)

if __name__ == "__main__":
    raise SystemExit(main())
