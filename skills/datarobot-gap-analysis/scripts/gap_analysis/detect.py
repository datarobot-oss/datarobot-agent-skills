# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Layer 2 (LLM reasoning over code) detection runner.

Layer 4 (regulatory) lives entirely in risk_management.py: it's driven by a
live DataRobot risk-management policy rather than taxonomy.yaml conditions,
so it has no LLM-prompt-based runner here.
"""

from __future__ import annotations

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import paths
from .inventory import evidence_files, glob_match
from .llm import LLMClient, brief_error, parse_json
from .models import ConditionSkip, Finding, Severity
from .taxonomy import Condition, Taxonomy

_MAX_FILES = 12  # cap files fed per condition
_DR_APP_CONTEXT_FILE = "prompts/_deployment_datarobot_app.md"
NO_LLM_NOTE = (
    "Layers 2 and 4 (LLM) skipped: no model client. Install the DataRobot CLI "
    "(run the datarobot-setup skill) so checks run through `dr opencode`, or add "
    "`--with litellm` and set DATAROBOT_API_TOKEN / DATAROBOT_ENDPOINT (or GAP_LLM_MODEL "
    "with provider credentials). Half of the framework is not assessed until then."
)
_DEFAULT_MAX_BYTES = 200_000
_DEFAULT_MAX_WORKERS = 4
_SUBMIT_STAGGER_SECONDS = 0.25  # avoid a thundering herd on the LLM backend


def _load_prompt(detector: str) -> str:
    """Load a prompt file, resolving an optional #anchor section."""
    ref, _, anchor = detector.partition("#")
    text = paths.resolve(ref).read_text()
    if not anchor:
        return text
    # Return the section whose heading carries {#anchor}
    sections = text.split("\n## ")
    for sec in sections:
        if f"{{#{anchor}}}" in sec.split("\n", 1)[0]:
            return "## " + sec
    return text


# Test and fixture code is never evidence for a production-readiness check.
_TEST_PATHS = [
    "**/tests/**",
    "**/test/**",
    "**/__tests__/**",
    "**/fixtures/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/conftest.py",
    "**/*.spec.*",
    "**/*.test.*",
]
# Build-time and infrastructure files, skipped for runtime-behaviour checks.
_NON_RUNTIME_PATHS = [
    "**/infra/**",
    "**/migrations/**",
    "**/alembic/**",
    "**/alembic*.py",
    "**/.github/**",
    "**/Taskfile*",
    "**/Pulumi*.yaml",
    "**/Dockerfile*",
]


def layer2_files(
    inventory: dict[str, Any], cond: Condition, limit: int = _MAX_FILES
) -> list[str]:
    """Evidence files for a Layer 2 condition, minus tests and, for runtime
    checks, minus IaC/migration/CI files; a condition whose own globs name test
    or infra paths keeps them."""
    wants_tests = any("test" in g for g in cond.files_glob)
    wants_infra = any("infra" in g for g in cond.files_glob)
    excluded: list[str] = []
    if not wants_tests:
        excluded += _TEST_PATHS
    if cond.runtime_only and not wants_infra:
        excluded += _NON_RUNTIME_PATHS
    return [
        f
        for f in evidence_files(inventory, cond.files_glob, limit * 3)
        if not any(glob_match(f, g) for g in excluded)
    ][:limit]


def _gather_files(
    workspace: Path, inventory: dict[str, Any], cond: Condition, max_bytes: int
) -> list[tuple[str, str]]:
    rels = layer2_files(inventory, cond, _MAX_FILES)
    out = []
    for rel in rels:
        p = workspace / rel
        try:
            data = p.read_text(errors="ignore")
        except Exception:
            continue
        if len(data.encode("utf-8", "ignore")) > max_bytes:
            data = data[:max_bytes] + "\n…[truncated]…"
        # NUL bytes survive errors="ignore" but cannot travel in a subprocess
        # argv (the opencode worker path) and break most JSON transports.
        out.append((rel, data.replace("\x00", "")))
    return out


def number_lines(text: str) -> str:
    return "\n".join(f"{i}| {line}" for i, line in enumerate(text.splitlines(), 1))


_HINT_EXTS = (
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".cfg",
    ".ini",
)
_HINT_MAX_LINES = 40
_HINT_MAX_PER_FILE = 4


def hint_hits(workspace: Path, inventory: dict[str, Any], cond: Condition) -> list[str]:
    """`path:line: text` grep hits for the condition's hint_patterns across the
    repo (tests excluded), so the model sees evidence outside its file cap."""
    if not cond.hint_patterns:
        return []
    try:
        pattern = re.compile("|".join(f"(?:{p})" for p in cond.hint_patterns))
    except re.error:
        return []
    excluded = list(_TEST_PATHS)
    if cond.runtime_only:
        excluded += _NON_RUNTIME_PATHS
    hits: list[str] = []
    for rel in inventory.get("files", []):
        if not rel.endswith(_HINT_EXTS) or any(glob_match(rel, g) for g in excluded):
            continue
        try:
            text = (workspace / rel).read_text(errors="ignore")
        except OSError:
            continue
        per_file = 0
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{rel}:{i}: {line.strip()[:160]}")
                per_file += 1
                if per_file >= _HINT_MAX_PER_FILE:
                    break
        if len(hits) >= _HINT_MAX_LINES:
            break
    return hits[:_HINT_MAX_LINES]


def _build_user_message(
    files: list[tuple[str, str]],
    hints: list[str] | None = None,
    extra_sections: list[tuple[str, str]] | None = None,
) -> str:
    parts = [f"=== FILE: {rel} ===\n{number_lines(content)}" for rel, content in files]
    if hints:
        parts.append(
            "=== REPO-WIDE EVIDENCE HINTS (grep hits from files not shown above) ===\n"
            + "\n".join(hints)
        )
    for title, body in extra_sections or []:
        parts.append(f"=== {title} ===\n{body}")
    return "\n\n".join(parts)


_LINE_PREFIX_RE = re.compile(r"^\s*\d+\|\s?")
_CODE_CHARS = set("()[]{}=:;\"'<>")


def _norm(text: str) -> str:
    return "".join(text.split())


def snap_line(raw: str, item: dict[str, Any]) -> bool | None:
    """Move `line` onto the line that actually holds the quoted evidence.

    Returns True when the evidence was located, False when it looks like code
    but is nowhere in the file, None when it is prose and cannot be checked.
    """
    evidence = str(item.get("evidence") or "")
    candidates = [
        _LINE_PREFIX_RE.sub("", line).strip() for line in evidence.splitlines()
    ]
    candidates = [c for c in candidates if len(c) >= 8 and set(c) & _CODE_CHARS]
    if not candidates:
        return None
    lines = raw.splitlines()
    normalized = [_norm(line) for line in lines]
    for cand in candidates:
        key = _norm(cand)
        for i, line in enumerate(normalized, 1):
            if key and key in line:
                item["line"] = i
                return True
        # Model answers often quote a fragment of a longer statement.
        head = key[:24]
        if len(head) >= 16:
            for i, line in enumerate(normalized, 1):
                if head in line:
                    item["line"] = i
                    return True
    return False


_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]


def lower_severity(sev: Severity) -> Severity:
    i = _SEVERITY_ORDER.index(sev)
    return _SEVERITY_ORDER[min(i + 1, len(_SEVERITY_ORDER) - 1)]


def _group_by_root_cause(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Locations sharing a root cause collapse into one finding listing them."""
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for n, it in enumerate(items):
        key = _norm(str(it.get("root_cause") or "")).lower() or f"__{n}"
        if key not in groups:
            order.append(key)
        groups.setdefault(key, []).append(it)
    out = []
    for key in order:
        grp = groups[key]
        merged = _merge_locations(grp) if len(grp) > 1 else grp[0]
        out.append(merged)
    return out


def _result_to_findings(cond: Condition, result: dict[str, Any]) -> list[Finding]:
    items = list(result.get("findings", []) or [])
    if cond.scope == "repo" and len(items) > 1:
        items = [_merge_locations(items)]
    elif len(items) > 1:
        items = _group_by_root_cause(items)
    findings = []
    for item in items:
        conf = item.get("confidence", "high")
        severity = cond.severity
        if item.get("severity_adjustment") == "lower" or item.get("_weakened"):
            severity = lower_severity(severity)
        explanation = str(item.get("explanation", ""))
        if item.get("severity_reason"):
            explanation += f" Severity lowered: {item['severity_reason']}"
        findings.append(
            Finding(
                condition_id=cond.id,
                pillar=cond.pillar,
                severity=severity,
                title=cond.title,
                file=item.get("file"),
                line=item.get("line"),
                evidence=str(item.get("evidence", ""))[:500],
                explanation=explanation,
                remediation=cond.remediation,
                fix_type=cond.fix_type,
                fix_strategy=cond.fix_strategy,
                fix_risk=cond.fix_risk,
                confidence=conf,
                layer=cond.layer,
                detector=cond.detector,
                root_cause=str(item.get("root_cause") or ""),
                verified=bool(item.get("_verified")),
                verification=str(item.get("_verify_reason") or ""),
                shape=str(item.get("_shape") or ""),
            )
        )
    return findings


_VERIFY_FILE = "prompts/_verify.md"
_VERIFY_CONTEXT_LINES = 80
_VERIFY_WHOLE_FILE_MAX = 250


def verification_enabled() -> bool:
    return os.environ.get("GAP_VERIFY", "on").lower() not in ("off", "0", "false")


def _region(raw: str, line: int | None) -> str:
    lines = raw.splitlines()
    if len(lines) <= _VERIFY_WHOLE_FILE_MAX or not line:
        return number_lines(raw)
    lo = max(1, line - _VERIFY_CONTEXT_LINES)
    hi = min(len(lines), line + _VERIFY_CONTEXT_LINES)
    return "\n".join(f"{i}| {lines[i - 1]}" for i in range(lo, hi + 1))


def verify_item(
    client: LLMClient,
    workspace: Path,
    cond: Condition,
    item: dict[str, Any],
    raw_files: dict[str, str],
    hints: list[str],
) -> str:
    """Second look at one finding. Returns the verdict and annotates `item`
    with `_verified`, `_weakened`, `_verify_reason`, `_shape`, corrected line."""
    rel = item.get("file")
    raw = raw_files.get(rel or "")
    if raw is None and rel:
        try:
            raw = (workspace / rel).read_text(errors="ignore").replace("\x00", "")
        except OSError:
            raw = None
    if raw is None:
        return "unverifiable"
    prompt = paths.resolve(_VERIFY_FILE).read_text()
    system = (
        f"{prompt}\n\n---\n# Condition\n{cond.id}: {cond.title}\n{cond.description}\n"
        "Return ONLY the JSON object."
    )
    finding_text = json.dumps(
        {k: v for k, v in item.items() if not str(k).startswith("_")}, indent=2
    )
    user = (
        f"=== FINDING ===\n{finding_text}\n\n=== FILE REGION: {rel} ===\n"
        f"{_region(raw, item.get('line'))}"
    )
    if hints:
        user += "\n\n=== REPO-WIDE EVIDENCE HINTS ===\n" + "\n".join(hints)
    try:
        verdict_obj = parse_json(client.complete(system, user))
    except Exception as e:  # noqa: BLE001
        item["_verify_reason"] = f"verification failed ({brief_error(e)})"
        return "unverifiable"
    verdict = str(verdict_obj.get("verdict", "confirmed")).lower()
    reason = str(verdict_obj.get("reason") or "")
    line = verdict_obj.get("line")
    if isinstance(line, int) and line > 0:
        item["line"] = line
    shape = str(verdict_obj.get("remediation_shape") or "").lower()
    if shape in ("patch", "structural"):
        item["_shape"] = shape
    if verdict == "refuted":
        item["_verify_reason"] = reason
        return "refuted"
    if verdict == "weakened":
        item["_weakened"] = bool(verdict_obj.get("severity_overstated"))
        item["confidence"] = "low" if item.get("confidence") == "low" else "medium"
        item["_verify_reason"] = reason
    elif reason:
        item["_verify_reason"] = reason
    item["_verified"] = True
    return verdict if verdict in ("confirmed", "weakened") else "confirmed"


def _context_sections(cond: Condition) -> list[tuple[str, str]]:
    if cond.context != "llm_gateway_catalog":
        return []
    from .conformance import llm_gateway_models

    catalog = llm_gateway_models()
    if not catalog:
        return []
    return [
        (
            "KNOWN MODEL IDS (served by the org's DataRobot LLM Gateway; these are "
            "valid identifiers, and pinned when they carry a date or version)",
            "\n".join(catalog),
        )
    ]


def deployment_context(inventory: dict[str, Any]) -> str:
    """Runtime facts the code alone cannot show, as a prompt section, or ''.

    A DataRobot custom application receives identity headers from the
    platform proxy; without saying so, header reads look like trusting
    unauthenticated client input.
    """
    app = inventory.get("datarobot_app")
    if not app:
        return ""
    text = paths.resolve(_DR_APP_CONTEXT_FILE).read_text()
    return (
        "---\n"
        + text.format(resource=app["resource"], file=app["file"]).rstrip()
        + "\n\n"
    )


def run_condition(
    client: LLMClient,
    workspace: Path,
    inventory: dict[str, Any],
    cond: Condition,
    contract: str,
    max_bytes: int,
) -> tuple[list[Finding], ConditionSkip | None, list[str]]:
    """Detect, then verify. Returns (findings, skip, notes)."""
    files = _gather_files(workspace, inventory, cond, max_bytes)
    if not files:
        return [], ConditionSkip(cond.id, "no files matched this condition's globs"), []
    hints = hint_hits(workspace, inventory, cond)
    prompt = _load_prompt(cond.detector)
    system = (
        f"{prompt}\n\n{deployment_context(inventory)}---\n# Output contract\n"
        f"{contract}\n\n"
        f"You are checking condition {cond.id}. Return ONLY the JSON object."
    )
    user = _build_user_message(files, hints, _context_sections(cond))
    try:
        raw = client.complete(system, user)
        result = parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return [], ConditionSkip(cond.id, f"LLM/parse error: {brief_error(e)}"), []
    status = result.get("status", "found")
    if status == "skipped":
        return (
            [],
            ConditionSkip(cond.id, result.get("skip_reason", "model reported skipped")),
            [],
        )
    if status == "not_found":
        return [], None, []

    notes: list[str] = []
    raw_files = dict(files)
    items = list(result.get("findings", []) or [])
    kept = []
    for item in items:
        rel = item.get("file")
        if rel in raw_files:
            located = snap_line(raw_files[rel], item)
            if located is False:
                item["confidence"] = "low"
                item["_verify_reason"] = "quoted evidence was not found in the file"
        kept.append(item)
    items = kept

    if verification_enabled() and items:
        survivors = []
        for item in items:
            verdict = verify_item(client, workspace, cond, item, raw_files, hints)
            if verdict == "refuted":
                notes.append(
                    f"Layer 2: {cond.id} at {item.get('file')} dropped on verification: "
                    f"{item.get('_verify_reason') or 'refuted'}"
                )
                continue
            survivors.append(item)
        items = survivors
    result = dict(result, findings=items)
    return _result_to_findings(cond, result), None, notes


def _merge_locations(items: list[dict[str, Any]]) -> dict[str, Any]:
    """One finding for a repo-wide question, with every location listed."""
    first = dict(items[0])
    locs = []
    for it in items:
        if it.get("file"):
            locs.append(
                f"{it['file']}:{it['line']}" if it.get("line") else str(it["file"])
            )
    shown = ", ".join(locs[:6]) + (f", +{len(locs) - 6} more" if len(locs) > 6 else "")
    first["evidence"] = f"{len(items)} location(s): {shown}. " + str(
        first.get("evidence", "")
    )
    ranks = {"high": 3, "medium": 2, "low": 1}
    first["confidence"] = max(
        (it.get("confidence", "high") for it in items), key=lambda c: ranks.get(c, 0)
    )
    return first


def run_layer2(
    client: LLMClient | None,
    workspace,
    inventory,
    taxonomy: Taxonomy,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    progress=None,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> tuple[list[Finding], list[ConditionSkip], list[str]]:
    notes: list[str] = []
    if client is None:
        skips = [
            ConditionSkip(c.id, "Layer 2 (LLM) not run: no model client configured")
            for c in taxonomy.by_layer(2)
        ]
        notes.append(NO_LLM_NOTE)
        return [], skips, notes
    contract = (paths.prompts_dir() / "_contract.md").read_text()
    workspace = Path(workspace)
    conds = taxonomy.by_layer(2)
    if progress:
        progress(
            f"▶ Layer 2 (LLM reasoning): starting {len(conds)} checks "
            f"({max(1, max_workers)} workers)…"
        )
    results: dict[str, tuple[list[Finding], ConditionSkip | None, list[str]]] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = {}
        for i, cond in enumerate(conds):
            if i:
                time.sleep(_SUBMIT_STAGGER_SECONDS)
            futures[
                pool.submit(
                    run_condition,
                    client,
                    workspace,
                    inventory,
                    cond,
                    contract,
                    max_bytes,
                )
            ] = cond
        for future in as_completed(futures):
            cond = futures[future]
            done += 1
            results[cond.id] = future.result()
            if progress:
                progress(
                    f"Layer 2 (LLM reasoning): {cond.id} done [{done}/{len(conds)}]"
                )

    # Aggregate in taxonomy order so reports stay deterministic across runs.
    findings: list[Finding] = []
    skips: list[ConditionSkip] = []
    dropped = 0
    for cond in conds:
        f, skip, cond_notes = results[cond.id]
        findings += f
        if skip:
            skips.append(skip)
        notes += cond_notes
        dropped += sum(1 for n in cond_notes if "dropped on verification" in n)
    if verification_enabled():
        verified = sum(1 for f in findings if f.verified)
        notes.append(
            f"Layer 2: {verified} finding(s) confirmed by a second verification pass, "
            f"{dropped} dropped as refuted (GAP_VERIFY=off disables the pass)."
        )
    return findings, skips, notes
