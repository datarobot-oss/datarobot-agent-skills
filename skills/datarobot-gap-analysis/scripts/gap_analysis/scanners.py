# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Layer 1 — deterministic scanners.

Prefers off-the-shelf tools (detect-secrets, pip-audit, semgrep) when installed,
and falls back to a built-in regex secret scanner + manifest parsing so the
engine always produces Layer-1 results offline. Never emits a raw secret value.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .inventory import _DEF_EXCLUDE, _iter_files, glob_match
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

# Credential-shaped strings under these paths are fixtures or build output.
_NOISE_PATH = re.compile(
    r"(^|/)(tests?|__tests__|testdata|test_data|fixtures|__mocks__|__snapshots__)/"
    r"|(^|/)(test_[^/]+|[^/]+_test\.[^/]+|[^/]+\.(test|spec)\.[^/]+|conftest\.py)$"
    r"|(^|/)static/assets/"
    r"|\.(bundle|chunk)\.js$"
)
# Real credentials are single tokens; structure means code, not a secret.
_NOT_SECRET_CHARS = re.compile(r"[\s(){}\[\]<>;,|`\\]")
_MINIFIED_LINE_CHARS = 2000

_NON_RUNTIME_SAST_PATHS = [
    "**/tests/**",
    "**/test/**",
    "**/__tests__/**",
    "**/fixtures/**",
    "**/test_*.py",
    "**/*_test.py",
    "**/conftest.py",
    "**/*.spec.*",
    "**/*.test.*",
    "**/infra/**",
    "**/migrations/**",
    "**/alembic/**",
    "**/alembic*.py",
    "**/.github/**",
]
_SUPPLY_CHAIN_RULE = re.compile(
    r"github-actions|package_managers\.|supply-chain|dependabot|cooldown|release-age|pinned",
    re.IGNORECASE,
)
_CREDENTIAL_RULE = re.compile(r"credential|secret|password", re.IGNORECASE)


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
                if _PLACEHOLDER.search(value) or _NOT_SECRET_CHARS.search(value):
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
    skipped_fixtures = 0
    skipped_generated = 0

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
        if _NOISE_PATH.search(rel):
            skipped_fixtures += 1
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        lines = text.splitlines()
        if any(len(line) > _MINIFIED_LINE_CHARS for line in lines):
            skipped_generated += 1
            continue
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

    if skipped_fixtures or skipped_generated:
        notes.append(
            f"Secret scan skipped {skipped_fixtures} test/fixture file(s) and "
            f"{skipped_generated} generated/minified file(s)."
        )
    return findings, notes


def _looks_env(rel: str) -> bool:
    low = rel.lower()
    if Path(rel).name.lower().startswith(".env"):
        return True
    return low.endswith((".env", ".yaml", ".yml", ".json")) and any(
        tag in low for tag in ("dev", "staging", "stage", "prod")
    )


def _export_uv_locks(root: Path, notes: list[str]) -> list[tuple[Path, str]]:
    """Resolve each uv.lock to a pinned requirements file pip-audit can read.

    Returns (exported file, lockfile path relative to the repo). Exports land in a
    temp directory so the analysed checkout is never modified; a bare `pip-audit`
    on a pyproject-only repo would audit the running interpreter instead.
    """
    locks = [
        p
        for p in root.rglob("uv.lock")
        if not {"node_modules", ".venv", "venv"} & set(p.parts)
    ]
    if not locks:
        return []
    if not shutil.which("uv"):
        notes.append("SEC-010: uv not installed, uv.lock files not audited.")
        return []
    scratch = Path(tempfile.mkdtemp(prefix="gap-audit-"))
    out: list[tuple[Path, str]] = []
    for lock in locks:
        rel = lock.relative_to(root).as_posix()
        target = scratch / (rel.replace("/", "__") + ".txt")
        try:
            proc = subprocess.run(
                [
                    "uv",
                    "export",
                    "--frozen",
                    "--no-hashes",
                    "--no-emit-project",
                    "--format",
                    "requirements-txt",
                    "--directory",
                    str(lock.parent),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                notes.append(
                    f"SEC-010: uv export failed for {rel}: {proc.stderr.strip()[:200]}"
                )
                continue
            target.write_text(proc.stdout)
            out.append((target, rel))
        except (OSError, subprocess.TimeoutExpired) as e:
            notes.append(f"SEC-010: uv export failed for {rel}: {e}")
    return out


_WAIVER_ID_RE = re.compile(
    r"\b(CVE-\d{4}-\d+|GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}|PYSEC-\d{4}-\d+)\b"
)


def _cve_waivers(root: Path) -> set[str]:
    """Advisory ids the repo has already reviewed and waived in trivy-ignore.rego."""
    ids: set[str] = set()
    for p in root.glob("**/trivy-ignore.rego"):
        if not {"node_modules", ".venv", "venv"} & set(p.parts):
            ids.update(_WAIVER_ID_RE.findall(_read(p)))
    return ids


def _audit_one(root: Path, target: Path) -> list[dict]:
    proc = subprocess.run(
        [
            "pip-audit",
            "-f",
            "json",
            "--no-deps",
            "--progress-spinner",
            "off",
            "-r",
            str(target),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    data = json.loads(proc.stdout or "{}")
    deps = data.get("dependencies", data) if isinstance(data, dict) else data
    return deps if isinstance(deps, list) else []


def run_sca(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """SEC-010: Python dependency vulnerabilities via pip-audit, one finding per
    vulnerable package and manifest. Advisories waived in trivy-ignore.rego are
    dropped and counted in the notes."""
    root = Path(workspace)
    notes: list[str] = []
    findings: list[Finding] = []
    cond = taxonomy.get("SEC-010")
    if not cond:
        return findings, notes
    if not shutil.which("pip-audit"):
        notes.append("SEC-010: pip-audit not installed — dependency CVE scan skipped.")
        return findings, notes

    targets: list[tuple[Path, str]] = [
        (p, p.relative_to(root).as_posix())
        for p in root.rglob("requirements*.txt")
        if not {"node_modules", ".venv", "venv"} & set(p.parts)
    ]
    targets += _export_uv_locks(root, notes)
    if not targets:
        notes.append(
            "SEC-010: no requirements*.txt or uv.lock found, Python dependency CVE scan skipped."
        )
        return findings, notes
    waived_ids = _cve_waivers(root)
    waived = 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_audit_one, root, tgt): rel for tgt, rel in targets}
        for fut, rel in futures.items():
            try:
                deps = fut.result()
            except Exception as e:  # noqa: BLE001
                notes.append(f"SEC-010: pip-audit failed on {rel}: {e}")
                continue
            for dep in deps:
                vulns = []
                for vuln in dep.get("vulns", []) or []:
                    ids = {vuln.get("id", "")} | set(vuln.get("aliases", []) or [])
                    if ids & waived_ids:
                        waived += 1
                        continue
                    vulns.append(vuln)
                if not vulns:
                    continue
                fixes = sorted(
                    {v for vuln in vulns for v in (vuln.get("fix_versions") or [])}
                )
                ids_txt = ", ".join(v.get("id", "?") for v in vulns[:6])
                if len(vulns) > 6:
                    ids_txt += f", +{len(vulns) - 6} more"
                findings.append(
                    _mk(
                        cond,
                        rel,
                        None,
                        f"{dep.get('name')}=={dep.get('version')}: {ids_txt}",
                        f"{len(vulns)} known vulnerabilit{'y' if len(vulns) == 1 else 'ies'}; "
                        f"fixed in: {', '.join(fixes) or 'see advisory'}.",
                    )
                )
    if waived:
        notes.append(
            f"SEC-010: {waived} advisor{'y' if waived == 1 else 'ies'} waived by the repo's "
            "trivy-ignore.rego were not reported."
        )
    return findings, notes


def run_sca_npm(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """SEC-010 — JavaScript dependency vulnerabilities via `npm audit`.

    Runs against each package-lock.json from the lockfile alone (no
    node_modules, no install). Findings are advisory: the auto bump codemod
    only understands Python requirement files, so npm upgrades stay a manual
    (or `npm audit fix`) step.
    """
    root = Path(workspace)
    notes: list[str] = []
    findings: list[Finding] = []
    cond = taxonomy.get("SEC-010")
    if not cond:
        return findings, notes
    lockfiles = [
        p
        for p in root.rglob("package-lock.json")
        if "node_modules" not in p.parts and ".venv" not in p.parts
    ]
    if not lockfiles:
        return findings, notes
    if not shutil.which("npm"):
        notes.append(
            "SEC-010: package-lock.json present but npm is not installed — "
            "JavaScript dependency CVE scan skipped."
        )
        return findings, notes

    for lock in lockfiles:
        rel = lock.relative_to(root).as_posix()
        try:
            # npm audit exits non-zero when vulnerabilities exist; parse stdout
            # regardless of the exit code.
            proc = subprocess.run(
                ["npm", "audit", "--package-lock-only", "--json"],
                cwd=lock.parent,
                capture_output=True,
                text=True,
                timeout=120,
            )
            data = json.loads(proc.stdout or "{}")
            vulns = data.get("vulnerabilities", {}) or {}
            for name, info in vulns.items():
                advisories = [
                    v for v in info.get("via", []) or [] if isinstance(v, dict)
                ]
                if not advisories:
                    continue  # transitive echo of another reported package
                titles = "; ".join(a.get("title", "") for a in advisories[:3])
                fix = info.get("fixAvailable")
                fix_txt = (
                    f"fix available via {fix['name']}@{fix['version']}"
                    if isinstance(fix, dict)
                    else (
                        "fix available via `npm audit fix`"
                        if fix
                        else "no fix released yet"
                    )
                )
                f = _mk(
                    cond,
                    rel,
                    None,
                    f"{name}@{info.get('range', '?')} — {info.get('severity', '?')}",
                    f"Known npm vulnerability: {titles}; {fix_txt}.",
                )
                f.detector = "npm-audit"
                f.fix_type = "advisory"
                f.fix_strategy = None
                f.fix_risk = "none"
                findings.append(f)
        except (
            subprocess.TimeoutExpired,
            OSError,
            json.JSONDecodeError,
            ValueError,
        ) as e:
            notes.append(f"SEC-010: npm audit failed on {rel}: {e}")
    return findings, notes


def _classify_semgrep(check_id: str) -> tuple[str, str] | None:
    """(condition id, confidence) for a semgrep rule, or None to drop it.

    Supply-chain hygiene rules (unpinned actions, missing dependency cooldowns)
    are hardening advice rather than injection risks, and `.audit.` rules are
    heuristics that need a human look before they count as confirmed.
    """
    cid = check_id.lower()
    if _SUPPLY_CHAIN_RULE.search(cid):
        return "SEC-014", "high"
    if "security" not in cid:
        return None
    if "logging" in cid and _CREDENTIAL_RULE.search(cid):
        return "SEC-004", "medium"
    return "SEC-011", ("medium" if ".audit." in cid else "high")


def run_sast(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """Optional semgrep pass (auto rules), routed by rule family to SEC-011,
    SEC-004 or SEC-014. Supply-chain findings collapse to one per rule and file."""
    notes: list[str] = []
    findings: list[Finding] = []
    if not shutil.which("semgrep"):
        notes.append(
            "SEC-011: semgrep not installed — SAST pass skipped (LLM Layer-2 still runs)."
        )
        return findings, notes
    root = Path(workspace)
    grouped: dict[tuple[str, str], list[int]] = {}
    grouped_msg: dict[tuple[str, str], str] = {}
    dropped = 0
    try:
        proc = subprocess.run(
            ["semgrep", "--config", "auto", "--json", "--quiet", str(root)],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
        )
        data = json.loads(proc.stdout or "{}")
        for res in data.get("results", [])[:400]:
            check_id = res.get("check_id", "semgrep")
            routed = _classify_semgrep(check_id)
            if routed is None:
                dropped += 1
                continue
            cid, confidence = routed
            cond = taxonomy.get(cid)
            if not cond:
                continue
            path = Path(res.get("path", "")).as_posix()
            try:
                path = Path(path).resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                pass
            # Injection and credential-logging rules judge runtime code; IaC,
            # migrations, CI and tests are not where those sinks live.
            if cid != "SEC-014" and any(
                glob_match(path, g) for g in _NON_RUNTIME_SAST_PATHS
            ):
                dropped += 1
                continue
            line = (res.get("start") or {}).get("line")
            message = (res.get("extra") or {}).get("message", "semgrep finding")
            if cid == "SEC-014":
                grouped.setdefault((check_id, path), []).append(line or 0)
                grouped_msg[(check_id, path)] = message
                continue
            f = _mk(cond, path, line, check_id, message)
            f.confidence = confidence
            f.layer = 1
            f.detector = "semgrep"
            findings.append(f)
        cond14 = taxonomy.get("SEC-014")
        if cond14:
            by_rule: dict[str, list[str]] = {}
            for check_id, path in sorted(grouped):
                by_rule.setdefault(check_id, []).append(path)
            for check_id, paths in by_rule.items():
                hits = sum(len(grouped[(check_id, p)]) for p in paths)
                shown = ", ".join(paths[:5])
                if len(paths) > 5:
                    shown += f", +{len(paths) - 5} more"
                f = _mk(
                    cond14,
                    paths[0],
                    None,
                    f"{check_id.rsplit('.', 1)[-1]}: {hits} occurrence(s) in {shown}",
                    grouped_msg[(check_id, paths[0])],
                )
                f.detector = "semgrep"
                findings.append(f)
        if dropped:
            notes.append(
                f"SAST: {dropped} semgrep finding(s) not reported (style/correctness rules, "
                "or hits in test, IaC, migration and CI files)."
            )
    except Exception as e:  # noqa: BLE001
        notes.append(f"SEC-011: semgrep failed: {e}")
    return findings, notes


_TEST_GLOBS = [
    "**/test_*.py",
    "**/*_test.py",
    "**/tests/**",
    "**/*.spec.*",
    "**/*.test.*",
]
_CI_DIRS = [".github/workflows", ".harness", ".circleci", ".buildkite"]
_CI_FILES = [
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
    "bitbucket-pipelines.yml",
    ".travis.yml",
]
_LINT_CONFIG_FILES = (
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    ".flake8",
    ".pylintrc",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.ts",
    ".eslintrc",
    ".eslintrc.json",
    ".eslintrc.js",
    ".eslintrc.cjs",
    "biome.json",
)
_LINT_SECTION_RE = re.compile(r"^\[tool\.(ruff|mypy|pyright|flake8|pylint)", re.M)
_LINT_TOOL_RE = re.compile(
    r"\b(ruff|mypy|pyright|flake8|pylint|eslint|biome|tsc|golangci-lint|lint-check)\b"
)
_VULN_SCAN_RE = re.compile(
    r"trivy|grype|snyk|pip-audit|npm audit|osv-scanner|dependency-review|codeql|anchore",
    re.IGNORECASE,
)
_ACTION_MOVING_REF_RE = re.compile(
    r"^\s*-?\s*uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@(main|master|latest)\s*$",
    re.M,
)
_PY_MANIFESTS = ("pyproject.toml", "requirements.txt", "setup.py", "Pipfile")
_PY_LOCKS = ("uv.lock", "poetry.lock", "Pipfile.lock", "pdm.lock", "requirements.lock")
_JS_LOCKS = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
)
_SKIP_MANIFEST_DIRS = {"node_modules", ".venv", "venv", "dist", "build"}


def _read(p: Path) -> str:
    try:
        return p.read_text(errors="ignore")
    except OSError:
        return ""


def _automation_text(root: Path) -> str:
    """Everything that could invoke a tool: CI workflows, Taskfiles, Makefiles, scripts."""
    chunks: list[str] = []
    for d in _CI_DIRS:
        base = root / d
        if base.is_dir():
            for p in base.rglob("*"):
                if p.is_file() and p.suffix in (".yml", ".yaml"):
                    chunks.append(_read(p))
    for name in _CI_FILES:
        if (root / name).is_file():
            chunks.append(_read(root / name))
    for p in root.rglob("*"):
        if not p.is_file() or _SKIP_MANIFEST_DIRS & set(p.parts):
            continue
        if p.name in (
            "Makefile",
            ".pre-commit-config.yaml",
            "package.json",
        ) or p.name.startswith(("Taskfile", "taskfile")):
            chunks.append(_read(p))
    return "\n".join(chunks)


def _manifest_dirs(root: Path, names: tuple[str, ...]) -> list[Path]:
    dirs: set[Path] = set()
    for p in root.rglob("*"):
        if p.is_file() and p.name in names and not _SKIP_MANIFEST_DIRS & set(p.parts):
            dirs.add(p.parent)
    return sorted(dirs)


def check_presence(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """REL-001 (tests) and REL-002 (CI) presence checks."""
    root = Path(workspace)
    findings: list[Finding] = []
    notes: list[str] = []

    has_tests = any(
        glob_match(rel, g)
        for _p, rel in _iter_files(root, _DEF_EXCLUDE)
        for g in _TEST_GLOBS
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

    ci_exists = any((root / d).is_dir() for d in _CI_DIRS) or any(
        (root / f).exists() for f in _CI_FILES
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
                    "No CI/CD pipeline detected (.github/workflows, .harness, .gitlab-ci.yml, …).",
                )
            )
    return findings, notes


def check_engineering_baseline(
    workspace: str | Path, taxonomy: Taxonomy
) -> tuple[list[Finding], list[str]]:
    """The gates every DataRobot application template ships with: a lint/type-check
    gate (REL-005), lockfiles (REL-006), automated dependency updates (SEC-015),
    vulnerability scanning in CI (SEC-016), CODEOWNERS (ITA-006), and GitHub
    Actions pinned to something immutable (SEC-014)."""
    root = Path(workspace)
    findings: list[Finding] = []
    notes: list[str] = []

    py_dirs = _manifest_dirs(root, _PY_MANIFESTS)
    js_dirs = _manifest_dirs(root, ("package.json",))
    if not py_dirs and not js_dirs:
        notes.append(
            "Engineering baseline: no Python/JS manifests found, checks skipped."
        )
        return findings, notes
    automation = _automation_text(root)

    c = taxonomy.get("REL-005")
    if c:
        has_config = any(
            (d / name).is_file()
            for d in [root, *py_dirs, *js_dirs]
            for name in _LINT_CONFIG_FILES
        ) or any(_LINT_SECTION_RE.search(_read(d / "pyproject.toml")) for d in py_dirs)
        has_invocation = bool(_LINT_TOOL_RE.search(automation))
        if not (has_config and has_invocation):
            missing = []
            if not has_config:
                missing.append(
                    "no linter/type-checker configuration (ruff, mypy, eslint, …)"
                )
            if not has_invocation:
                missing.append("no CI workflow, Taskfile or Makefile that runs one")
            findings.append(
                _mk(
                    c,
                    None,
                    None,
                    "; ".join(missing),
                    "Code style and type errors are not caught before merge.",
                )
            )

    c = taxonomy.get("REL-006")
    if c:
        for d in py_dirs:
            pinned_reqs = any("==" in _read(p) for p in d.glob("requirements*.txt"))
            if not any((d / lock).is_file() for lock in _PY_LOCKS) and not pinned_reqs:
                rel = d.relative_to(root).as_posix() or "."
                findings.append(
                    _mk(
                        c,
                        f"{rel}/pyproject.toml"
                        if (d / "pyproject.toml").is_file()
                        else rel,
                        None,
                        "no uv.lock / poetry.lock / pinned requirements",
                        "Builds are not reproducible; a dependency release can change behaviour.",
                    )
                )
        for d in js_dirs:
            if not any((d / lock).is_file() for lock in _JS_LOCKS):
                rel = d.relative_to(root).as_posix() or "."
                findings.append(
                    _mk(
                        c,
                        f"{rel}/package.json",
                        None,
                        "no package-lock.json / yarn.lock / pnpm-lock.yaml",
                        "Builds are not reproducible; a dependency release can change behaviour.",
                    )
                )

    c = taxonomy.get("SEC-015")
    if c:
        has_updates = any(
            (root / f).is_file()
            for f in (
                ".github/dependabot.yml",
                ".github/dependabot.yaml",
                "renovate.json",
                "renovate.json5",
                ".renovaterc",
                ".renovaterc.json",
                ".github/renovate.json",
                ".github/renovate.json5",
            )
        )
        if not has_updates:
            findings.append(
                _mk(
                    c,
                    None,
                    None,
                    "no .github/dependabot.yml or renovate config",
                    "Vulnerable dependencies stay in place until someone notices.",
                )
            )

    c = taxonomy.get("SEC-016")
    if c:
        has_scan = (
            bool(_VULN_SCAN_RE.search(automation))
            or (root / "trivy-ignore.rego").is_file()
        )
        if not has_scan:
            findings.append(
                _mk(
                    c,
                    None,
                    None,
                    "no trivy / grype / pip-audit / npm audit / dependency-review step in CI",
                    "Known CVEs in dependencies or images are not caught automatically.",
                )
            )

    c = taxonomy.get("ITA-006")
    if c:
        if not any(
            (root / f).is_file()
            for f in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
        ):
            findings.append(
                _mk(
                    c,
                    None,
                    None,
                    "no CODEOWNERS file",
                    "Nobody is automatically accountable for reviewing changes.",
                )
            )

    c = taxonomy.get("SEC-014")
    workflows = root / ".github" / "workflows"
    if c and workflows.is_dir():
        for wf in sorted(workflows.glob("*.y*ml")):
            moving = sorted(
                {
                    f"{m.group(1)}@{m.group(2)}"
                    for m in _ACTION_MOVING_REF_RE.finditer(_read(wf))
                }
            )
            if moving:
                f = _mk(
                    c,
                    wf.relative_to(root).as_posix(),
                    None,
                    "actions on a moving ref: " + ", ".join(moving),
                    "A branch or `latest` ref lets an upstream push change what runs in CI.",
                )
                f.detector = "action_pinning"
                findings.append(f)
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


def run_layer1(
    workspace, taxonomy, exclude=None, progress=None
) -> tuple[list[Finding], list[str]]:
    def _tick(msg: str) -> None:
        if progress:
            progress(msg)

    findings: list[Finding] = []
    notes: list[str] = []
    _tick("Layer 1: secret scan…")
    f, n = run_secret_scan(workspace, taxonomy, exclude)
    findings += f
    notes += n
    for label, fn in (
        ("dependency CVEs (pip-audit)", run_sca),
        ("npm dependency CVEs (npm audit)", run_sca_npm),
        ("SAST (semgrep)", run_sast),
        ("tests/CI presence", check_presence),
        ("engineering baseline", check_engineering_baseline),
    ):
        _tick(f"Layer 1: {label}…")
        f, n = fn(workspace, taxonomy)
        findings += f
        notes += n
    return findings, notes
