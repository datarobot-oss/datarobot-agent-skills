# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""One item format for swarm breaches and gap-analysis findings.

Turns `eval-results.json` (agent-assist-simulate) and `gap-findings.json`
(datarobot-gap-analysis) into a single list of items with one severity scale,
a status, and whether the item blocks deployment and under which rule.

Blocking rules:
- a swarm breach blocks when its severity is in the agent spec's `fail_on`;
- an exhausted or errored swarm scenario always blocks;
- a gap finding blocks when its severity is in the gap policy's `fail_on`.

Standard library only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SEVERITIES = ("critical", "high", "medium", "low")
DEFAULT_GAP_FAIL_ON = ("critical", "high")

# open: still present. fixed: closed on the fix branch. exhausted / error: a
# swarm scenario that convergence could not resolve or could not run. warning:
# a passed swarm scenario the evaluator still scored.
STATUS_ORDER = ("exhausted", "error", "open", "warning", "fixed")


@dataclass
class Item:
    id: str
    source: str  # swarm | gap
    severity: str | None  # critical | high | medium | low | None (unrated)
    title: str
    location: str
    status: str
    blocking: bool = False
    rule: str | None = None
    evidence: list[str] = field(default_factory=list)
    fix: str = ""
    # How a gap item was closed: "codemod" (--fix applied it) or "re-score" (the
    # re-run no longer finds it, e.g. after an assisted fix).
    fixed_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def severity_rank(severity: str | None) -> int:
    return SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES)


def sort_items(items: list[Item]) -> list[Item]:
    return sorted(
        items,
        key=lambda i: (
            not i.blocking,
            STATUS_ORDER.index(i.status),
            severity_rank(i.severity),
            i.id,
        ),
    )


def _rated(severity: str | None) -> str | None:
    return severity if severity in SEVERITIES else None


def swarm_items(eval_results: dict[str, Any]) -> list[Item]:
    """Items from eval-results.json. Clean passes produce no item."""
    fail_on = list(eval_results.get("fail_on") or [])
    fail_on_label = ", ".join(fail_on) or "none"
    changes: dict[str, list[str]] = {}
    for change in eval_results.get("changes") or []:
        changes.setdefault(change["scenario_id"], []).append(change["summary"])

    items = []
    for outcome in eval_results.get("scenarios", []):
        sid = outcome["scenario_id"]
        status = outcome["status"]
        severity = _rated(outcome.get("severity"))
        initially_breached = outcome.get("initial_status") in ("breach", "exhausted")
        item = Item(
            id=f"swarm:{sid}",
            source="swarm",
            severity=severity,
            title=f"[{outcome['track']}] {outcome['name']}",
            location=f"capability: {outcome.get('capability_targeted') or 'n/a'}",
            status="open",
            evidence=list(outcome.get("evidence") or []),
            fix="; ".join(changes.get(sid, [])),
        )
        reason = outcome.get("breach_reason") or outcome.get("evaluation_reason")
        if reason and not item.evidence:
            item.evidence = [reason]
        if status == "passed":
            if initially_breached:
                item.status = "fixed"
                item.severity = _rated(outcome.get("initial_severity"))
            elif severity:
                item.status = "warning"
            else:
                continue
        elif status in ("exhausted", "error"):
            item.status = status
            item.blocking = True
            item.rule = f"{'errored' if status == 'error' else 'exhausted'} swarm scenarios always block"
        elif severity in fail_on:
            item.blocking = True
            item.rule = f"agent_spec fail_on: {fail_on_label}"
        items.append(item)
    return items


def finding_key(finding: dict[str, Any]) -> tuple[Any, ...]:
    """gap-analysis Finding.dedup_key, computed from its JSON form."""
    line = finding.get("line")
    return (
        finding.get("condition_id"),
        finding.get("file"),
        line,
        (finding.get("evidence") or "") if line is None else "",
    )


def _gap_item(
    index: int, finding: dict[str, Any], status: str, fail_on: list[str]
) -> Item:
    severity = _rated(finding.get("severity"))
    location = finding.get("file") or "repo-wide"
    if finding.get("line"):
        location += f":{finding['line']}"
    item = Item(
        id=f"gap:{index}",
        source="gap",
        severity=severity,
        title=f"{finding.get('condition_id')}: {finding.get('title', '')}",
        location=location,
        status=status,
        evidence=[finding["evidence"]] if finding.get("evidence") else [],
        fix=finding.get("remediation") or "",
    )
    if status == "open" and severity in fail_on:
        item.blocking = True
        item.rule = f"gap policy fail_on: {', '.join(fail_on)}"
    return item


def gap_items(
    before: dict[str, Any],
    after: dict[str, Any] | None = None,
    fix_results: dict[str, Any] | None = None,
    fail_on: list[str] | tuple[str, ...] = DEFAULT_GAP_FAIL_ON,
) -> list[Item]:
    """Items from the first gap analysis, marked fixed when the fix run applied
    them or the re-score no longer finds them. Findings that only the re-score
    reports are added as open items."""
    fail_on = list(fail_on)
    applied = {
        tuple(result["key"])
        for result in (fix_results or {}).get("results", [])
        if result.get("status") == "applied"
    }
    after_findings = (after or {}).get("findings")
    after_keys = (
        {finding_key(f) for f in after_findings} if after_findings is not None else None
    )
    before_findings = before.get("findings", [])
    before_keys = {finding_key(f) for f in before_findings}

    items = []
    for index, finding in enumerate(before_findings):
        key = finding_key(finding)
        fixed_by = (
            "codemod"
            if key in applied
            else "re-score"
            if after_keys is not None and key not in after_keys
            else None
        )
        item = _gap_item(index, finding, "fixed" if fixed_by else "open", fail_on)
        item.fixed_by = fixed_by
        items.append(item)
    for offset, finding in enumerate(after_findings or []):
        if finding_key(finding) in before_keys:
            continue
        item = _gap_item(offset, finding, "open", fail_on)
        item.id = f"gap-after:{offset}"
        item.title += " (new after fixes)"
        items.append(item)
    return items
