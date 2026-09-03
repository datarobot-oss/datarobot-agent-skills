# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render the analysis result as a Markdown gap report."""

from __future__ import annotations

from typing import Any

from .posture import migration_advice
from .models import AnalysisResult, Finding, PILLARS

_SEV_BADGE = {
    "critical": "🟥 CRITICAL",
    "high": "🟧 HIGH",
    "medium": "🟨 MEDIUM",
    "low": "⬜ LOW",
}
_FIX_BADGE = {
    "auto": "🔧 auto-fix",
    "assisted": "🤖 assisted-fix",
    "advisory": "📝 advisory",
}
_RISK_BADGE = {"plumbing": "plumbing", "business_logic": "⚠ business-logic"}

# Scorecard row definitions, shared with the HTML renderer so the two never drift.
CONFORMANCE_ROWS = [
    ("ITA-001", "Python version"),
    ("ITA-002", "Library allow/deny"),
    ("ITA-003", "Approved LLM model"),
    ("ITA-004", "OSS licenses"),
    ("ITA-005", "Approved base image"),
    ("AIG-003", "Approved LLM model (gov)"),
]

# Layer 4 (regulatory) has no fixed row list: it's driven entirely by whatever
# the org's live DataRobot risk-management policy contains (see
# risk_management.py), so the coverage table renders result.regulatory_coverage
# instead of a static checklist.
COVERAGE_STATUS_LABEL = {
    "gap": "❌ gap",
    "pass": "✅ evidence found",
    "not_assessed": "❔ required, not assessed",
    "unknown_type": "⚠ unrecognized mitigation type",
}


def _fix_label(f: Finding) -> str:
    """Fix-type badge, suffixed with the blast-radius class when a fix exists."""
    base = _FIX_BADGE.get(f.fix_type, f.fix_type)
    risk = _RISK_BADGE.get(f.fix_risk)
    return f"{base} · {risk}" if risk else base


def _loc(f: Finding) -> str:
    if not f.file:
        return "_(repo-wide)_"
    return f"`{f.file}`" + (f":{f.line}" if f.line else "")


def render_report(
    result: AnalysisResult, repo: str = "", policy: dict[str, Any] | None = None
) -> str:
    counts = result.counts()
    total = len(result.findings)
    lines: list[str] = []
    lines.append("# Enterprise-Readiness Gap Report")
    if repo:
        lines.append(f"\n**Repository:** {repo}")
    inv = result.inventory
    if inv:
        langs = ", ".join(
            f"{k} ({v})" for k, v in list(inv.get("languages", {}).items())[:6]
        )
        lines.append(
            f"**Files scanned:** {inv.get('file_count', 0)} &nbsp;|&nbsp; "
            f"**Python:** {python_label(inv)} &nbsp;|&nbsp; "
            f"**Top types:** {langs or 'n/a'}"
        )
        stack = stack_line(inv)
        if stack:
            lines.append(stack)

    # Summary line
    lines.append("\n## Summary\n")
    lines.append(
        f"**{total} gaps** — "
        + " · ".join(
            f"{_SEV_BADGE[s]}: {counts[s]}"
            for s in ["critical", "high", "medium", "low"]
        )
    )

    fixable = sum(1 for f in result.findings if f.fix_type in ("auto", "assisted"))
    auto = sum(1 for f in result.findings if f.fix_type == "auto")
    lines.append(
        f"\n{fixable} of {total} are fixable ({auto} automatically). "
        f"Run with `--fix` to remediate on a `gap-fixes/*` branch."
    )

    # Remediation posture — patch in place vs. re-platform onto af-components
    if result.posture:
        lines.append(_posture_section(result.posture))

    # Findings grouped by pillar, ordered by severity within
    lines.append("\n## Findings\n")
    by_pillar: dict[str, list[Finding]] = {}
    for f in result.by_severity():
        by_pillar.setdefault(f.pillar, []).append(f)

    if not result.findings:
        lines.append("_No gaps detected._")
    # Regulatory (POL) findings render inside the Layer 4 section below.
    for pillar in [p for p in PILLARS if p in by_pillar and p != "POL"]:
        lines.append(f"\n### {PILLARS[pillar]} ({pillar})\n")
        for f in by_pillar[pillar]:
            conf = "" if f.confidence == "high" else f" _(confidence: {f.confidence})_"
            lines.append(
                f"- **{f.condition_id}** {_SEV_BADGE[f.severity.value]} · "
                f"{_fix_label(f)} — {f.title}{conf}\n"
                f"  - **Where:** {_loc(f)}\n"
                f"  - **Evidence:** {f.evidence or '—'}\n"
                f"  - **Why it matters:** {f.explanation or '—'}\n"
                f"  - **Fix:** {f.remediation or '—'}"
            )
            lines.extend(_fix_details(f))

    # Conformance scorecard (Layer 3)
    lines.append("\n## IT Conformance Scorecard\n")
    lines.append(_conformance_table(result, policy or {}))

    # DataRobot risk-management coverage (Layer 4)
    lines.append("\n## DataRobot Risk-Management Coverage\n")
    lines.append(_regulatory_section(result))

    # Skips & notes
    if result.skipped:
        lines.append("\n## Not Evaluated (skipped)\n")
        for s in result.skipped:
            lines.append(f"- **{s.condition_id}**: {_clip(s.reason)}")
    if result.notes:
        lines.append("\n## Engine Notes\n")
        for n in result.notes:
            lines.append(f"- {n}")

    lines.append(
        "\n---\n_Secret values are never shown. DataRobot risk-management "
        "findings are advisory and not legal advice._"
    )
    return "\n".join(lines)


_POSTURE_BADGE = {
    "PATCH": "🟢 PATCH",
    "HYBRID": "🟡 HYBRID",
    "RE-PLATFORM": "🔴 RE-PLATFORM",
}


def _posture_section(posture: dict[str, Any]) -> str:
    rec = posture.get("recommendation", "PATCH")
    badge = _POSTURE_BADGE.get(rec, rec)
    pct = int(round(posture.get("score", 0.0) * 100))
    out = [
        "\n## Remediation Posture\n",
        f"**Recommendation: {badge}** &nbsp;|&nbsp; "
        f"structural risk: {pct}% &nbsp;|&nbsp; "
        f"{posture.get('structural_count', 0)} of {posture.get('total', 0)} gaps structural\n",
        posture.get("rationale", ""),
    ]
    drivers = posture.get("drivers") or []
    if drivers:
        out.append("\n**Structural drivers** (can't be surgically patched):\n")
        for d in drivers:
            sev = _SEV_BADGE.get(d.get("severity", ""), d.get("severity", ""))
            out.append(f"- **{d['condition_id']}** {sev} — {d['title']}")
        if rec != "PATCH" and posture.get("advice"):
            out.append(f"\n_{posture['advice']}_")
    return "\n".join(out)


def _conformance_table(result: AnalysisResult, policy: dict[str, Any]) -> str:
    found_ids = {f.condition_id for f in result.findings}
    out = ["| Control | Status |", "|---|---|"]
    for cid, label in CONFORMANCE_ROWS:
        status = "❌ gap" if cid in found_ids else "✅ pass"
        out.append(f"| {cid} — {label} | {status} |")
    return "\n".join(out)


def python_label(inv: dict[str, Any]) -> str:
    """'3.10' for one floor, '3.10 lowest (repo root 3.10, core 3.11,
    web 3.12)' when components differ, 'n/a' when nothing declares one."""
    floor = inv.get("python_version")
    if not floor:
        return "n/a"
    versions = inv.get("python_versions") or {}
    if len(set(versions.values())) > 1:
        ordered = sorted(versions.items(), key=lambda kv: (kv[0] != ".", kv[0]))
        parts = ", ".join(f"{'repo root' if d == '.' else d} {v}" for d, v in ordered)
        return f"{floor} lowest ({parts})"
    return str(floor)


def stack_line(inv: dict[str, Any]) -> str:
    """Template provenance and agent framework, when known."""
    parts = []
    if inv.get("template_sources"):
        parts.append("**Template:** " + ", ".join(inv["template_sources"]))
    if inv.get("agent_frameworks"):
        parts.append(
            "**Agent framework:** "
            + ", ".join(
                f"{f['name']} ({'native DataRobot template' if f['native'] else 'Base template'})"
                for f in inv["agent_frameworks"]
            )
        )
    return " &nbsp;|&nbsp; ".join(parts)


def _clip(text: str, limit: int = 400) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fix_details(f: Finding) -> list[str]:
    """Structured remediation lines (Layer 4): prerequisite, steps, docs."""
    out: list[str] = []
    if f.prerequisite:
        out.append(f"  - **Needs:** {f.prerequisite}")
    if f.steps:
        out.append("  - **How:**")
        out.extend(f"    {i}. {step}" for i, step in enumerate(f.steps, start=1))
    if f.docs_url:
        out.append(f"  - **Docs:** {f.docs_url}")
    elif f.docs_topic:
        out.append(f"  - **Docs:** search docs.datarobot.com for {f.docs_topic!r}")
    return out


def compliance_path(result: AnalysisResult) -> list[dict[str, Any]]:
    """Group the regulatory gaps into the ordered steps that close them.

    Eighteen guard and monitoring gaps on an application-only Pulumi program
    collapse into one architectural step (deploy the LLM path through
    DataRobot) followed by configuration, compliance tests and console work.
    """
    pol = [f for f in result.findings if f.pillar == "POL"]
    if not pol:
        return []
    iac = result.iac or {}
    has = {
        "deployment": bool(iac.get("deployment")),
        "custom_model": bool(iac.get("custom_model")),
    }

    def needs(f: Finding) -> str:
        return f.fix_requires or ("deployment" if f.fix_via == "automatic" else "")

    blocked = [f for f in pol if needs(f) and not has.get(needs(f), False)]
    ready = [f for f in pol if f.fix_via == "pulumi" and f not in blocked]
    free = [f for f in pol if f.fix_via == "automatic" and f not in blocked]
    tests = [f for f in pol if f.fix_via == "api" and "compliance_test" in f.detector]
    console = [
        f for f in pol if f.fix_via in ("api", "organizational") and f not in tests
    ]
    steps: list[dict[str, Any]] = []
    if blocked:
        resources = sorted({_RESOURCE_LABEL.get(needs(f), needs(f)) for f in blocked})
        automatic = [f for f in blocked if f.fix_via == "automatic"]
        configure = [f for f in blocked if f.fix_via != "automatic"]
        steps.append(
            {
                "title": "Put the model or LLM path behind DataRobot",
                "detail": (
                    f"Add {' and '.join(resources)} to the Pulumi program (a RegisteredModel "
                    "or CustomModel deployed through a datarobot.Deployment). "
                    f"{migration_advice(result.inventory)} "
                    f"Unlocks {len(blocked)} mitigation(s): {len(automatic)} come with the "
                    f"deployment, {len(configure)} then need a settings block."
                ),
                "items": blocked,
            }
        )
    if ready:
        steps.append(
            {
                "title": "Configure the existing Deployment / CustomModel in Pulumi",
                "detail": "Settings blocks and guard configurations on resources the program already declares.",
                "items": ready,
            }
        )
    if free:
        steps.append(
            {
                "title": "Provided by the platform once deployed",
                "detail": "Nothing to configure; verify in Console after the first deploy.",
                "items": free,
            }
        )
    if tests:
        steps.append(
            {
                "title": "Run the compliance tests in the LLM test suite",
                "detail": "Use Case playground evaluation tools; attach results to the risk assessment.",
                "items": tests,
            }
        )
    if console:
        steps.append(
            {
                "title": "Complete in the DataRobot console or API",
                "detail": "Risk assessment, compliance documentation and organizational confirmations.",
                "items": console,
            }
        )
    return steps


_RESOURCE_LABEL = {
    "deployment": "a datarobot.Deployment",
    "custom_model": "a datarobot.CustomModel",
}


def _short_title(f: Finding) -> str:
    return f.title.replace("DataRobot risk-management: ", "").replace(
        " not satisfied", ""
    )


def _regulatory_section(result: AnalysisResult) -> str:
    """Layer 4 in one place: every required mitigation, grouped by the step that
    closes it, each gap expanded with its evidence and fix; then what passed and
    what could not be assessed."""
    if not result.regulatory_coverage:
        return (
            "_No DataRobot risk-management policy was reachable for this run "
            "(see Engine Notes below for why); nothing to show here. There is "
            "no local fallback checklist, this section is empty rather than "
            "misleadingly reassuring._"
        )
    coverage = result.regulatory_coverage
    gaps = [f for f in result.findings if f.pillar == "POL"]
    passed = [r for r in coverage if r["status"] == "pass"]
    unassessed = [r for r in coverage if r["status"] not in ("pass", "gap")]
    out = [
        f"{len(coverage)} required mitigation(s): {len(gaps)} gap(s), {len(passed)} with "
        f"evidence, {len(unassessed)} not assessed."
    ]
    for i, step in enumerate(compliance_path(result), start=1):
        out.append(f"\n**{i}. {step['title']}.** {step['detail']}\n")
        for f in step["items"]:
            docs = f" · [docs]({f.docs_url})" if f.docs_url else ""
            if not docs and f.docs_topic:
                docs = f" · docs: search {f.docs_topic!r}"
            conf = "" if f.confidence == "high" else f" _(confidence: {f.confidence})_"
            out.append(f"- ❌ **{_short_title(f)}** (`{f.condition_id}`){docs}{conf}")
            out.append(f"  - **Where:** {_loc(f)}")
            out.append(f"  - **Evidence:** {f.evidence or 'n/a'}")
            out.append(f"  - **Why it matters:** {f.explanation or 'n/a'}")
            out.append(f"  - **Fix:** {f.remediation or 'n/a'}")
            out.extend(
                line for line in _fix_details(f) if not line.startswith("  - **Docs")
            )
    if passed:
        out.append("\n**Evidence found**\n")
        out.extend(f"- ✅ {r['title']}" for r in passed)
    if unassessed:
        out.append("\n**Required, not assessed**\n")
        out.extend(
            f"- {COVERAGE_STATUS_LABEL.get(r['status'], r['status'])}: {r['title']}"
            for r in unassessed
        )
    return "\n".join(out)
