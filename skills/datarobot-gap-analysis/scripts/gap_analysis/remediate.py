# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Remediation engine — applies fixes on a dedicated branch.

Safety rails:
  * all changes land on a new `gap-fixes/<timestamp>` branch, never the
    caller's checked-out default branch state is committed without the user;
  * nothing is pushed and no PR is opened here (see open_pull_request);
  * a fix that cannot be applied safely is downgraded to advisory guidance.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import paths
from .llm import LLMClient, parse_json
from .models import Finding
from .scanners import _SECRET_PATTERNS, _PLACEHOLDER

# Floating -> pinned model id map for AIG-002 auto-pinning (extend as needed).
_MODEL_PINS = {
    "gpt-4o": "gpt-4o-2024-11-20",
    "claude-3-5-sonnet": "claude-3-5-sonnet-20241022",
    "claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
    "gemini-1.5-pro": "gemini-1.5-pro-002",
}


# ───────────────────────── git helpers ─────────────────────────


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True)


def create_fix_branch(workspace: str | Path, timestamp: str) -> str:
    workspace = Path(workspace)
    branch = f"gap-fixes/{timestamp}"
    _git(workspace, "checkout", "-b", branch)
    return branch


def git_diff_stat(workspace: str | Path) -> str:
    return _git(Path(workspace), "diff", "--stat").stdout


# ───────────────────────── auto codemods ─────────────────────────


def _env_var_name(line: str, label: str) -> str:
    m = re.search(r"(?i)\b(api[_-]?key|secret|token|password|access[_-]?key)\b", line)
    base = (m.group(1) if m else label).upper().replace("-", "_").replace(" ", "_")
    if "openai" in line.lower():
        return "OPENAI_API_KEY"
    if "aws" in line.lower():
        return "AWS_ACCESS_KEY_ID"
    return (
        base
        if base.endswith(("KEY", "TOKEN", "SECRET", "PASSWORD"))
        else base + "_SECRET"
    )


def _fix_secret_to_env_var(workspace: Path, f: Finding) -> dict[str, Any]:
    if not f.file or not f.line:
        return _cannot(f, "no precise location for the secret")
    path = workspace / f.file
    lines = path.read_text(errors="ignore").splitlines(keepends=True)
    idx = f.line - 1
    if idx >= len(lines):
        return _cannot(f, "line out of range")
    line = lines[idx]
    # Locate the actual secret value on the line.
    value = None
    for _label, pat in _SECRET_PATTERNS:
        m = pat.search(line)
        if m:
            value = m.group(1) if m.groups() else m.group(0)
            if not _PLACEHOLDER.search(value):
                break
            value = None
    if not value:
        return _cannot(f, "could not relocate secret value")
    env_name = _env_var_name(line, "")
    is_py = f.file.endswith(".py")
    if is_py:
        # Replace the quoted literal with os.environ[...]
        new_line = re.sub(
            r"(['\"])" + re.escape(value) + r"\1",
            f'os.environ["{env_name}"]',
            line,
        )
        if "import os" not in "".join(lines):
            lines.insert(0, "import os\n")
            idx += 1
    else:
        new_line = line.replace(value, f"${{{env_name}}}")
        lines[idx] = new_line
        _add_gitignore(workspace, f.file)
        path.write_text("".join(lines))
        return _ok(
            f,
            f"Replaced secret in {f.file} with ${{{env_name}}}; added to .gitignore.",
            manual=f"Rotate the exposed credential and set {env_name} in your secret store.",
        )
    lines[idx] = new_line
    path.write_text("".join(lines))
    return _ok(
        f,
        f'Replaced hardcoded secret with os.environ["{env_name}"] in {f.file}.',
        manual=f"Rotate the exposed credential and set {env_name} in the environment.",
    )


def _add_gitignore(workspace: Path, rel: str) -> None:
    gi = workspace / ".gitignore"
    existing = gi.read_text().splitlines() if gi.exists() else []
    name = Path(rel).name
    if rel not in existing and name not in existing:
        with gi.open("a") as fh:
            fh.write(f"\n{rel}\n")


def _fix_bump_dependency(workspace: Path, f: Finding) -> dict[str, Any]:
    if not f.file:
        return _cannot(f, "no manifest location")
    fix_ver = fix_version_from(f.explanation)
    pkg = (f.evidence.split("==")[0] if "==" in f.evidence else "").strip()
    if not fix_ver or not pkg:
        return _cannot(f, "no fix version available")
    path = workspace / f.file
    if path.name == "uv.lock":
        return _bump_uv_lock(f, path.parent, pkg, fix_ver)
    text = path.read_text(errors="ignore")
    new = re.sub(rf"(?im)^({re.escape(pkg)})\s*[<>=!~]=?.*$", rf"\1>={fix_ver}", text)
    if new == text:
        return _cannot(f, f"could not find {pkg} pin to bump")
    path.write_text(new)
    return _ok(f, f"Bumped {pkg} to >= {fix_ver} in {f.file}.")


_FIX_VERSION_RE = re.compile(r"fixed in:\s*([0-9]+(?:\.[0-9]+)*)", re.IGNORECASE)


def fix_version_from(explanation: str) -> str | None:
    """The first version after 'fixed in:' in a SEC-010 explanation."""
    m = _FIX_VERSION_RE.search(explanation)
    return m.group(1) if m else None


def _locked_version(lock_text: str, pkg: str) -> str | None:
    m = re.search(
        rf'^name = "{re.escape(pkg)}"\nversion = "([^"]+)"', lock_text, re.M | re.I
    )
    return m.group(1) if m else None


_SPEC_RE = re.compile(r"^([A-Za-z0-9._-]+(?:\[[^\]]*\])?)\s*([^;]*)(;.*)?$")


def _raise_floor(spec: str, fix_ver: str) -> str:
    """`aiohttp[speedups]>=3.9,<4; python_version<'3.13'` -> floor raised to
    fix_ver, upper bounds, exclusions and markers kept."""
    m = _SPEC_RE.match(spec.strip())
    if not m:
        return spec
    name, specifiers, marker = m.group(1), m.group(2), m.group(3) or ""
    keep = [
        part.strip()
        for part in specifiers.split(",")
        if part.strip() and not part.strip().startswith((">", "=", "~"))
    ]
    return f"{name}>={fix_ver}" + ("," + ",".join(keep) if keep else "") + marker


def pin_in_pyproject(text: str, pkg: str, fix_ver: str) -> tuple[str, str]:
    """Record the fixed version in pyproject.toml, the file uv.lock is generated from.

    A direct dependency or an existing `[tool.uv] constraint-dependencies` entry
    gets its floor raised; a transitive package gets a new constraint entry, the
    same pattern DataRobot templates use for CVE pins. Returns (new text, how).
    """
    entry_re = re.compile(rf'"({re.escape(pkg)}(?:\[[^\]]*\])?[^"]*)"', re.IGNORECASE)
    m = entry_re.search(text)
    if m:
        # The key of the list this entry sits in is on the line holding the last "[".
        opener = text.rfind("[", 0, m.start())
        key_line = text[text.rfind("\n", 0, opener) + 1 : opener]
        how = "constraint" if "constraint-dependencies" in key_line else "direct"
        return text[: m.start()] + f'"{_raise_floor(m.group(1), fix_ver)}"' + text[
            m.end() :
        ], how
    entry = f'    "{pkg}>={fix_ver}",\n'
    cm = re.search(r"^constraint-dependencies\s*=\s*\[\n", text, re.M)
    if cm:
        return text[: cm.end()] + entry + text[cm.end() :], "constraint"
    um = re.search(r"^\[tool\.uv\]\n", text, re.M)
    block = f"constraint-dependencies = [\n{entry}]\n"
    if um:
        return text[: um.end()] + block + text[um.end() :], "constraint"
    return text.rstrip("\n") + f"\n\n[tool.uv]\n{block}", "constraint"


def _uv_error_line(output: str) -> str:
    """uv reports the failure on a line marked with × or 'error'; the version
    banner that precedes it is noise."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for ln in lines:
        low = ln.lower()
        if ln.startswith("×") or "error" in low or "failed" in low:
            return ln.lstrip("× ").strip()
    return lines[-1] if lines else ""


def _bump_uv_lock(
    f: Finding, project_dir: Path, pkg: str, fix_ver: str
) -> dict[str, Any]:
    """Pin the fixed version in pyproject.toml and regenerate uv.lock from it.

    The lock is generated output, so the durable change is the manifest; the
    constraint in pyproject.toml is what a future `uv lock` will honour.
    """
    if not shutil.which("uv"):
        return _cannot(f, "uv is not installed, cannot re-lock")
    pyproject = project_dir / "pyproject.toml"
    if not pyproject.is_file():
        return _cannot(f, f"{project_dir.name}/ has a uv.lock but no pyproject.toml")
    original = pyproject.read_text(errors="ignore")
    updated, how = pin_in_pyproject(original, pkg, fix_ver)
    pyproject.write_text(updated)
    try:
        proc = subprocess.run(
            ["uv", "lock"], cwd=project_dir, capture_output=True, text=True, timeout=300
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        pyproject.write_text(original)
        return _cannot(f, f"uv lock failed: {e}")
    if proc.returncode != 0:
        pyproject.write_text(original)
        first = _uv_error_line(proc.stderr or proc.stdout)
        return _cannot(
            f,
            f"uv lock failed in {project_dir.name}/ after pinning {pkg}>={fix_ver}: "
            f"{first[:240]}. Another constraint may block the fixed version, or a path "
            "dependency is missing from this checkout; pyproject.toml was left unchanged.",
        )
    now = _locked_version((project_dir / "uv.lock").read_text(errors="ignore"), pkg)
    where = (
        "[tool.uv] constraint-dependencies"
        if how == "constraint"
        else "its dependency entry"
    )
    return _ok(
        f,
        f"Pinned {pkg}>={fix_ver} in {project_dir.name}/pyproject.toml ({where}) and "
        f"regenerated uv.lock ({pkg} now {now or 'updated'}).",
        manual="Run `uv sync` and the tests in that component.",
    )


def _fix_pin_model(workspace: Path, f: Finding) -> dict[str, Any]:
    floating = f.evidence.strip()
    pinned = None
    for k, v in _MODEL_PINS.items():
        if k in floating:
            pinned = floating.replace(k, v)
            break
    if not pinned or not f.file:
        return _cannot(f, "no known pinned id for this model alias")
    path = workspace / f.file
    text = path.read_text(errors="ignore")
    new = text.replace(floating, pinned)
    if new == text:
        return _cannot(f, "model id not found verbatim")
    path.write_text(new)
    return _ok(f, f"Pinned model '{floating}' -> '{pinned}' in {f.file}.")


def _fix_pin_python(
    workspace: Path, f: Finding, policy: dict[str, Any]
) -> dict[str, Any]:
    min_v = (policy.get("it_admin", {}).get("python", {}) or {}).get("min_version")
    if not min_v:
        return _cannot(f, "policy has no python.min_version")
    pp = workspace / "pyproject.toml"
    if pp.exists():
        text = pp.read_text()
        if "requires-python" in text:
            new = re.sub(
                r"requires-python\s*=\s*['\"][^'\"]+['\"]",
                f'requires-python = ">={min_v}"',
                text,
            )
        else:
            new = text.replace(
                "[project]", f'[project]\nrequires-python = ">={min_v}"', 1
            )
        pp.write_text(new)
    (workspace / ".python-version").write_text(f"{min_v}\n")
    return _ok(
        f, f"Set Python requirement to >= {min_v} (pyproject.toml + .python-version)."
    )


def _fix_scaffold_ci(workspace: Path, f: Finding) -> dict[str, Any]:
    wf = workspace / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "ci.yml").write_text(_CI_TEMPLATE)
    return _ok(f, "Added .github/workflows/ci.yml (lint + test + pip-audit).")


def _fix_scaffold_tests(workspace: Path, f: Finding) -> dict[str, Any]:
    tdir = workspace / "tests"
    tdir.mkdir(exist_ok=True)
    (tdir / "test_smoke.py").write_text(_TEST_TEMPLATE)
    return _ok(
        f,
        "Added tests/test_smoke.py starter test.",
        manual="Replace the placeholder with real assertions for your code.",
    )


_AUTO = {
    "secret_to_env_var": lambda ws, f, pol, cl: _fix_secret_to_env_var(ws, f),
    "bump_vulnerable_dependency": lambda ws, f, pol, cl: _fix_bump_dependency(ws, f),
    "pin_model_version": lambda ws, f, pol, cl: _fix_pin_model(ws, f),
    "pin_python_version": lambda ws, f, pol, cl: _fix_pin_python(ws, f, pol),
    "scaffold_ci_workflow": lambda ws, f, pol, cl: _fix_scaffold_ci(ws, f),
    "scaffold_test_stub": lambda ws, f, pol, cl: _fix_scaffold_tests(ws, f),
}


# ───────────────────────── assisted (LLM) fixes ─────────────────────────


def _fix_assisted(
    workspace: Path, f: Finding, client: LLMClient | None
) -> dict[str, Any]:
    if client is None:
        return _cannot(f, "assisted fix needs an LLM client (none configured)")
    if not f.fix_strategy or not f.file:
        return _cannot(f, "no fix prompt or file for this finding")
    prompt = paths.resolve(f.fix_strategy).read_text()
    contract = (paths.prompts_dir() / "_fix_contract.md").read_text()
    path = workspace / f.file
    try:
        content = path.read_text(errors="ignore")
    except Exception as e:  # noqa: BLE001
        return _cannot(f, f"cannot read {f.file}: {e}")
    system = f"{prompt}\n\n---\n# Output contract\n{contract}"
    user = (
        f"Finding: {f.condition_id} at {f.file}:{f.line}\n"
        f"Evidence: {f.evidence}\n\n=== FILE: {f.file} ===\n{content}"
    )
    try:
        result = parse_json(client.complete(system, user))
    except Exception as e:  # noqa: BLE001
        return _cannot(f, f"LLM/parse error: {e}")
    if not result.get("can_fix"):
        return _cannot(f, result.get("explanation", "model declined to fix"))

    applied = []
    for edit in result.get("edits", []) or []:
        old, new = edit.get("old_string"), edit.get("new_string")
        if old and old in content and content.count(old) == 1:
            content = content.replace(old, new)
            applied.append("edit")
        else:
            return _cannot(f, "edit old_string not unique/found — skipped for safety")
    if applied:
        path.write_text(content)
    for nf in result.get("new_files", []) or []:
        p = workspace / nf["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(nf["content"])
        applied.append(f"new:{nf['path']}")
    return _ok(
        f,
        result.get("explanation", "applied assisted fix"),
        manual=result.get("manual_followup", ""),
    )


# ───────────────────────── orchestration ─────────────────────────


def apply_fix(
    workspace: str | Path,
    finding: Finding,
    policy: dict[str, Any],
    client: LLMClient | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace)
    if finding.fix_type == "auto":
        fn = _AUTO.get(finding.fix_strategy or "")
        if not fn:
            return _cannot(finding, f"no auto codemod '{finding.fix_strategy}'")
        try:
            return fn(workspace, finding, policy, client)
        except Exception as e:  # noqa: BLE001
            return _cannot(finding, f"codemod error: {e}")
    if finding.fix_type == "assisted":
        return _fix_assisted(workspace, finding, client)
    return _cannot(finding, "advisory finding — manual remediation only")


def remediate(
    workspace: str | Path,
    findings: list[Finding],
    policy: dict[str, Any],
    timestamp: str,
    client: LLMClient | None = None,
    selected_ids: set[str] | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace)
    rem = policy.get("remediation", {})
    allow = set(rem.get("allow_fix_types", ["auto", "assisted"]))
    # Risk classes that may be applied without an explicit per-finding selection.
    # Business-logic-touching fixes are never swept into a blanket "fix all" — they
    # must be named by condition id so a human consciously opts into the blast radius.
    auto_apply_risk = set(rem.get("auto_apply_risk", ["plumbing"]))

    candidates = [
        f
        for f in findings
        if f.fix_type in allow
        and (selected_ids is None or f.condition_id in selected_ids)
    ]
    # When no ids were named, hold back fixes whose risk class isn't auto-applyable.
    targets, held_back = [], []
    for f in candidates:
        if selected_ids is None and f.fix_risk not in auto_apply_risk:
            held_back.append(f)
        else:
            targets.append(f)

    fixable_ids = {f.condition_id for f in candidates}
    unfixable_selected = sorted(
        cid
        for cid in (selected_ids or set())
        if cid not in fixable_ids and any(f.condition_id == cid for f in findings)
    )
    branch = create_fix_branch(workspace, timestamp) if targets else None
    results = []
    for f in targets:
        r = apply_fix(workspace, f, policy, client)
        r["fix_risk"] = f.fix_risk
        results.append(r)
    applied = [r for r in results if r["status"] == "applied"]

    # Surface what was deliberately not applied, so the caller can re-run with ids.
    skipped_risky = [
        {
            "condition_id": f.condition_id,
            "file": f.file,
            "fix_risk": f.fix_risk,
            "message": "business-logic fix held back — select it explicitly by id to apply",
        }
        for f in held_back
    ]
    touched_logic = any(r.get("fix_risk") == "business_logic" for r in applied)
    has_tests = bool(result_has_tests(workspace))
    followups = [r["manual"] for r in applied if r.get("manual")]
    if touched_logic:
        followups.append(
            "A business-logic fix was applied — run the test suite on this branch "
            "before merging."
            + ("" if has_tests else " (No tests detected; add coverage first.)")
        )
    return {
        "branch": branch,
        "attempted": len(targets),
        "applied": len(applied),
        "results": results,
        "held_back": skipped_risky,
        "unfixable_selected": unfixable_selected,
        "diff_stat": git_diff_stat(workspace) if branch else "",
        "followups": followups,
    }


def result_has_tests(workspace: Path) -> bool:
    """Cheap heuristic: does the workspace carry a test suite?"""
    for pat in ("tests", "test"):
        if (workspace / pat).is_dir():
            return True
    return any(workspace.glob("**/test_*.py")) or any(workspace.glob("**/*_test.py"))


def _ok(f: Finding, msg: str, manual: str = "") -> dict[str, Any]:
    return {
        "status": "applied",
        "condition_id": f.condition_id,
        "file": f.file,
        "message": msg,
        "manual": manual,
    }


def _cannot(f: Finding, reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "condition_id": f.condition_id,
        "file": f.file,
        "message": reason,
        "manual": "",
    }


_CI_TEMPLATE = """\
name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e . pytest pip-audit
      - run: pytest -q
      - run: pip-audit || true
"""

_TEST_TEMPLATE = """\
def test_smoke():
    # TODO: replace with real assertions for your code.
    assert True
"""
