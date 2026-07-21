# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Layer 1 — deterministic scanners.

Prefers off-the-shelf tools (detect-secrets, pip-audit, semgrep) when installed,
and falls back to a built-in regex secret scanner + manifest parsing so the
engine always produces Layer-1 results offline. Never emits a raw secret value.
"""

from __future__ import annotations

import fnmatch
import json
import re
import shutil
import subprocess
from pathlib import Path

from .inventory import _DEF_EXCLUDE, _iter_files
from .models import Finding
from .taxonomy import Taxonomy

# Vendor + generic credential patterns. Group 'val' is the secret (never emitted).
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("OpenAI key", re.compile(r"\b(sk-[A-Za-z0-9]{20,})")),
    ("AWS access key id", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("Slack token", re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})")),
    ("GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,})")),
    ("Google API key", re.compile(r"\b(AIza[0-9A-Za-z_\-]{30,})")),
    (
        "Private key block",
        re.compile(r"(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"),
    ),
    (
        "Generic credential assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|access[_-]?key)\b"
            r"\s*[:=]\s*['\"]([^'\"]{8,})['\"]"
        ),
    ),
]

# Values that look credential-shaped but are obviously placeholders.
_PLACEHOLDER = re.compile(
    r"(?i)(your[_-]?|example|placeholder|xxx+|<.*>|\$\{|change[_-]?me|dummy|test|fake)"
)

_LOG_CALL = re.compile(
    r"(?i)\b(print|console\.(log|error|warn|info)|logger?\.\w+|logging\.\w+|trace)\s*\("
)


def _redact(label: str, value: str) -> str:
    tail = value[-4:] if len(value) >= 8 else ""
    return f"{label} (…{tail})" if tail else label


def _scan_text_for_secrets(text: str) -> list[tuple[int, str, str, str]]:
    """Return (line_no, label, redacted, raw_value) for each match."""
    out = []
    for i, line in enumerate(text.splitlines(), start=1):
        for label, pat in _SECRET_PATTERNS:
            for m in pat.finditer(line):
                value = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(value):
                    continue
                out.append((i, label, _redact(label, value), value))
    return out


def run_secret_scan(
    workspace: str | Path, taxonomy: Taxonomy, exclude: list[str] | None = None
) -> tuple[list[Finding], list[str]]:
    """Produce SEC-002/003/004/006 findings. Returns (findings, notes)."""
    root = Path(workspace)
    exclude = (exclude or []) + _DEF_EXCLUDE
    notes: list[str] = []
    findings: list[Finding] = []

    c002 = taxonomy.get("SEC-002")
    c003 = taxonomy.get("SEC-003")
    c004 = taxonomy.get("SEC-004")
    c006 = taxonomy.get("SEC-006")

    # value -> list of (file) for SEC-006 cross-env duplicate detection
    value_locations: dict[str, list[str]] = {}

    for p, rel in _iter_files(root, exclude):
        if p.suffix.lower() not in {
            ".py",
            ".ts",
            ".js",
            ".tsx",
            ".jsx",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".env",
            ".cfg",
            ".ini",
        } and not p.name.lower().startswith(".env"):
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        lines = text.splitlines()
        for line_no, label, redacted, raw in _scan_text_for_secrets(text):
            value_locations.setdefault(raw, []).append(rel)
            is_config = bool(
                rel.lower().endswith((".env", ".yaml", ".yml", ".json"))
                or "docker-compose" in rel.lower()
                or Path(rel).name.lower().startswith(".env")
            )
            line_text = lines[line_no - 1] if line_no - 1 < len(lines) else ""
            logged = bool(_LOG_CALL.search(line_text))

            if logged and c004:
                findings.append(
                    _mk(
                        c004,
                        rel,
                        line_no,
                        _redact(label, raw),
                        "Credential-shaped value passed to a log/print/trace call.",
                    )
                )
            elif is_config and c003:
                findings.append(
                    _mk(
                        c003,
                        rel,
                        line_no,
                        redacted,
                        "Credential found in checked-in configuration.",
                    )
                )
            elif c002:
                findings.append(
                    _mk(
                        c002,
                        rel,
                        line_no,
                        redacted,
                        "Hardcoded credential-shaped string in source/config.",
                    )
                )

    # SEC-006 — same secret value across >1 environment file
    if c006:
        for raw, locs in value_locations.items():
            env_locs = sorted({loc for loc in locs if _looks_env(loc)})
            if len(env_locs) > 1:
                findings.append(
                    _mk(
                        c006,
                        env_locs[0],
                        None,
                        _redact("shared secret", raw),
                        "Identical secret value appears in multiple environment configs: "
                        + ", ".join(env_locs),
                    )
                )

    return findings, notes


def _looks_env(rel: str) -> bool:
    low = rel.lower()
    return (
        Path(rel).name.lower().startswith(".env")
        or any(tag in low for tag in ("dev", "staging", "stage", "prod", "test"))
        and low.endswith((".env", ".yaml", ".yml", ".json"))
    )


def run_sca(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """SEC-010 — dependency vulnerabilities via pip-audit if available."""
    root = Path(workspace)
    notes: list[str] = []
    findings: list[Finding] = []
    cond = taxonomy.get("SEC-010")
    if not cond:
        return findings, notes
    if not shutil.which("pip-audit"):
        notes.append("SEC-010: pip-audit not installed — dependency CVE scan skipped.")
        return findings, notes

    req_files = list(root.rglob("requirements*.txt"))
    targets = req_files or (
        [root / "pyproject.toml"] if (root / "pyproject.toml").exists() else []
    )
    for tgt in targets:
        try:
            proc = subprocess.run(
                ["pip-audit", "-f", "json", "-r", str(tgt)]
                if tgt.name.startswith("requirements")
                else ["pip-audit", "-f", "json"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=300,
            )
            data = json.loads(proc.stdout or "{}")
            deps = data.get("dependencies", data) if isinstance(data, dict) else data
            for dep in deps if isinstance(deps, list) else []:
                for vuln in dep.get("vulns", []) or []:
                    fix = (
                        ", ".join(vuln.get("fix_versions", []) or []) or "see advisory"
                    )
                    findings.append(
                        _mk(
                            cond,
                            tgt.relative_to(root).as_posix(),
                            None,
                            f"{dep.get('name')}=={dep.get('version')} — {vuln.get('id')}",
                            f"Known vulnerability {vuln.get('id')}; fixed in: {fix}.",
                        )
                    )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:  # noqa: BLE001
            notes.append(f"SEC-010: pip-audit failed on {tgt.name}: {e}")
    return findings, notes


def run_sast(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """Optional semgrep pass (auto rules). Mapped loosely to SEC-011."""
    notes: list[str] = []
    findings: list[Finding] = []
    cond = taxonomy.get("SEC-011")
    if not shutil.which("semgrep"):
        notes.append(
            "SEC-011: semgrep not installed — SAST pass skipped (LLM Layer-2 still runs)."
        )
        return findings, notes
    root = Path(workspace)
    try:
        proc = subprocess.run(
            ["semgrep", "--config", "auto", "--json", "--quiet", str(root)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
        )
        data = json.loads(proc.stdout or "{}")
        for res in data.get("results", [])[:200]:
            if cond:
                findings.append(
                    _mk(
                        cond,
                        Path(res.get("path", "")).as_posix(),
                        (res.get("start") or {}).get("line"),
                        res.get("check_id", "semgrep"),
                        (res.get("extra") or {}).get("message", "semgrep finding"),
                    )
                )
    except Exception as e:  # noqa: BLE001
        notes.append(f"SEC-011: semgrep failed: {e}")
    return findings, notes


def check_presence(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """REL-001 (tests) and REL-002 (CI) presence checks."""
    root = Path(workspace)
    findings: list[Finding] = []
    notes: list[str] = []

    has_tests = any(
        fnmatch.fnmatch(f.relative_to(root).as_posix(), g)
        for f in root.rglob("*")
        if f.is_file()
        for g in [
            "**/test_*.py",
            "**/*_test.py",
            "**/tests/**",
            "**/*.spec.*",
            "**/*.test.*",
        ]
    )
    if not has_tests:
        c = taxonomy.get("REL-001")
        if c:
            findings.append(
                _mk(
                    c,
                    None,
                    None,
                    "no test files found",
                    "No unit/integration tests detected anywhere in the repo.",
                )
            )

    ci_exists = (root / ".github" / "workflows").is_dir() or any(
        (root / f).exists()
        for f in [".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"]
    )
    if not ci_exists:
        c = taxonomy.get("REL-002")
        if c:
            findings.append(
                _mk(
                    c,
                    None,
                    None,
                    "no CI configuration found",
                    "No CI/CD pipeline detected (.github/workflows, .gitlab-ci.yml, …).",
                )
            )
    return findings, notes


def _mk(cond, file, line, evidence, explanation) -> Finding:
    return Finding(
        condition_id=cond.id,
        pillar=cond.pillar,
        severity=cond.severity,
        title=cond.title,
        file=file,
        line=line,
        evidence=evidence,
        explanation=explanation,
        remediation=cond.remediation,
        fix_type=cond.fix_type,
        fix_strategy=cond.fix_strategy,
        fix_risk=cond.fix_risk,
        layer=cond.layer,
        detector=cond.detector,
    )


def run_layer1(workspace, taxonomy, exclude=None) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    notes: list[str] = []
    for fn in (run_secret_scan,):
        f, n = fn(workspace, taxonomy, exclude)
        findings += f
        notes += n
    for fn in (run_sca, run_sast, check_presence):
        f, n = fn(workspace, taxonomy)
        findings += f
        notes += n
    return findings, notes
