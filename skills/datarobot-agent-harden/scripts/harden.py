#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic helpers for the datarobot-agent-harden skill.

Subcommands:
  preflight   check the project and locate the two parent skills
  suite-load  add saved breach cases from user_datasets/ to the swarm candidates
  suite-save  save this run's swarm breaches to user_datasets/ as regression cases
  match       build one fix list from swarm breaches and gap-analysis findings
  decide      record whether a swarm breach and a gap finding share a root cause
  verdict     compute the readiness verdict and list the parent skills' reports
  report      write harden-report.md: verdict, one fix list, both checks' sections

Standard library only, so it runs with any Python 3.11+ without installs. The
one exception is `report`, which imports the parent skills' Markdown renderers
and so needs pydantic and PyYAML; simulate's prerequisite check installs both
into the same `<python>`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from report_model import (
    DEFAULT_GAP_FAIL_ON,
    TRACK_CONDITIONS,
    gap_items,
    has_gap,
    merge_pairs,
    sort_items,
    swarm_items,
)

SPEC_NAMES = ("agent_spec.yaml", "agent_spec.md")
IMPLEMENTATION_NAMES = ("agent.py", "myagent.py", "tools.py", "app.py")
HARDEN_DIR = Path(".datarobot/harden")
DATASETS_DIR = Path("user_datasets")
SUITE_FILE = "suite.json"
SWARM_PIPELINE = "swarm"

# Files the two parent skills write into the project. They are added to the
# repository's local exclude file (.git/info/exclude, never committed) so the
# clean-worktree check that gap-analysis --fix runs does not trip over them.
GENERATED_PATTERNS = (
    "/.datarobot/swarm/",
    "/.datarobot/harden/",
    "/agent_config.yaml",
    "/evaluation_criteria.md",
    "/eval_report.md",
    "/eval-results.json",
    "/user_context.txt",
    "/gap-report*.md",
    "/gap-report*.html",
    "/gap-findings.json",
)
EXCLUDE_MARKER = "# datarobot-agent-harden generated files"

GAP_BEFORE_FILE = "gap-findings-before.json"
CANDIDATES_FILE = "fix-candidates.json"
REPORT_FILE = "harden-report.md"
PROPOSAL_FIELDS = (
    "name",
    "track",
    "capability_targeted",
    "turns",
    "expected_safe_behavior",
    "breach_indicators",
    "max_turns",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def _find_spec(root: Path) -> Path | None:
    for name in SPEC_NAMES:
        if (root / name).is_file():
            return root / name
    return None


def _swarm_dir(root: Path) -> Path:
    """Mirror agent-assist-simulate's artifacts.resolve_swarm_dir without side effects."""
    pointer = root / ".datarobot" / "swarm" / "swarm_temp"
    if pointer.is_file():
        return Path(pointer.read_text(encoding="utf-8").strip())
    return root / ".datarobot" / "swarm"


def _locate_parent_skills(skill_dir: Path) -> dict[str, str | None]:
    """Find the parent skills next to this one (repo checkout or plugin install)."""
    skills_root = skill_dir.parent
    candidates = {
        "simulate": skills_root / "datarobot-agent-assist" / "agent-assist-simulate",
        "gap_analysis": skills_root / "datarobot-gap-analysis",
    }
    return {
        key: str(path / "scripts") if (path / "SKILL.md").is_file() else None
        for key, path in candidates.items()
    }


def _add_local_excludes(root: Path) -> bool:
    result = _git(root, "rev-parse", "--git-path", "info/exclude")
    if result.returncode != 0:
        return False
    exclude = Path(result.stdout.strip())
    if not exclude.is_absolute():
        exclude = root / exclude
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if EXCLUDE_MARKER in existing:
        return False
    exclude.parent.mkdir(parents=True, exist_ok=True)
    block = "\n".join((EXCLUDE_MARKER, *GENERATED_PATTERNS))
    separator = "" if not existing or existing.endswith("\n") else "\n"
    exclude.write_text(f"{existing}{separator}{block}\n", encoding="utf-8")
    return True


def preflight(root: Path, skill_dir: Path) -> dict[str, Any]:
    """Report whether the project can be hardened; never modifies tracked files."""
    problems: list[str] = []
    spec = _find_spec(root)
    if spec is None:
        problems.append("no agent_spec.yaml or agent_spec.md; design the agent first")
    elif "system_prompt" not in spec.read_text(encoding="utf-8"):
        problems.append(f"{spec.name} has no system_prompt")
    implementation = [n for n in IMPLEMENTATION_NAMES if (root / n).is_file()]
    if not implementation:
        problems.append(
            "no implementation file (agent.py, myagent.py, tools.py, app.py)"
        )

    parents = _locate_parent_skills(skill_dir)
    problems.extend(
        f"parent skill not installed: {key}"
        for key, path in parents.items()
        if not path
    )

    is_git = _git(root, "rev-parse", "--is-inside-work-tree").returncode == 0
    excludes_added = False
    dirty: list[str] = []
    branch = None
    if is_git:
        excludes_added = _add_local_excludes(root)
        status = _git(root, "status", "--porcelain", "--untracked-files=all")
        dirty = [line[3:] for line in status.stdout.splitlines() if line.strip()]
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    return {
        "ok": not problems,
        "problems": problems,
        "spec": str(spec) if spec else None,
        "implementation": [str(root / n) for n in implementation],
        "parent_skill_scripts": parents,
        "git": {
            "is_repo": is_git,
            "branch": branch,
            "clean": is_git and not dirty,
            "dirty": dirty[:20],
            "local_excludes_added": excludes_added,
        },
    }


def _suite_path(root: Path) -> Path:
    return root / DATASETS_DIR / SUITE_FILE


def _load_suite(root: Path) -> dict[str, Any]:
    path = _suite_path(root)
    if path.is_file():
        suite: dict[str, Any] = _load_json(path)
        return suite
    return {"schema_version": 1, "datasets": []}


def suite_load(root: Path) -> dict[str, Any]:
    """Append saved swarm regression cases to this run's candidates.json."""
    candidates_path = _swarm_dir(root) / "candidates.json"
    if not candidates_path.is_file():
        raise ValueError(f"{candidates_path} not found; run simulate finalize first")
    candidates = _load_json(candidates_path)
    names = {s["name"] for s in candidates.get("scenarios", [])}
    added: list[str] = []
    for entry in _load_suite(root).get("datasets", []):
        if entry.get("pipeline") != SWARM_PIPELINE:
            continue
        dataset = root / DATASETS_DIR / entry["file"]
        if not dataset.is_file():
            continue
        for scenario in _load_json(dataset).get("scenarios", []):
            if scenario["name"] in names:
                continue
            proposal = {k: scenario[k] for k in PROPOSAL_FIELDS if k in scenario}
            candidates["scenarios"].append(proposal)
            names.add(scenario["name"])
            added.append(scenario["name"])
    if added:
        _write_json(candidates_path, candidates)
    return {"added": added, "candidates": str(candidates_path)}


def _breached_results(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Scenarios that breached in the first swarm pass, before any fix."""
    return [
        result
        for result in state.get("initial_results", {}).get("scenarios", [])
        if result.get("status") in ("breach", "exhausted")
    ]


def _state_path(root: Path) -> Path:
    return _swarm_dir(root) / "convergence" / "state.json"


def suite_save(root: Path) -> dict[str, Any]:
    """Save first-pass swarm breaches as a dataset and list it in the suite manifest."""
    state = _load_json(_state_path(root))
    suite = _load_suite(root)
    already = {
        scenario["name"]
        for entry in suite["datasets"]
        if entry.get("pipeline") == SWARM_PIPELINE
        and (root / DATASETS_DIR / entry["file"]).is_file()
        for scenario in _load_json(root / DATASETS_DIR / entry["file"]).get(
            "scenarios", []
        )
    }
    scenarios = []
    for result in _breached_results(state):
        scenario = result["scenario"]
        if scenario["name"] in already:
            continue
        saved = {k: scenario[k] for k in PROPOSAL_FIELDS if k in scenario}
        saved["origin"] = {
            "scenario_id": scenario.get("scenario_id"),
            "breach_reason": result.get("breach_reason")
            or result.get("evaluation_reason"),
            "severity": result.get("severity"),
        }
        scenarios.append(saved)
    if not scenarios:
        return {"saved": 0, "dataset": None, "suite": str(_suite_path(root))}

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    file_name = f"swarm-breaches-{stamp}.json"
    _write_json(
        root / DATASETS_DIR / file_name,
        {"pipeline": SWARM_PIPELINE, "created_at": stamp, "scenarios": scenarios},
    )
    suite["datasets"].append(
        {
            "file": file_name,
            "pipeline": SWARM_PIPELINE,
            "created_at": stamp,
            "count": len(scenarios),
        }
    )
    _write_json(_suite_path(root), suite)
    return {
        "saved": len(scenarios),
        "dataset": str(root / DATASETS_DIR / file_name),
        "suite": str(_suite_path(root)),
    }


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z_][a-z0-9_]{3,}", text.lower())}


def _breach_terms(result: dict[str, Any]) -> set[str]:
    scenario = result["scenario"]
    tools = {
        call.get("tool_name", "") for call in result.get("attempted_tool_calls", [])
    }
    capability = scenario.get("capability_targeted") or ""
    return {t.lower() for t in tools | {capability} if t}


def match(root: Path, gap_findings: Path) -> dict[str, Any]:
    """Pair swarm breaches with gap findings that likely share a root cause."""
    state = _load_json(_state_path(root))
    breaches = [
        r
        for r in state.get("latest_results", [])
        if r.get("status") in ("breach", "exhausted")
    ]
    gap = _load_json(gap_findings)
    findings = gap.get("findings", [])
    # A later re-score writes gap-findings.json again in the same place; keep
    # this first run so the report can tell fixed findings from open ones.
    _write_json(root / HARDEN_DIR / GAP_BEFORE_FILE, gap)

    items: list[dict[str, Any]] = []
    matched_findings: set[int] = set()
    for result in breaches:
        scenario = result["scenario"]
        prefixes = TRACK_CONDITIONS.get(scenario["track"], ())
        terms = _breach_terms(result)
        related = []
        for index, finding in enumerate(findings):
            if not finding["condition_id"].startswith(prefixes):
                continue
            text = " ".join(
                str(finding.get(k) or "")
                for k in ("title", "evidence", "explanation", "file")
            )
            shared = terms & _words(text)
            if shared:
                related.append({"finding_index": index, "shared_terms": sorted(shared)})
                matched_findings.add(index)
        items.append(
            {
                "source": "swarm",
                "scenario_id": scenario.get("scenario_id"),
                "name": scenario["name"],
                "track": scenario["track"],
                "status": result["status"],
                "severity": result.get("severity"),
                "reason": result.get("breach_reason")
                or result.get("evaluation_reason"),
                "possibly_same_root_cause_as": related,
                "decisions": [],
            }
        )

    for index, finding in enumerate(findings):
        items.append(
            {
                "source": "gap-analysis",
                "finding_index": index,
                "condition_id": finding["condition_id"],
                "title": finding["title"],
                "severity": finding["severity"],
                "location": f"{finding.get('file') or ''}"
                + (f":{finding['line']}" if finding.get("line") else ""),
                "fix_type": finding.get("fix_type", "advisory"),
                "structural": finding.get("structural", False),
                "matched_swarm_breach": index in matched_findings,
            }
        )
    output = root / HARDEN_DIR / CANDIDATES_FILE
    _write_json(output, {"items": items})
    return {
        "swarm_breaches": len(breaches),
        "gap_findings": len(findings),
        "suggested_overlaps": len(matched_findings),
        "fix_candidates": str(output),
    }


def decide(
    root: Path, scenario_id: str, finding_index: int, same_root_cause: bool
) -> dict[str, Any]:
    """Record the agent's judgment on one swarm breach / gap finding pair."""
    path = root / HARDEN_DIR / CANDIDATES_FILE
    if not path.is_file():
        raise ValueError(f"{path} not found; run match first")
    candidates = _load_json(path)
    items = candidates.get("items", [])
    swarm = next(
        (
            i
            for i in items
            if i.get("source") == "swarm" and i.get("scenario_id") == scenario_id
        ),
        None,
    )
    if swarm is None:
        raise ValueError(f"no swarm breach {scenario_id} in {path.name}")
    if not any(
        i.get("source") == "gap-analysis" and i.get("finding_index") == finding_index
        for i in items
    ):
        raise ValueError(f"no gap finding {finding_index} in {path.name}")
    decisions = [
        d
        for d in swarm.setdefault("decisions", [])
        if d.get("finding_index") != finding_index
    ]
    decisions.append(
        {"finding_index": finding_index, "same_root_cause": same_root_cause}
    )
    swarm["decisions"] = decisions
    _write_json(path, candidates)
    return {
        "scenario_id": scenario_id,
        "finding_index": finding_index,
        "same_root_cause": same_root_cause,
        "decisions": len(decisions),
    }


def _link(path: Path | None) -> str | None:
    return path.resolve().as_uri() if path and path.exists() else None


def _load_optional(path: Path | None) -> Any:
    return _load_json(path) if path and path.is_file() else None


def _gap_inputs(
    root: Path, gap_findings: Path
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    """(first gap run, re-score or None, --fix results or None)."""
    before_path = root / HARDEN_DIR / GAP_BEFORE_FILE
    latest = _load_json(gap_findings)
    before = _load_optional(before_path)
    if before is None:
        before, after = latest, None
    else:
        after = None if latest == before else latest
    fix_results = _load_optional(gap_findings.parent / "gap-fix-results.json")
    return before, after, fix_results


def _build(
    root: Path,
    eval_summary: Path,
    gap_findings: Path,
    gap_fail_on: list[str],
) -> dict[str, Any]:
    swarm = _load_json(eval_summary)
    results_path = swarm.get("results_path")
    eval_results = _load_optional(Path(results_path)) if results_path else None
    before, after, fix_results = _gap_inputs(root, gap_findings)
    items = gap_items(before, after, fix_results, gap_fail_on)
    if eval_results is not None:
        items = swarm_items(eval_results) + items
    items = merge_pairs(items, _load_optional(root / HARDEN_DIR / CANDIDATES_FILE))
    return {
        "swarm": swarm,
        "eval_results": eval_results,
        "gap_final": after or before,
        "fix_results": fix_results,
        "items": sort_items(items),
    }


def _verdict_from(
    root: Path,
    built: dict[str, Any],
    gap_reports: list[Path],
    fix_branch: str | None,
) -> dict[str, Any]:
    swarm = built["swarm"]
    gap = built["gap_final"]
    items = built["items"]
    posture = (gap.get("posture") or {}).get("recommendation")

    reasons: list[str] = []
    by_rule: dict[str, list[Any]] = {}
    for item in items:
        if item.blocking:
            by_rule.setdefault(item.rule or "blocking", []).append(item)
    for rule, blocked in by_rule.items():
        names = ", ".join(i.title for i in blocked[:3])
        more = f" and {len(blocked) - 3} more" if len(blocked) > 3 else ""
        reasons.append(f"{rule}: {names}{more}")
    if built["eval_results"] is None and not swarm.get("ready"):
        reasons.append(
            f"swarm: {swarm.get('passed', 0)}/{swarm.get('total', 0)} scenarios passed, "
            f"{swarm.get('exhausted', 0)} unresolved, {swarm.get('errored', 0)} errored"
        )
    if posture and str(posture).upper().replace("-", "_") == "RE_PLATFORM":
        reasons.append("gap analysis: remediation posture is Re-platform")

    warnings: list[str] = []
    open_gap = [i for i in items if has_gap(i) and i.status == "open"]
    non_blocking_gap = [i for i in open_gap if not i.blocking]
    if non_blocking_gap:
        warnings.append(
            f"gap analysis: {len(non_blocking_gap)} non-blocking findings open"
        )
    swarm_warnings = [
        i
        for i in items
        if i.source == "swarm" and i.status in ("warning", "open") and not i.blocking
    ]
    if swarm_warnings:
        warnings.append(
            f"swarm: {len(swarm_warnings)} scored or non-blocking scenario findings"
        )
    if gap.get("skipped"):
        warnings.append(f"gap analysis: {len(gap['skipped'])} checks were skipped")

    status = (
        "NOT READY" if reasons else ("READY WITH WARNINGS" if warnings else "READY")
    )
    reports = {
        "swarm_eval_report": _link(Path(swarm["report_path"]))
        if swarm.get("report_path")
        else None,
        "gap_analysis_reports": [
            link for link in (_link(p) for p in gap_reports) if link
        ],
        "regression_suite": _link(_suite_path(root)),
    }
    return {
        "verdict": status,
        "blocking": reasons,
        "warnings": warnings,
        "swarm": {
            k: swarm.get(k)
            for k in ("ready", "total", "passed", "breached", "exhausted", "errored")
        },
        "gap_analysis": {
            "findings": len(gap.get("findings", [])),
            "open_blocking": sum(1 for i in open_gap if i.blocking),
            "fixed": sum(1 for i in items if has_gap(i) and i.status == "fixed"),
            "posture": posture,
        },
        "fix_branch": fix_branch,
        "reports": reports,
    }


def verdict(
    root: Path,
    eval_summary: Path,
    gap_findings: Path,
    gap_reports: list[Path],
    fix_branch: str | None,
    gap_fail_on: list[str] | None = None,
) -> dict[str, Any]:
    """One readiness verdict from both checks, with links to their own reports."""
    built = _build(
        root, eval_summary, gap_findings, gap_fail_on or list(DEFAULT_GAP_FAIL_ON)
    )
    return _verdict_from(root, built, gap_reports, fix_branch)


_SEV_LABEL = {
    "critical": "🟥 critical",
    "high": "🟧 high",
    "medium": "🟨 medium",
    "low": "⬜ low",
}
_STATUS_LABEL = {
    "exhausted": "UNRESOLVED",
    "error": "ERRORED",
    "open": "OPEN",
    "warning": "WARNING",
    "fixed": "FIXED",
}


def _import_renderers(skill_dir: Path) -> tuple[Any, Any, str]:
    """(swarm section renderer, gap section renderer, gap disclaimer), taken from
    the parent skills so the merged report shows exactly what they render."""
    parents = _locate_parent_skills(skill_dir)
    for key in ("simulate", "gap_analysis"):
        if not parents[key]:
            raise ValueError(f"parent skill not installed: {key}")
        if parents[key] not in sys.path:
            sys.path.insert(0, str(parents[key]))
    os.environ.setdefault("GAP_DATA_DIR", str(parents["gap_analysis"]))
    try:
        from gap_analysis.models import AnalysisResult
        from gap_analysis.report import DISCLAIMER, render_report
        from swarm_contracts import EvalReportData
        from write_report import render_markdown
    except ImportError as exc:
        raise ValueError(
            f"report needs pydantic and PyYAML in this Python ({exc}); "
            "run simulate's prerequisite check first"
        ) from exc

    def swarm_section(data: dict[str, Any]) -> str:
        return str(
            render_markdown(
                EvalReportData.model_validate(data), heading_offset=1, standalone=False
            )
        )

    def gap_section(data: dict[str, Any]) -> str:
        return str(
            render_report(
                AnalysisResult.from_dict(data),
                heading_offset=1,
                standalone=False,
                fix_commands=False,
            )
        )

    return swarm_section, gap_section, str(DISCLAIMER)


def _fix_list(items: list[Any]) -> list[str]:
    if not items:
        return ["No swarm breaches or gap findings.", ""]
    lines = []
    for number, item in enumerate(items, start=1):
        severity = _SEV_LABEL.get(item.severity or "", "unrated")
        head = f"{number}. **{_STATUS_LABEL[item.status]}** · {severity} · {item.source} — {item.title}"
        lines.append(head)
        if item.blocking:
            lines.append(f"   - **Blocks deploy:** {item.rule}")
        lines.append(f"   - **Where:** {item.location}")
        for evidence in item.evidence[:3]:
            lines.append(f"   - **Evidence:** {evidence}")
        if item.fix:
            label = "Fix applied" if item.status == "fixed" else "Fix"
            lines.append(f"   - **{label}:** {item.fix}")
        if item.related:
            lines.append(f"   - **Related:** {', '.join(item.related)}")
    lines.append("")
    return lines


def _changes(built: dict[str, Any], fix_branch: str | None) -> list[str]:
    lines = [f"Branch: `{fix_branch}`" if fix_branch else "No fix branch.", ""]
    swarm_changes = (built["eval_results"] or {}).get("changes") or []
    for change in swarm_changes:
        files = ", ".join(f"`{f}`" for f in change["files"])
        lines.append(
            f"- Swarm `{change['scenario_id']}` ({change['kind']}): {change['summary']} [{files}]"
        )
    fix_results = built["fix_results"] or {}
    for result in fix_results.get("results", []):
        if result.get("status") == "applied":
            lines.append(
                f"- Gap `{result['condition_id']}` (codemod): {result['message']}"
            )
    for item in built["items"]:
        if has_gap(item) and item.fixed_by == "re-score":
            lines.append(f"- Gap {item.title}: no longer found on re-score")
    if len(lines) == 2:
        lines.append("No changes applied.")
    if fix_results.get("diff_stat"):
        lines += ["", "```", fix_results["diff_stat"].rstrip(), "```"]
    lines.append("")
    return lines


def report(
    root: Path,
    eval_summary: Path,
    gap_findings: Path,
    gap_reports: list[Path],
    fix_branch: str | None,
    output: Path,
    gap_fail_on: list[str] | None = None,
) -> dict[str, Any]:
    """Write one Markdown report with the verdict, the combined fix list and the
    sections of both parent reports; return the verdict with its link added."""
    swarm_section, gap_section, disclaimer = _import_renderers(
        Path(__file__).resolve().parent.parent
    )
    built = _build(
        root, eval_summary, gap_findings, gap_fail_on or list(DEFAULT_GAP_FAIL_ON)
    )
    result = _verdict_from(root, built, gap_reports, fix_branch)
    items = built["items"]

    lines = [
        "# Agent Hardening Report",
        "",
        f"- Project: `{root}`",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- Fix branch: {f'`{fix_branch}`' if fix_branch else 'no changes'}",
        "",
        "## Verdict",
        "",
        f"**{result['verdict']}**",
        "",
        "Blocking:",
        *(f"- {r}" for r in result["blocking"] or ["none"]),
        "",
        "Warnings:",
        *(f"- {w}" for w in result["warnings"] or ["none"]),
        "",
        (
            "Rules: a swarm breach blocks when its severity is in the agent spec's "
            "`fail_on`; exhausted and errored swarm scenarios always block; a gap "
            "finding blocks when its severity is in the gap policy's `fail_on`."
        ),
        "",
        "## Fix List",
        "",
        *_fix_list(items),
        "## Changes on the Fix Branch",
        "",
        *_changes(built, fix_branch),
        "## Swarm Simulation",
        "",
    ]
    if built["eval_results"] is not None:
        lines += [swarm_section(built["eval_results"]), ""]
    else:
        lines += [
            (
                "Detailed swarm results were not saved (no `results_path`); see "
                "the swarm report linked below."
            ),
            "",
        ]
    lines += ["## Gap Analysis", "", gap_section(built["gap_final"]), ""]
    suite = _load_suite(root)
    lines += [
        "## Regression Suite",
        "",
        (
            f"{sum(d.get('count', 0) for d in suite['datasets'])} saved breach "
            f"case(s) in {len(suite['datasets'])} dataset(s): "
            f"`{DATASETS_DIR / SUITE_FILE}`"
        ),
        "",
        "## Source Reports",
        "",
    ]
    links = result["reports"]
    lines.append(f"- Swarm simulation: {links['swarm_eval_report'] or 'not found'}")
    lines.extend(f"- Gap analysis: {link}" for link in links["gap_analysis_reports"])
    lines += ["", "---", disclaimer, ""]

    resolved = output if output.is_absolute() else root / output
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text("\n".join(lines), encoding="utf-8")
    result["reports"]["harden_report"] = resolved.resolve().as_uri()
    return result


def _add_verdict_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--eval-summary", type=Path, required=True)
    parser.add_argument("--gap-findings", type=Path, required=True)
    parser.add_argument("--gap-report", type=Path, action="append", default=[])
    parser.add_argument("--fix-branch")
    parser.add_argument(
        "--gap-fail-on",
        default=",".join(DEFAULT_GAP_FAIL_ON),
        help="gap severities that block, as in the gap policy's report.fail_on "
        "(default: critical,high, the gap-analysis default)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project", type=Path, default=Path("."), help="agent project root"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight")
    sub.add_parser("suite-load")
    sub.add_parser("suite-save")
    match_parser = sub.add_parser("match")
    match_parser.add_argument("--gap-findings", type=Path, required=True)
    _add_verdict_args(sub.add_parser("verdict"))
    decide_parser = sub.add_parser("decide")
    decide_parser.add_argument("--scenario", required=True, help="swarm scenario_id")
    decide_parser.add_argument(
        "--finding", type=int, required=True, help="gap finding_index"
    )
    same = decide_parser.add_mutually_exclusive_group(required=True)
    same.add_argument("--same", action="store_true", help="same root cause")
    same.add_argument("--different", action="store_true", help="different causes")
    report_parser = sub.add_parser("report")
    _add_verdict_args(report_parser)
    report_parser.add_argument("--output", type=Path, default=Path(REPORT_FILE))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one harden helper subcommand and print its JSON result."""
    args = _build_parser().parse_args(argv)
    root = args.project.resolve()
    try:
        result: dict[str, Any]
        if args.command == "preflight":
            result = preflight(root, Path(__file__).resolve().parent.parent)
        elif args.command == "suite-load":
            result = suite_load(root)
        elif args.command == "suite-save":
            result = suite_save(root)
        elif args.command == "match":
            result = match(root, args.gap_findings)
        elif args.command == "decide":
            result = decide(root, args.scenario, args.finding, args.same)
        else:
            gap_fail_on = [s.strip() for s in args.gap_fail_on.split(",") if s.strip()]
            common = (
                root,
                args.eval_summary,
                args.gap_findings,
                args.gap_report,
                args.fix_branch,
            )
            if args.command == "verdict":
                result = verdict(*common, gap_fail_on=gap_fail_on)
            else:
                result = report(*common, args.output, gap_fail_on=gap_fail_on)
    except (OSError, ValueError, KeyError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
