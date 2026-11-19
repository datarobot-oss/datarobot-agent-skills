#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic helpers for the datarobot-agent-harden skill.

Subcommands:
  preflight   check the project and locate the two parent skills
  suite-load  add saved breach cases from user_datasets/ to the swarm candidates
  suite-save  save this run's swarm breaches to user_datasets/ as regression cases
  match       build one fix list from swarm breaches and gap-analysis findings
  verdict     compute the readiness verdict and list the parent skills' reports

Standard library only, so it runs with any Python 3.11+ without installs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    "/user_context.txt",
    "/gap-report*.md",
    "/gap-report*.html",
    "/gap-findings.json",
)
EXCLUDE_MARKER = "# datarobot-agent-harden generated files"

# Gap-analysis condition prefixes that describe the same weakness a swarm track
# probes. Used only to suggest overlap; the agent confirms each pairing.
TRACK_CONDITIONS: dict[str, tuple[str, ...]] = {
    "attack": ("SEC-011", "SEC-012", "SEC-001", "IDN-", "AIG-"),
    "behavior": ("SEC-012", "AIG-", "REL-"),
    "persistence": ("AIG-", "SEC-011"),
}
BLOCKING_SEVERITIES = ("critical", "high")
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
    findings = _load_json(gap_findings).get("findings", [])

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
    output = root / HARDEN_DIR / "fix-candidates.json"
    _write_json(output, {"items": items})
    return {
        "swarm_breaches": len(breaches),
        "gap_findings": len(findings),
        "suggested_overlaps": len(matched_findings),
        "fix_candidates": str(output),
    }


def _link(path: Path | None) -> str | None:
    return path.resolve().as_uri() if path and path.exists() else None


def verdict(
    root: Path,
    eval_summary: Path,
    gap_findings: Path,
    gap_reports: list[Path],
    fix_branch: str | None,
) -> dict[str, Any]:
    """One readiness verdict from both checks, with links to their own reports."""
    swarm = _load_json(eval_summary)
    gap = _load_json(gap_findings)
    findings = gap.get("findings", [])
    posture = (gap.get("posture") or {}).get("recommendation")
    blocking = [f for f in findings if f.get("severity") in BLOCKING_SEVERITIES]
    medium = [f for f in findings if f.get("severity") == "medium"]

    reasons = []
    if not swarm.get("ready"):
        reasons.append(
            f"swarm: {swarm.get('passed', 0)}/{swarm.get('total', 0)} scenarios passed, "
            f"{swarm.get('exhausted', 0)} unresolved, {swarm.get('errored', 0)} errored"
        )
    if blocking:
        reasons.append(f"gap analysis: {len(blocking)} critical/high findings open")
    if posture and str(posture).upper().replace("-", "_") == "RE_PLATFORM":
        reasons.append("gap analysis: remediation posture is Re-platform")
    warnings = []
    if medium:
        warnings.append(f"gap analysis: {len(medium)} medium findings open")
    if gap.get("skipped"):
        warnings.append(f"gap analysis: {len(gap['skipped'])} checks were skipped")

    if reasons:
        status = "NOT READY"
    elif warnings:
        status = "READY WITH WARNINGS"
    else:
        status = "READY"

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
            "findings": len(findings),
            "critical_high": len(blocking),
            "posture": posture,
        },
        "fix_branch": fix_branch,
        "reports": reports,
    }


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
    verdict_parser = sub.add_parser("verdict")
    verdict_parser.add_argument("--eval-summary", type=Path, required=True)
    verdict_parser.add_argument("--gap-findings", type=Path, required=True)
    verdict_parser.add_argument("--gap-report", type=Path, action="append", default=[])
    verdict_parser.add_argument("--fix-branch")
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
        else:
            result = verdict(
                root,
                args.eval_summary,
                args.gap_findings,
                args.gap_report,
                args.fix_branch,
            )
    except (OSError, ValueError, KeyError) as exc:
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
