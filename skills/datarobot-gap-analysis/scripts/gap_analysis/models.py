# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Core data types shared across the engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
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
    structural: bool = False  # only meaningful for findings with no taxonomy.yaml
    # Layer 2 provenance: the root cause the model grouped locations under, whether
    # a second verification pass confirmed the finding, and the remediation shape
    # that pass saw ("patch" | "structural"; empty defers to the taxonomy flag).
    root_cause: str = ""
    verified: bool = False
    verification: str = ""
    shape: str = ""
    # entry (dynamically-generated Layer 4 findings); posture.py falls back to
    # this when a taxonomy lookup by condition_id finds nothing.
    # Structured remediation (Layer 4): ordered steps, the docs page for the
    # DataRobot feature, what the fix attaches to and whether the repo has it,
    # and the fix path (pulumi | api | automatic | organizational) with the
    # resource it requires (deployment | custom_model | "").
    steps: list[str] = field(default_factory=list)
    docs_url: str = ""
    docs_topic: str = ""
    prerequisite: str = ""
    fix_via: str = ""
    fix_requires: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d

    @property
    def dedup_key(self) -> tuple[str, str | None, int | None, str]:
        """Identity for collapsing/matching findings: file-level findings (no
        line) stay distinct per evidence so N CVEs in one manifest aren't one."""
        return (
            self.condition_id,
            self.file,
            self.line,
            self.evidence if self.line is None else "",
        )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        data = dict(d)
        data["severity"] = Severity(data.get("severity", "medium"))
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


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
    # Every mitigation considered for Layer 4 (DataRobot risk-management), not just
    # the ones that became findings, each is {mitigation_type, title, status},
    # status one of "gap" | "pass" | "not_applicable" | "not_assessed". Lets the
    # report render regulatory coverage without a fixed checklist to compare
    # against (Layer 4 has no static condition list, see taxonomy.yaml).
    regulatory_coverage: list[dict[str, str]] = field(default_factory=list)
    # The repo's pulumi-datarobot footprint as seen by Layer 4 (see
    # risk_management._detect_iac); empty when no Pulumi program was found.
    iac: dict[str, Any] = field(default_factory=dict)
    # LLM Gateway token usage for this run, per phase and in total (see
    # datarobot_skills_utils.opencode.UsageMeter); empty when no LLM ran.
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "skipped": [asdict(s) for s in self.skipped],
            "notes": list(self.notes),
            "posture": self.posture,
            "regulatory_coverage": self.regulatory_coverage,
            "iac": self.iac,
            "usage": self.usage,
            "inventory": {k: v for k, v in self.inventory.items() if k != "files"},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AnalysisResult":
        result = cls()
        result.findings = [Finding.from_dict(f) for f in d.get("findings", [])]
        result.skipped = [ConditionSkip(**s) for s in d.get("skipped", [])]
        result.notes = list(d.get("notes", []))
        result.posture = d.get("posture") or {}
        result.regulatory_coverage = d.get("regulatory_coverage") or []
        result.iac = d.get("iac") or {}
        result.usage = d.get("usage") or {}
        result.inventory = d.get("inventory") or {}
        return result

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
