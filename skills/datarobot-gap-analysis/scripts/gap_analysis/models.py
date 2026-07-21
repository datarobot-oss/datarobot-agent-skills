# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core data types shared across the engine."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @property
    def rank(self) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}[self.value]


# Pillar id -> human label, used for grouping in the report.
PILLARS = {
    "SEC": "Security",
    "IDN": "Identity & Access",
    "AIG": "AI/LLM Governance",
    "OPS": "Operations & Observability",
    "REL": "Reliability",
    "ITA": "IT Conformance",
    "POL": "Regulatory Policy",
}


@dataclass
class Finding:
    """A single detected gap. Never carries a raw secret value."""

    condition_id: str
    pillar: str
    severity: Severity
    title: str
    file: str | None = None
    line: int | None = None
    evidence: str = ""
    explanation: str = ""
    remediation: str = ""
    fix_type: str = "advisory"  # auto | assisted | advisory
    fix_strategy: str | None = None
    fix_risk: str = "none"  # plumbing | business_logic | none (blast radius)
    confidence: str = "high"  # high | medium | low
    layer: int = 0
    detector: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class ConditionSkip:
    """Recorded when a (usually relational) condition could not be evaluated."""

    condition_id: str
    reason: str


@dataclass
class AnalysisResult:
    findings: list[Finding] = field(default_factory=list)
    skipped: list[ConditionSkip] = field(default_factory=list)
    inventory: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    posture: dict[str, Any] = field(
        default_factory=dict
    )  # remediation posture (see posture.py)

    def by_severity(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (f.severity.rank, f.pillar, f.condition_id),
        )

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in Severity}
        for f in self.findings:
            out[f.severity.value] += 1
        return out
