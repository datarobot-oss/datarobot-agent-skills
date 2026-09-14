# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Locate the engine's data files (taxonomy, policy, prompts).

Defaults to the directory one level above this package (the `scripts/`
directory this package's data files, taxonomy.yaml, policy/, prompts/, and
risk_management_mitigations.yaml, are vendored into alongside it). When
vendored at a different depth, set GAP_DATA_DIR to the directory that
contains them.
"""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def root() -> Path:
    return Path(os.environ.get("GAP_DATA_DIR", _DEFAULT_ROOT))


def taxonomy_file() -> Path:
    return root() / "taxonomy.yaml"


def policy_file() -> Path:
    return root() / "policy" / "defaults.yaml"


def prompts_dir() -> Path:
    return root() / "prompts"


def risk_management_mitigations_file() -> Path:
    return root() / "risk_management_mitigations.yaml"


def resolve(ref: str) -> Path:
    """Resolve a data-relative reference like 'prompts/sec-001-...md'."""
    return root() / ref
