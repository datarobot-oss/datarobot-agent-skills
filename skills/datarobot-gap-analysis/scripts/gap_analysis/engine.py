# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level orchestration: analyze() and fix() used by the CLI and the agent tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .conformance import check_conformance
from .detect import run_layer2, run_layer4
from .inventory import build_inventory
from .llm import get_client
from .migrate import extract_spec, scaffold_from_spec
from .models import AnalysisResult
from .policy import load_policy
from .posture import assess_posture
from .remediate import remediate
from .scanners import run_layer1
from .taxonomy import Taxonomy


def analyze(
    workspace: str | Path,
    policy_path: str | None = None,
    llm_client=None,
    use_llm: bool = True,
    progress=None,
) -> tuple[AnalysisResult, dict[str, Any]]:
    """Run all enabled layers over an already-available workspace.

    Returns (result, policy). `llm_client` may be an injected af-component-llm
    callable; otherwise a standalone client is auto-detected. `progress`, if given,
    is called with short status strings as each stage runs (for CLI feedback).
    """

    def _tick(msg: str) -> None:
        if progress:
            progress(msg)

    policy = load_policy(policy_path)
    taxonomy = Taxonomy.load()
    taxonomy.apply_severity_overrides(policy.get("severity_overrides", {}))
    exclude = policy.get("scan", {}).get("exclude", [])
    max_bytes = int(policy.get("scan", {}).get("max_file_bytes", 200_000))

    result = AnalysisResult()
    _tick("Building file inventory…")
    result.inventory = build_inventory(workspace, exclude)

    # Layer 1 — deterministic
    _tick("Layer 1 (scanners: secrets, dependencies, SAST, tests/CI)…")
    f1, n1 = run_layer1(workspace, taxonomy, exclude)
    result.findings += f1
    result.notes += n1

    # Layer 3 — conformance
    _tick("Layer 3 (policy conformance)…")
    f3, n3 = check_conformance(result.inventory, policy, taxonomy)
    result.findings += f3
    result.notes += n3

    # Layers 2 & 4 — LLM reasoning + regulatory
    client = get_client(llm_client) if use_llm else None
    if use_llm and client is None:
        _tick(
            "No LLM client configured — skipping Layers 2 & 4 (set GAP_LLM_MODEL + creds)."
        )
    f2, s2, n2 = run_layer2(
        client, workspace, result.inventory, taxonomy, max_bytes, _tick
    )
    result.findings += f2
    result.skipped += s2
    result.notes += n2

    packs = policy.get("regulatory", {}).get("packs", [])
    f4, s4, n4 = run_layer4(
        client, workspace, result.inventory, taxonomy, packs, max_bytes, _tick
    )
    result.findings += f4
    result.skipped += s4
    result.notes += n4

    result.findings = _dedup(result.findings)
    _tick("Scoring remediation posture…")
    result.posture = assess_posture(result, policy, taxonomy)
    return result, policy


def _dedup(findings):
    """Collapse findings that share (condition_id, file, line)."""
    seen = set()
    out = []
    for f in findings:
        key = (f.condition_id, f.file, f.line)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def fix(
    workspace: str | Path,
    result: AnalysisResult,
    policy: dict[str, Any],
    timestamp: str,
    llm_client=None,
    selected_ids: set[str] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    client = get_client(llm_client) if use_llm else None
    return remediate(
        workspace, result.findings, policy, timestamp, client, selected_ids
    )


def migrate_extract(
    workspace: str | Path,
    result: AnalysisResult,
    policy: dict[str, Any],
    llm_client=None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Extract the agent's business logic into a reviewable migration spec (Part B step 1)."""
    client = get_client(llm_client) if use_llm else None
    max_bytes = int(policy.get("scan", {}).get("max_file_bytes", 120_000))
    return extract_spec(workspace, result.inventory, client, max_bytes)


def migrate_scaffold(
    workspace: str | Path, spec: dict[str, Any], dest: str | Path
) -> dict[str, Any]:
    """Assemble the migration bundle from an (approved) spec (Part B step 3)."""
    return scaffold_from_spec(spec, workspace, dest)
