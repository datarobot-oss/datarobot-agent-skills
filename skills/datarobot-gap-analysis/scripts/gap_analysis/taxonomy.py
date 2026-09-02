# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load and index the condition registry (taxonomy.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import paths
from .models import Severity

# Blast-radius classification for the remediation phase.
#   plumbing       — surgical, deterministic; touches config/manifests/scaffolding only.
#   business_logic — edits application code; can alter behavior the author owns.
#   none           — advisory finding, no fix applied.
# Derived from fix_type by default (auto -> plumbing, assisted -> business_logic,
# advisory -> none); a condition may override via the `fix_risk:` key in taxonomy.yaml
# (e.g. assisted fixes that only swap a model id or base image are really plumbing).
_FIX_RISK_VALUES = {"plumbing", "business_logic", "none"}


def _derive_fix_risk(fix_type: str) -> str:
    if fix_type == "auto":
        return "plumbing"
    if fix_type == "assisted":
        return "business_logic"
    return "none"


@dataclass
class Condition:
    id: str
    pillar: str
    layer: int
    severity: Severity
    title: str
    description: str
    files_glob: list[str]
    relational: bool
    detector: str
    remediation: str
    fix_type: str
    fix_strategy: str | None
    fix_risk: str = "none"
    structural: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Condition":
        fix_type = d.get("fix_type", "advisory")
        fix_risk = d.get("fix_risk") or _derive_fix_risk(fix_type)
        if fix_risk not in _FIX_RISK_VALUES:
            fix_risk = _derive_fix_risk(fix_type)
        # A condition is "structural" when it flags an architectural deficiency that
        # cannot be surgically patched (declared explicitly, or any advisory finding at
        # high/critical severity — those have no safe in-place fix).
        severity = Severity(d.get("severity", "medium"))
        structural = bool(d.get("structural", False)) or (
            fix_type == "advisory" and severity in (Severity.CRITICAL, Severity.HIGH)
        )
        return cls(
            id=d["id"],
            pillar=d["pillar"],
            layer=int(d["layer"]),
            severity=severity,
            title=d["title"],
            description=d.get("description", "").strip(),
            files_glob=list(d.get("files_glob", [])),
            relational=bool(d.get("relational", False)),
            detector=d.get("detector", ""),
            remediation=d.get("remediation", ""),
            fix_type=fix_type,
            fix_strategy=d.get("fix_strategy"),
            fix_risk=fix_risk,
            structural=structural,
        )


class Taxonomy:
    def __init__(self, conditions: list[Condition]):
        self.conditions = conditions
        self._by_id = {c.id: c for c in conditions}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Taxonomy":
        p = Path(path) if path else paths.taxonomy_file()
        data = yaml.safe_load(p.read_text())
        return cls([Condition.from_dict(c) for c in data.get("conditions", [])])

    def get(self, condition_id: str) -> Condition | None:
        return self._by_id.get(condition_id)

    def by_layer(self, layer: int) -> list[Condition]:
        return [c for c in self.conditions if c.layer == layer]

    def by_detector(self, detector: str) -> list[Condition]:
        """All conditions whose detector starts with `detector` (e.g. a scanner name)."""
        return [c for c in self.conditions if c.detector.split("#")[0] == detector]

    def apply_severity_overrides(self, overrides: dict[str, str]) -> None:
        for cid, sev in (overrides or {}).items():
            c = self._by_id.get(cid)
            if c:
                c.severity = Severity(sev)
