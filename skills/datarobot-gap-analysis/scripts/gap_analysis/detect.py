# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Layer 2 (LLM reasoning) and Layer 4 (regulatory) detection runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import paths
from .inventory import files_matching
from .llm import LLMClient, parse_json
from .models import ConditionSkip, Finding
from .taxonomy import Condition, Taxonomy

_MAX_FILES = 12  # cap files fed per condition
_DEFAULT_MAX_BYTES = 200_000


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
        out.append((rel, data))
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
    findings: list[Finding] = []
    skips: list[ConditionSkip] = []
    conds = taxonomy.by_layer(2)
    for i, cond in enumerate(conds, 1):
        if progress:
            progress(f"Layer 2 (LLM reasoning): {cond.id} [{i}/{len(conds)}]")
        f, skip = run_condition(client, workspace, inventory, cond, contract, max_bytes)
        findings += f
        if skip:
            skips.append(skip)
    return findings, skips, notes


def run_layer4(
    client: LLMClient | None,
    workspace,
    inventory,
    taxonomy: Taxonomy,
    packs: list[str],
    max_bytes: int = _DEFAULT_MAX_BYTES,
    progress=None,
) -> tuple[list[Finding], list[ConditionSkip], list[str]]:
    notes: list[str] = []
    # Currently only the eu_ai_act pack (POL-*) is implemented via prompts.
    if "eu_ai_act" not in (packs or []):
        return [], [], notes
    if client is None:
        skips = [
            ConditionSkip(
                c.id, "Layer 4 (regulatory) not run — no model client configured"
            )
            for c in taxonomy.by_layer(4)
        ]
        notes.append("Layer 4 (regulatory) skipped — no model client configured.")
        return [], skips, notes
    contract = (paths.prompts_dir() / "_contract.md").read_text()
    workspace = Path(workspace)
    findings: list[Finding] = []
    skips: list[ConditionSkip] = []
    conds = taxonomy.by_layer(4)
    for i, cond in enumerate(conds, 1):
        if progress:
            progress(f"Layer 4 (EU AI Act): {cond.id} [{i}/{len(conds)}]")
        f, skip = run_condition(client, workspace, inventory, cond, contract, max_bytes)
        findings += f
        if skip:
            skips.append(skip)
    return findings, skips, notes
