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
from .inventory import files_matching
from .llm import LLMClient, parse_json
from .models import ConditionSkip, Finding
from .taxonomy import Condition, Taxonomy

_MAX_FILES = 12  # cap files fed per condition
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


def _gather_files(
    workspace: Path, inventory: dict[str, Any], cond: Condition, max_bytes: int
) -> list[tuple[str, str]]:
    rels = files_matching(inventory, cond.files_glob)[:_MAX_FILES]
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
    findings = []
    for item in result.get("findings", []) or []:
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
        f"{prompt}\n\n---\n# Output contract\n{contract}\n\n"
        f"You are checking condition {cond.id}. Return ONLY the JSON object."
    )
    user = _build_user_message(files)
    try:
        raw = client.complete(system, user)
        result = parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return [], ConditionSkip(cond.id, f"LLM/parse error: {e}")
    status = result.get("status", "found")
    if status == "skipped":
        return [], ConditionSkip(
            cond.id, result.get("skip_reason", "model reported skipped")
        )
    if status == "not_found":
        return [], None
    return _result_to_findings(cond, result), None


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
            ConditionSkip(c.id, "Layer 2 (LLM) not run — no model client configured")
            for c in taxonomy.by_layer(2)
        ]
        notes.append("Layer 2 (LLM) skipped — no model client configured.")
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
