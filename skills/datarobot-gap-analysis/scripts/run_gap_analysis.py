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
so the PyYAML dependency above is resolved automatically, with no install step:

  uv run <skill_scripts_dir>/run_gap_analysis.py <repo-url-or-path> [options]

For deeper Layer-1 scanning or Layer-2/4 LLM reasoning, add the optional extras:

  uv run --with detect-secrets --with pip-audit --with semgrep --with litellm \\
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
