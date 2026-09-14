# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""High-level orchestration: analyze() and fix() used by the CLI and the agent tools."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections.abc import Callable
from typing import Any

from .conformance import check_conformance
from .detect import NO_LLM_NOTE, run_layer2, verify_layer1_findings
from .inventory import build_inventory, git_ignore
from .llm import get_client
from .migrate import extract_spec, scaffold_from_spec
from .models import AnalysisResult, ConditionSkip, Finding
from .settings import DEFAULTS, Settings
from .policy import load_policy
from .posture import assess_posture
from .remediate import remediate
from .risk_management import EU_AI_ACT_POLICY_NAME, run_dynamic_layer4
from .scanners import run_layer1
from .taxonomy import Taxonomy


def analyze(
    workspace: str | Path,
    policy_path: str | None = None,
    llm_client: Any = None,
    progress: Callable[[str], None] | None = None,
    settings: Settings = DEFAULTS,
    only: set[str] | None = None,
) -> tuple[AnalysisResult, dict[str, Any]]:
    """Run all enabled layers over an already-available workspace.

    Returns (result, policy). `llm_client` may be an injected af-component-llm
    callable; otherwise a standalone client is auto-detected from `settings`.
    `progress`, if given, is called with short status strings as each stage
    runs (for CLI feedback). `only` restricts Layer 2 to the named condition
    ids, for re-running checks that timed out.
    """
    use_llm = settings.use_llm
    max_workers = settings.workers

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
    result.inventory = build_inventory(workspace, exclude, offline=settings.offline)
    _phase("repo index", t0, f"{len(result.inventory.get('files', []))} files")
    ignored = git_ignore(Path(workspace)).entries
    if ignored:
        shown = ", ".join(f"`{e}`" for e in ignored[:6])
        if len(ignored) > 6:
            shown += f" and {len(ignored) - 6} more"
        result.notes.append(
            f"{len(ignored)} git-ignored entr{'y' if len(ignored) == 1 else 'ies'} "
            f"left out of every layer, since git would never commit them: {shown}."
        )

    # The layers only read the inventory and are independent of each other, so
    # they run in three concurrent lanes: Layer 1 (subprocess scanners, often
    # the slowest), Layer 3 (instant), and Layers 2+4 sequentially in one lane
    # so LLM concurrency stays at `max_workers` rather than doubling.
    def _lane_layer1() -> tuple[list[Finding], list[str]]:
        started = time.monotonic()
        _tick("▶ Layer 1 (scanners): secrets, dependencies, SAST, tests/CI…")
        f1, n1 = run_layer1(workspace, taxonomy, exclude, progress=_tick, policy=policy)
        _phase("Layer 1 (scanners)", started, f"{len(f1)} finding(s)")
        return f1, n1

    def _lane_layer3() -> tuple[list[Finding], list[str]]:
        started = time.monotonic()
        _tick("▶ Layer 3 (conformance): repo vs policy…")
        f3, n3 = check_conformance(
            result.inventory, policy, taxonomy, offline=settings.offline
        )
        _phase("Layer 3 (conformance)", started, f"{len(f3)} finding(s)")
        return f3, n3

    def _lane_llm() -> tuple[
        list[Finding],
        list[ConditionSkip],
        list[str],
        list[Finding],
        list[dict[str, str]],
        list[str],
        dict[str, Any],
        Any,
    ]:
        # Layer 2, then Layer 4: the org's DataRobot risk-management policy
        # decides what Layer 4 requires; the same LLM client judges whether
        # the repo shows evidence for each requirement (risk_management.py).
        # Without an LLM, requirements are still fetched and reported as not
        # assessed.
        started = time.monotonic()
        client = get_client(llm_client, settings) if use_llm else None
        if use_llm and client is None:
            _tick(NO_LLM_NOTE)
        _set_phase(client, "Layer 2 (code reasoning + verification)")
        f2, s2, n2 = run_layer2(
            client,
            workspace,
            result.inventory,
            taxonomy,
            max_bytes,
            _tick,
            max_workers=max_workers,
            settings=settings,
            only=only,
        )
        if client is not None:
            _phase("Layer 2 (LLM reasoning)", started, f"{len(f2)} finding(s)")

        f4: list[Finding] = []
        coverage4: list[dict[str, str]] = []
        n4: list[str] = []
        iac4: dict[str, Any] = {}
        packs = policy.get("regulatory", {}).get("packs", [])
        if "eu_ai_act" in (packs or []):
            started = time.monotonic()
            policy_name = policy.get("regulatory", {}).get(
                "policy_name", EU_AI_ACT_POLICY_NAME
            )
            _set_phase(client, "Layer 4 (risk-management judging)")
            f4, coverage4, n4, iac4 = run_dynamic_layer4(
                client,
                workspace,
                result.inventory,
                policy_name,
                max_bytes,
                progress=_tick,
                max_workers=max_workers,
                offline=settings.offline,
            )
            _phase("Layer 4 (regulatory)", started, f"{len(f4)} finding(s)")
        return f2, s2, n2, f4, coverage4, n4, iac4, client

    with ThreadPoolExecutor(max_workers=3) as lanes:
        fut1 = lanes.submit(_lane_layer1)
        fut3 = lanes.submit(_lane_layer3)
        fut_llm = lanes.submit(_lane_llm)
        f1, n1 = fut1.result()
        f3, n3 = fut3.result()
        f2, s2, n2, f4, coverage4, n4, iac4, client = fut_llm.result()

    if client is not None and settings.verify:
        _set_phase(client, "Layer 1 (secret verification)")
        f1, n1v = verify_layer1_findings(client, Path(workspace), taxonomy, f1, _tick)
        n1 += n1v
    usage = usage_snapshot(client)

    # Aggregate in a fixed order so reports stay deterministic regardless of
    # which lane finished first.
    result.findings += f1 + f3 + f2 + f4
    result.notes += n1 + n3 + n2 + n4
    result.skipped += s2
    result.regulatory_coverage += coverage4
    result.iac = iac4
    result.usage = usage
    if not coverage4:
        skip = next(
            (
                n
                for n in n4
                if n.startswith("Layer 4 (DataRobot risk-management) skipped")
            ),
            None,
        )
        if skip:
            result.skipped.append(ConditionSkip("POL-DR-* (Layer 4)", skip))

    result.findings = _dedup(result.findings)
    _tick("Scoring remediation posture…")
    result.posture = assess_posture(result, policy, taxonomy)
    return result, policy


def _set_phase(client: Any, phase: str) -> None:
    meter = getattr(client, "usage", None)
    if meter is not None:
        meter.phase = phase


def usage_snapshot(client: Any) -> dict[str, Any]:
    """Token usage the client has metered so far; {} for clients without a meter."""
    meter = getattr(client, "usage", None)
    return dict(meter.snapshot()) if meter is not None else {}


def _dedup(findings: list[Finding]) -> list[Finding]:
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
    selected_ids: set[str] | None = None,
    report_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Apply the deterministic codemods; no model is involved."""
    return remediate(
        workspace, result.findings, policy, timestamp, None, selected_ids, report_dir
    )


def migrate_extract(
    workspace: str | Path,
    result: AnalysisResult,
    policy: dict[str, Any],
    llm_client: Any = None,
    settings: Settings = DEFAULTS,
) -> dict[str, Any]:
    """Extract the agent's business logic into a reviewable migration spec (Part B step 1)."""
    client = get_client(llm_client, settings) if settings.use_llm else None
    max_bytes = int(policy.get("scan", {}).get("max_file_bytes", 120_000))
    return extract_spec(workspace, result.inventory, client, max_bytes)


def migrate_scaffold(
    workspace: str | Path, spec: dict[str, Any], dest: str | Path
) -> dict[str, Any]:
    """Assemble the migration bundle from an (approved) spec (Part B step 3)."""
    return scaffold_from_spec(spec, workspace, dest)
