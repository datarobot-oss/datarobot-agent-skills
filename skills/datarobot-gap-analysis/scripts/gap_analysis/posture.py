# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Remediation-posture decision gate.

Turns a flat gap list into a recommendation: PATCH, HYBRID, or RE-PLATFORM.

The premise: fix-in-place vs. rebuild-from-scratch is a false binary. The unit of
decision is the *gap*, not the agent. Plumbing gaps (secrets, pins, scaffolding) patch
safely; STRUCTURAL gaps (no observability, no guardrails, human identity, no resilience)
can't be surgically fixed — "fixing" them means restructuring someone else's business
logic. When structural gaps dominate, lifting the business logic into a fresh, conformant
af-components base (see migrate.py) is safer than in-place surgery.

`structural` is a per-condition flag in taxonomy.yaml (any advisory high/critical also
counts). Thresholds live under `posture:` in the policy.
"""

from __future__ import annotations

from typing import Any

from .models import AnalysisResult, Severity
from .taxonomy import Taxonomy

# Severity weights — structural density is weighted, so a couple of critical structural
# gaps outweigh a long tail of low-severity plumbing.
_WEIGHT = {
    Severity.CRITICAL: 4.0,
    Severity.HIGH: 3.0,
    Severity.MEDIUM: 2.0,
    Severity.LOW: 1.0,
}

PATCH = "PATCH"
HYBRID = "HYBRID"
REPLATFORM = "RE-PLATFORM"

_DEFAULTS = {
    # score <= patch_max         -> PATCH
    # patch_max < score < replatform_min -> HYBRID
    # score >= replatform_min    -> RE-PLATFORM
    "patch_max": 0.25,
    "replatform_min": 0.50,
    # Absolute override: this many high/critical structural gaps forces RE-PLATFORM
    # regardless of density (a small repo can be all-structural at low total weight).
    "replatform_structural_count": 4,
    "max_drivers": 8,
}


def assess_posture(
    result: AnalysisResult,
    policy: dict[str, Any] | None = None,
    taxonomy: Taxonomy | None = None,
) -> dict[str, Any]:
    """Return {recommendation, score, structural_count, total, drivers, rationale}."""
    cfg = {**_DEFAULTS, **(policy or {}).get("posture", {})}
    tax = taxonomy or Taxonomy.load()

    findings = result.findings
    total = len(findings)
    if not total:
        return {
            "recommendation": PATCH,
            "score": 0.0,
            "structural_count": 0,
            "total": 0,
            "drivers": [],
            "rationale": "No gaps detected — nothing to remediate or re-platform.",
        }

    def is_structural(condition_id: str) -> bool:
        c = tax.get(condition_id)
        return bool(c and c.structural)

    total_weight = sum(_WEIGHT[f.severity] for f in findings)
    structural = [f for f in findings if is_structural(f.condition_id)]
    structural_weight = sum(_WEIGHT[f.severity] for f in structural)
    score = round(structural_weight / total_weight, 3) if total_weight else 0.0

    high_structural = [
        f for f in structural if f.severity in (Severity.CRITICAL, Severity.HIGH)
    ]

    # Decide.
    if (
        len(high_structural) >= cfg["replatform_structural_count"]
        or score >= cfg["replatform_min"]
    ):
        rec = REPLATFORM
    elif score <= cfg["patch_max"]:
        rec = PATCH
    else:
        rec = HYBRID

    drivers = _drivers(structural, int(cfg["max_drivers"]))
    return {
        "recommendation": rec,
        "score": score,
        "structural_count": len(structural),
        "total": total,
        "drivers": drivers,
        "rationale": _rationale(rec, score, len(structural), total, high_structural),
    }


def _drivers(structural, limit: int) -> list[dict[str, str]]:
    """One row per structural condition (deduped), worst severity first."""
    seen: dict[str, dict[str, str]] = {}
    for f in structural:
        cur = seen.get(f.condition_id)
        if cur is None or f.severity.rank < Severity(cur["severity"]).rank:
            seen[f.condition_id] = {
                "condition_id": f.condition_id,
                "severity": f.severity.value,
                "title": f.title,
            }
    ordered = sorted(seen.values(), key=lambda d: Severity(d["severity"]).rank)
    return ordered[:limit]


def _rationale(
    rec: str, score: float, structural_count: int, total: int, high_structural: list
) -> str:
    pct = int(round(score * 100))
    if rec == PATCH:
        return (
            f"Only {structural_count} of {total} gaps are structural "
            f"({pct}% of weighted risk). Patch in place — the fixes are surgical and "
            f"low-risk to existing business logic."
        )
    if rec == REPLATFORM:
        return (
            f"{len(high_structural)} high/critical structural gaps and {pct}% of "
            f"weighted risk is architectural. Patching these means restructuring code "
            f"you don't own — re-platform: extract the business logic into a fresh "
            f"af-components base (migrate_agent)."
        )
    return (
        f"Mixed profile — {structural_count} of {total} gaps are structural "
        f"({pct}% of weighted risk). Patch the plumbing now, and plan a migration for "
        f"the structural core rather than restructuring it in place."
    )
