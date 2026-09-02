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

`structural` is a per-condition flag in taxonomy.yaml for Layers 1-3 (any advisory
high/critical also counts); Layer 4 findings carry it directly on the Finding instead,
since they're generated dynamically from a DataRobot risk-management policy rather
than a taxonomy.yaml entry (almost always true there, since satisfying a mitigation
nearly always means adopting a DataRobot platform feature, not patching code in
place). Thresholds live under `posture:` in the policy.
"""

from __future__ import annotations

from typing import Any

from .models import AnalysisResult, Finding, Severity
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

    def is_structural(f: Finding) -> bool:
        # Findings with a taxonomy.yaml entry (Layers 1-3) defer to the
        # condition's own flag. Layer 4 findings are dynamically generated (no
        # taxonomy entry, driven by the org's live DataRobot risk-management
        # policy (see risk_management.py) and carry the flag on the Finding
        # itself instead.
        c = tax.get(f.condition_id)
        if c is not None:
            return bool(c.structural)
        return bool(f.structural)

    total_weight = sum(_WEIGHT[f.severity] for f in findings)
    structural = [f for f in findings if is_structural(f)]
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
    advice = migration_advice(result.inventory)
    return {
        "recommendation": rec,
        "score": score,
        "structural_count": len(structural),
        "total": total,
        "drivers": drivers,
        "advice": advice,
        "rationale": _rationale(
            rec, score, len(structural), total, high_structural, advice
        ),
    }


def migration_advice(inventory: dict[str, Any] | None) -> str:
    """What "re-platform" means for this repo.

    A repo already generated from af-components keeps its application; the
    structural fix is to put the agent or LLM path behind a DataRobot agent
    deployment so guards and monitoring can attach. The agent framework is
    never changed unless the user asks: frameworks without a native DataRobot
    template deploy through the generic Base flavor.
    """
    inv = inventory or {}
    sources = [s for s in inv.get("template_sources", []) if "af-component" in s]
    frameworks = inv.get("agent_frameworks") or []
    if sources:
        text = (
            f"This repo already builds on af-components ({', '.join(sources)}). Keep the "
            "application and put the agent or LLM path behind a DataRobot agent deployment "
            "(a CustomModel behind a datarobot.Deployment) so guards and monitoring attach."
        )
    else:
        text = (
            "Re-platform onto af-components with the datarobot-agent-assist skill: extract "
            "the business logic into a fresh af-components base rather than restructuring "
            "in place."
        )
    if frameworks:
        native = [f["name"] for f in frameworks if f["native"]]
        other = [f["name"] for f in frameworks if not f["native"]]
        if other:
            choices = inv.get("agent_template_choices") or {}
            natives = [label for label, value in choices.items() if value != "base"]
            offered = ", ".join(natives) if natives else "a fixed set of frameworks"
            text += (
                f" The agent uses {', '.join(other)}; the DataRobot agent template offers "
                f"{offered} natively, so deploy it through its generic Base flavor, which "
                "wraps any Python agent, rather than rewriting it onto another framework."
            )
        elif native:
            text += f" The agent uses {', '.join(native)}, which has a native DataRobot agent template."
    return text


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
    rec: str,
    score: float,
    structural_count: int,
    total: int,
    high_structural: list,
    advice: str = "",
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
            f"weighted risk is architectural: these gaps are closed by changing how the "
            f"system is deployed and governed, not by editing individual files. {advice}"
        )
    return (
        f"Mixed profile — {structural_count} of {total} gaps are structural "
        f"({pct}% of weighted risk). Patch the plumbing now, and plan the structural "
        f"core separately. {advice}"
    )
