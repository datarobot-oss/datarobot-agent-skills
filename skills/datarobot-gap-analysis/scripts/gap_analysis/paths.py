# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Locate the engine's data files (taxonomy, policy, prompts).

Defaults to the repo root (two levels above this package). When the package is
vendored into another project (e.g. the DataRobot agent template), set
GAP_DATA_DIR to the directory that contains taxonomy.yaml, policy/, and prompts/.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def root() -> Path:
    return Path(os.environ.get("GAP_DATA_DIR", _DEFAULT_ROOT))


def taxonomy_file() -> Path:
    return root() / "taxonomy.yaml"


def policy_file() -> Path:
    return root() / "policy" / "defaults.yaml"


def prompts_dir() -> Path:
    return root() / "prompts"


def resolve(ref: str) -> Path:
    """Resolve a data-relative reference like 'prompts/sec-001-...md'."""
    return root() / ref
