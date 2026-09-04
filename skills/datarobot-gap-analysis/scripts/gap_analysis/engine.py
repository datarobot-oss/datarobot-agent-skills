# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level orchestration: analyze() and fix() used by the CLI and the agent tools."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .conformance import check_conformance
from .detect import NO_LLM_NOTE, run_layer2
from .inventory import build_inventory
from .llm import get_client
from .migrate import extract_spec, scaffold_from_spec
from .models import AnalysisResult
from .policy import load_policy
from .posture import assess_posture
from .remediate import remediate
from .risk_management import EU_AI_ACT_POLICY_NAME, run_dynamic_layer4
from .scanners import run_layer1
from .taxonomy import Taxonomy


def analyze(
    workspace: str | Path,
    policy_path: str | None = None,
    llm_client=None,
    use_llm: bool = True,
    progress=None,
    max_workers: int = 4,
) -> tuple[AnalysisResult, dict[str, Any]]:
    """Run all enabled layers over an already-available workspace.

    Returns (result, policy). `llm_client` may be an injected af-component-llm
    callable; otherwise a standalone client is auto-detected. `progress`, if given,
    is called with short status strings as each stage runs (for CLI feedback).
    """

    def _tick(msg: str) -> None:
        if progress:
            progress(msg)

    def _phase(label: str, started: float, detail: str) -> None:
        # One distinct, greppable line per completed phase: progress monitors
        # should match on "✓" to get phase-level events instead of per-check spam.
        _tick(f"✓ {label} complete — {detail} in {time.monotonic() - started:.1f}s")

    policy = load_policy(policy_path)
    taxonomy = Taxonomy.load()
    taxonomy.apply_severity_overrides(policy.get("severity_overrides", {}))
    exclude = policy.get("scan", {}).get("exclude", [])
    max_bytes = int(policy.get("scan", {}).get("max_file_bytes", 200_000))

    result = AnalysisResult()
    t0 = time.monotonic()
    _tick("▶ Indexing repository files…")
    result.inventory = build_inventory(workspace, exclude)
    _phase("repo index", t0, f"{len(result.inventory.get('files', []))} files")

    # The layers only read the inventory and are independent of each other, so
    # they run in three concurrent lanes: Layer 1 (subprocess scanners, often
    # the slowest), Layer 3 (instant), and Layers 2+4 sequentially in one lane
    # so LLM concurrency stays at `max_workers` rather than doubling.
    def _lane_layer1():
        started = time.monotonic()
        _tick("▶ Layer 1 (scanners): secrets, dependencies, SAST, tests/CI…")
        f1, n1 = run_layer1(workspace, taxonomy, exclude, progress=_tick, policy=policy)
        _phase("Layer 1 (scanners)", started, f"{len(f1)} finding(s)")
        return f1, n1

    def _lane_layer3():
        started = time.monotonic()
        _tick("▶ Layer 3 (conformance): repo vs policy…")
        f3, n3 = check_conformance(result.inventory, policy, taxonomy)
        _phase("Layer 3 (conformance)", started, f"{len(f3)} finding(s)")
        return f3, n3

    def _lane_llm():
        # Layer 2, then Layer 4: the org's DataRobot risk-management policy
        # decides what Layer 4 requires; the same LLM client judges whether
        # the repo shows evidence for each requirement (risk_management.py).
        # Without an LLM, requirements are still fetched and reported as not
        # assessed.
        started = time.monotonic()
        client = get_client(llm_client) if use_llm else None
        if use_llm and client is None:
            _tick(NO_LLM_NOTE)
        f2, s2, n2 = run_layer2(
            client,
            workspace,
            result.inventory,
            taxonomy,
            max_bytes,
            _tick,
            max_workers=max_workers,
        )
        if client is not None:
            _phase("Layer 2 (LLM reasoning)", started, f"{len(f2)} finding(s)")

        f4: list = []
        coverage4: list = []
        n4: list = []
        iac4: dict = {}
        packs = policy.get("regulatory", {}).get("packs", [])
        if "eu_ai_act" in (packs or []):
            started = time.monotonic()
            policy_name = policy.get("regulatory", {}).get(
                "policy_name", EU_AI_ACT_POLICY_NAME
            )
            f4, coverage4, n4, iac4 = run_dynamic_layer4(
                client,
                workspace,
                result.inventory,
                policy_name,
                max_bytes,
                progress=_tick,
                max_workers=max_workers,
            )
            _phase("Layer 4 (regulatory)", started, f"{len(f4)} finding(s)")
        return f2, s2, n2, f4, coverage4, n4, iac4

    with ThreadPoolExecutor(max_workers=3) as lanes:
        fut1 = lanes.submit(_lane_layer1)
        fut3 = lanes.submit(_lane_layer3)
        fut_llm = lanes.submit(_lane_llm)
        f1, n1 = fut1.result()
        f3, n3 = fut3.result()
        f2, s2, n2, f4, coverage4, n4, iac4 = fut_llm.result()

    # Aggregate in a fixed order so reports stay deterministic regardless of
    # which lane finished first.
    result.findings += f1 + f3 + f2 + f4
    result.notes += n1 + n3 + n2 + n4
    result.skipped += s2
    result.regulatory_coverage += coverage4
    result.iac = iac4

    result.findings = _dedup(result.findings)
    _tick("Scoring remediation posture…")
    result.posture = assess_posture(result, policy, taxonomy)
    return result, policy


def _dedup(findings):
    """Collapse findings that share (condition_id, file, line); file-level findings
    (no line) stay distinct per evidence so N CVEs in one manifest stay N."""
    seen = set()
    out = []
    for f in findings:
        key = (f.condition_id, f.file, f.line, f.evidence if f.line is None else "")
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
