# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Layer 2 (LLM reasoning over code) detection runner.

Layer 4 (regulatory) lives entirely in risk_management.py: it's driven by a
live DataRobot risk-management policy rather than taxonomy.yaml conditions,
so it has no LLM-prompt-based runner here.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import paths
from .inventory import evidence_files, glob_match
from .llm import LLMClient, brief_error, parse_json
from .models import ConditionSkip, Finding
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


def _build_user_message(files: list[tuple[str, str]]) -> str:
    parts = []
    for rel, content in files:
        parts.append(f"=== FILE: {rel} ===\n{content}")
    return "\n\n".join(parts)


def _result_to_findings(cond: Condition, result: dict[str, Any]) -> list[Finding]:
    items = list(result.get("findings", []) or [])
    if cond.scope == "repo" and len(items) > 1:
        items = [_merge_locations(items)]
    findings = []
    for item in items:
        conf = item.get("confidence", "high")
        findings.append(
            Finding(
                condition_id=cond.id,
                pillar=cond.pillar,
                severity=cond.severity,
                title=cond.title,
                file=item.get("file"),
                line=item.get("line"),
                evidence=str(item.get("evidence", ""))[:500],
                explanation=str(item.get("explanation", "")),
                remediation=cond.remediation,
                fix_type=cond.fix_type,
                fix_strategy=cond.fix_strategy,
                fix_risk=cond.fix_risk,
                confidence=conf,
                layer=cond.layer,
                detector=cond.detector,
            )
        )
    return findings


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
) -> tuple[list[Finding], ConditionSkip | None]:
    files = _gather_files(workspace, inventory, cond, max_bytes)
    if not files:
        return [], ConditionSkip(cond.id, "no files matched this condition's globs")
    prompt = _load_prompt(cond.detector)
    system = (
        f"{prompt}\n\n{deployment_context(inventory)}---\n# Output contract\n"
        f"{contract}\n\n"
        f"You are checking condition {cond.id}. Return ONLY the JSON object."
    )
    user = _build_user_message(files)
    try:
        raw = client.complete(system, user)
        result = parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return [], ConditionSkip(cond.id, f"LLM/parse error: {brief_error(e)}")
    status = result.get("status", "found")
    if status == "skipped":
        return [], ConditionSkip(
            cond.id, result.get("skip_reason", "model reported skipped")
        )
    if status == "not_found":
        return [], None
    return _result_to_findings(cond, result), None


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
    results: dict[str, tuple[list[Finding], ConditionSkip | None]] = {}
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
    for cond in conds:
        f, skip = results[cond.id]
        findings += f
        if skip:
            skips.append(skip)
    return findings, skips, notes
