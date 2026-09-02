# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guided migration — extract business logic, review as a spec, scaffold a fresh base.

The logic-preserving alternative to both blind rebuild and risky in-place restructuring.
When the remediation posture is RE-PLATFORM (see posture.py), patching structural gaps
means restructuring code you don't own. Instead we:

  1. extract_spec()        — lift the business logic (prompts, tools, graph, deps) into a
                             structured spec via an LLM pass over the repo's key files;
  2. render_spec_markdown()— render it as an agent_spec.md, the HUMAN REVIEW checkpoint;
  3. scaffold_from_spec()  — assemble a migration bundle (spec + carried-over logic +
                             externalized prompts) ready for the DataRobot agent template
                             (the `datarobot-agent-assist` skill / `dr` scaffolder) to turn
                             into a runnable af-components agent.

The checkpoint is the SPEC, not a diff of unfamiliar code — that is what makes this safe.
"""

from __future__ import annotations

import fnmatch
import shutil
from pathlib import Path
from typing import Any

from . import paths
from .llm import LLMClient, parse_json

# Files most likely to hold business logic (entrypoints, graph, tools, prompts).
# Deliberately broad on the agent/tool side, then capped by byte budget.
_LOGIC_GLOBS = [
    "**/agent*.py",
    "**/*agent*.py",
    "**/graph*.py",
    "**/*graph*.py",
    "**/main.py",
    "**/app.py",
    "**/workflow*.py",
    "**/chain*.py",
    "**/tools.py",
    "**/tools/**",
    "**/*tool*.py",
    "**/prompt*",
    "**/*prompt*",
    "**/system_message*",
    "**/instructions*",
]


def _matches(rel: str, glob: str) -> bool:
    """Glob match on the full path OR the basename, so '**/agent*.py' also hits a
    top-level 'agent.py' (fnmatch does not special-case '**')."""
    base = glob[3:] if glob.startswith("**/") else glob
    return fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(Path(rel).name, base)


def _gather_logic_files(
    workspace: Path, inventory: dict[str, Any], max_bytes: int
) -> list[tuple[str, str]]:
    """Return (rel_path, content) for candidate business-logic files, byte-capped."""
    rels: list[str] = []
    seen: set[str] = set()
    for rel in inventory.get("files", []):
        if rel not in seen and any(_matches(rel, g) for g in _LOGIC_GLOBS):
            seen.add(rel)
            rels.append(rel)
    # Stable order: agent/graph first, then tools, then prompts — most informative first.
    rels.sort(key=lambda r: ("prompt" in r.lower(), "tool" in r.lower(), r))

    out: list[tuple[str, str]] = []
    budget = max_bytes
    for rel in rels:
        p = workspace / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:  # noqa: BLE001
            continue
        snippet = text[:budget]
        out.append((rel, snippet))
        budget -= len(snippet)
        if budget <= 0:
            break
    return out


def extract_spec(
    workspace: str | Path,
    inventory: dict[str, Any],
    client: LLMClient | None,
    max_bytes: int = 120_000,
) -> dict[str, Any]:
    """Run the extraction prompt over the repo's key files; return the spec dict.

    Raises RuntimeError if no LLM client is available (extraction is inherently a
    reasoning task — there is no deterministic fallback).
    """
    if client is None:
        raise RuntimeError("migration extraction needs an LLM client (none configured)")
    workspace = Path(workspace)
    files = _gather_logic_files(workspace, inventory, max_bytes)
    if not files:
        return {
            "name": "",
            "description": "",
            "framework": "unknown",
            "model": "",
            "system_prompt": "",
            "tools": [],
            "workflow": "",
            "domain_dependencies": [],
            "carryover_files": [],
            "manual_wiring": [
                "No agent/tool/prompt files found — this may not be an agent repo."
            ],
            "confidence": "low",
        }

    prompt = paths.resolve("prompts/migrate-extract-spec.md").read_text()
    contract = (paths.prompts_dir() / "_migrate_contract.md").read_text()
    system = f"{prompt}\n\n---\n# Output contract\n{contract}"
    parts = [f"=== FILE: {rel} ===\n{content}" for rel, content in files]
    declared = inventory.get("dependencies", [])
    user = (
        "Repository key files follow. Declared dependencies: "
        f"{', '.join(declared) or 'n/a'}.\n\n" + "\n\n".join(parts)
    )

    spec = parse_json(client.complete(system, user))
    # Normalize the shape so downstream rendering/scaffolding is total.
    spec.setdefault("name", inventory.get("root", "agent").split("/")[-1])
    for k, default in (
        ("tools", []),
        ("domain_dependencies", []),
        ("carryover_files", []),
        ("manual_wiring", []),
    ):
        spec.setdefault(k, default)
    for k in (
        "description",
        "framework",
        "model",
        "system_prompt",
        "workflow",
        "confidence",
    ):
        spec.setdefault(k, "")
    return spec


def render_spec_markdown(spec: dict[str, Any]) -> str:
    """Render the extracted spec as an agent_spec.md for human review/edit."""
    import yaml  # local import; yaml already a dependency via taxonomy/policy

    lines = [
        "# Migrated Agent — agent_spec.md",
        "#",
        "# Generated by the gap-analysis guided migration. REVIEW AND EDIT THIS before",
        "# scaffolding. The af-component stack (base + llm + datarobot-mcp + agent@langgraph)",
        "# provides the runtime; the fields below are your carried-over business logic.",
        "",
        f"name: {spec.get('name') or 'migrated-agent'}",
        f"description: {_yaml_scalar(spec.get('description'))}",
        f"source_framework: {spec.get('framework') or 'unknown'}",
        f"confidence: {spec.get('confidence') or 'unknown'}",
        "",
        f"model: {_yaml_scalar(spec.get('model') or 'datarobot/anthropic/claude-sonnet-4-6')}",
        "",
        "system_prompt: |",
    ]
    for ln in (spec.get("system_prompt") or "(none extracted)").splitlines() or [""]:
        lines.append(f"  {ln}")

    lines += ["", "workflow: |"]
    for ln in (spec.get("workflow") or "(none extracted)").splitlines() or [""]:
        lines.append(f"  {ln}")

    lines += ["", "tools:"]
    if spec.get("tools"):
        lines.append(yaml.safe_dump(spec["tools"], sort_keys=False).rstrip())
    else:
        lines.append("  []")

    lines += ["", "domain_dependencies:"]
    for d in spec.get("domain_dependencies") or []:
        lines.append(f"  - {d}")

    lines += ["", "carryover_files:"]
    for f in spec.get("carryover_files") or []:
        lines.append(f"  - {f}")

    if spec.get("manual_wiring"):
        lines += ["", "manual_wiring:  # reconnect these after scaffolding"]
        for m in spec["manual_wiring"]:
            lines.append(f"  - {_yaml_scalar(m)}")

    return "\n".join(lines) + "\n"


def _yaml_scalar(s: Any) -> str:
    """Quote a scalar if it could confuse the YAML reader."""
    s = "" if s is None else str(s)
    if s == "" or any(ch in s for ch in ":#\n") or s.strip() != s:
        return '"' + s.replace('"', '\\"').replace("\n", " ") + '"'
    return s


def scaffold_from_spec(
    spec: dict[str, Any], workspace: str | Path, dest: str | Path
) -> dict[str, Any]:
    """Assemble a migration bundle at `dest` ready for the af-components scaffolder.

    Produces, deterministically:
      dest/agent_spec.md          — the rendered, reviewable spec (handoff to the template)
      dest/prompts/system.md      — the extracted system prompt, externalized (also fixes AIG-008)
      dest/carryover/<files>      — business-logic files copied verbatim for re-insertion
      dest/README.md              — how to finish: run the datarobot-agent-assist scaffolder

    The heavy af-components template generation is intentionally DELEGATED to the
    `datarobot-agent-assist` skill / `dr` template (which the repo already depends on);
    re-implementing it here would duplicate that template.
    """
    workspace = Path(workspace)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # 1. The spec — the primary artifact the scaffolder consumes.
    spec_md = render_spec_markdown(spec)
    (dest / "agent_spec.md").write_text(spec_md)

    # 2. Externalize the system prompt as a versioned file.
    prompts_dir = dest / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    if spec.get("system_prompt"):
        (prompts_dir / "system.md").write_text(spec["system_prompt"].rstrip() + "\n")

    # 3. Copy carried-over business-logic files (skip anything missing or outside the repo).
    carried, missing = [], []
    carry_root = dest / "carryover"
    for rel in spec.get("carryover_files") or []:
        src = (workspace / rel).resolve()
        try:
            src.relative_to(workspace.resolve())
        except ValueError:
            missing.append(rel)  # path escapes the workspace — refuse
            continue
        if not src.is_file():
            missing.append(rel)
            continue
        out_path = carry_root / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out_path)
        carried.append(rel)

    # 4. README handoff.
    (dest / "README.md").write_text(_readme(spec, carried, missing))

    return {
        "dest": str(dest),
        "spec_path": str(dest / "agent_spec.md"),
        "carried_over": carried,
        "missing_files": missing,
        "manual_wiring": spec.get("manual_wiring") or [],
    }


def _readme(spec: dict[str, Any], carried: list[str], missing: list[str]) -> str:
    tools = (
        ", ".join(t.get("name", "?") for t in spec.get("tools") or [])
        or "none detected"
    )
    lines = [
        f"# Migration bundle — {spec.get('name') or 'migrated-agent'}",
        "",
        "This bundle was produced by the gap-analysis guided migration. It contains the",
        "**business logic** lifted from the source agent, ready to be scaffolded onto the",
        "DataRobot af-component stack — instead of restructuring the original in place.",
        "",
        "## Contents",
        "- `agent_spec.md` — the reviewable spec (model, system prompt, tools, workflow).",
        "- `prompts/system.md` — the externalized system prompt.",
        f"- `carryover/` — {len(carried)} business-logic file(s) copied verbatim.",
        "",
        f"**Source framework:** {spec.get('framework') or 'unknown'} &nbsp;|&nbsp; "
        f"**Tools:** {tools} &nbsp;|&nbsp; **Confidence:** {spec.get('confidence') or 'unknown'}",
        "",
        "## Next step — scaffold the af-components agent",
        "1. **Review and edit `agent_spec.md`.** This is the human checkpoint — confirm the",
        "   prompt, tools, and workflow are faithful before generating any code.",
        "2. Run the DataRobot agent template scaffolder against it (the `datarobot-agent-assist`",
        "   skill, or `dr` with the agent template), which generates the af-component-base /",
        "   -llm / -datarobot-mcp / agent@langgraph runtime around this spec.",
        "3. Re-insert the carried-over logic from `carryover/` into the generated tools/graph.",
        "4. Re-run `run_gap_analysis` on the scaffolded agent to confirm the structural gaps",
        "   are closed.",
    ]
    if missing:
        lines += [
            "",
            "## Files referenced but not copied",
            *[f"- {m}" for m in missing],
        ]
    if spec.get("manual_wiring"):
        lines += ["", "## Manual wiring", *[f"- {m}" for m in spec["manual_wiring"]]]
    return "\n".join(lines) + "\n"
