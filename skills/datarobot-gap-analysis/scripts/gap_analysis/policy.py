# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load policy/defaults.yaml and deep-merge a user override over it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import paths


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override into base.

    - dicts merge recursively
    - a key ending in ``_add`` appends its list to the base list at the stripped key
    - everything else (including plain lists) is replaced
    """
    out = dict(base)
    for key, val in (override or {}).items():
        if key.endswith("_add") and isinstance(val, list):
            target = key[:-4]
            out[target] = list(out.get(target, [])) + list(val)
        elif isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def load_policy(user_path: str | Path | None = None) -> dict[str, Any]:
    """Return the merged policy (defaults <- user override)."""
    defaults = yaml.safe_load(paths.policy_file().read_text()) or {}
    if not user_path:
        return defaults
    user = yaml.safe_load(Path(user_path).read_text()) or {}
    return _deep_merge(defaults, user)
