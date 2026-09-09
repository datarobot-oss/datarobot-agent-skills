# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Token accounting across the LLM calls of one run, grouped by phase."""

from __future__ import annotations

import threading
from typing import Any

_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


class UsageMeter:
    """Sums per-call token meta into per-phase and total rows.

    Callers set `phase` before a batch of calls ("Layer 2", "Layer 4",
    "fix"); worker threads then record their meta under whichever phase is
    current. Reasoning tokens are counted separately when the backend reports
    them and are also part of output tokens where the provider bills them so.
    """

    def __init__(self, model: str = "", reasoning_effort: str | None = None) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.phase = "other"
        self._lock = threading.Lock()
        self._phases: dict[str, dict[str, Any]] = {}

    def record(self, meta: dict[str, Any] | None, phase: str | None = None) -> None:
        if not meta:
            return
        name = phase or self.phase
        with self._lock:
            row = self._phases.setdefault(name, self._empty())
            row["calls"] += 1
            for key in _FIELDS:
                row[key] += int(meta.get(key, 0) or 0)
            row["reasoning_tokens"] += int(meta.get("reasoning_tokens", 0) or 0)
            row["cost"] += float(meta.get("cost", 0.0) or 0.0)

    @staticmethod
    def _empty() -> dict[str, Any]:
        row: dict[str, Any] = {"calls": 0, "reasoning_tokens": 0, "cost": 0.0}
        row.update({key: 0 for key in _FIELDS})
        return row

    def snapshot(self) -> dict[str, Any]:
        """{model, reasoning_effort, phases: {name: row}, total: row}; every
        row carries calls, input/output/cache tokens, reasoning tokens, cost."""
        with self._lock:
            phases = {k: dict(v) for k, v in self._phases.items()}
        total = self._empty()
        for row in phases.values():
            for key, value in row.items():
                total[key] += value
        total["cost"] = round(total["cost"], 6)
        for row in phases.values():
            row["cost"] = round(row["cost"], 6)
        return {
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "phases": phases,
            "total": total,
        }
