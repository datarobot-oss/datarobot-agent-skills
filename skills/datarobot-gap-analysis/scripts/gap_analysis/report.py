# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render the analysis result as a Markdown gap report."""

from __future__ import annotations

from typing import Any

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
EU_ROWS = [
    ("POL-001", "Risk classification"),
    ("POL-002", "Transparency / disclosure"),
    ("POL-003", "Technical documentation"),
    ("POL-004", "Record-keeping / logging"),
    ("POL-005", "Human oversight"),
    ("POL-006", "Accuracy / robustness / security"),
    ("POL-007", "Prohibited-practice screen"),
]


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
            f"**Python:** {inv.get('python_version') or 'n/a'} &nbsp;|&nbsp; "
            f"**Top types:** {langs or 'n/a'}"
        )

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
    for pillar in [p for p in PILLARS if p in by_pillar]:
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

    # Conformance scorecard (Layer 3)
    lines.append("\n## IT Conformance Scorecard\n")
    lines.append(_conformance_table(result, policy or {}))

    # EU AI Act coverage (Layer 4)
    lines.append("\n## EU AI Act Coverage\n")
    lines.append(_eu_table(result))

    # Skips & notes
    if result.skipped:
        lines.append("\n## Not Evaluated (skipped)\n")
        for s in result.skipped:
            lines.append(f"- **{s.condition_id}** — {s.reason}")
    if result.notes:
        lines.append("\n## Engine Notes\n")
        for n in result.notes:
            lines.append(f"- {n}")

    lines.append(
        "\n---\n_Secret values are never shown. EU AI Act findings are "
        "advisory and not legal advice._"
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
        if rec != "PATCH":
            out.append(
                "\n_For these, prefer `migrate_agent`: extract the business logic into "
                "a fresh af-components base rather than restructuring in place._"
            )
    return "\n".join(out)


def _conformance_table(result: AnalysisResult, policy: dict[str, Any]) -> str:
    found_ids = {f.condition_id for f in result.findings}
    out = ["| Control | Status |", "|---|---|"]
    for cid, label in CONFORMANCE_ROWS:
        status = "❌ gap" if cid in found_ids else "✅ pass"
        out.append(f"| {cid} — {label} | {status} |")
    return "\n".join(out)


def _eu_table(result: AnalysisResult) -> str:
    found_ids = {f.condition_id for f in result.findings}
    skipped_ids = {s.condition_id for s in result.skipped}
    out = ["| Article area | Status |", "|---|---|"]
    for cid, label in EU_ROWS:
        if cid in found_ids:
            status = "❌ gap"
        elif cid in skipped_ids:
            status = "➖ not evaluated"
        else:
            status = "✅ evidence found"
        out.append(f"| {cid} — {label} | {status} |")
    return "\n".join(out)
