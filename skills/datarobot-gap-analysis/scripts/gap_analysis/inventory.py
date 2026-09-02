# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build a file/manifest inventory of a cloned repo.

Pure-stdlib extraction used by the conformance layer and to scope file globs
for the LLM layer. Conservative: when something can't be determined it is left
absent rather than guessed.
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

# Directories always skipped, matched by path component (robust vs. glob quirks).
_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
}

# File extensions we treat as text/source for scanning.
TEXT_EXTS = {
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
    ".txt",
    ".md",
    ".dockerfile",
    ".sh",
}

_DEF_EXCLUDE = [
    "**/.git/**",
    "**/node_modules/**",
    "**/.venv/**",
    "**/venv/**",
    "**/dist/**",
    "**/build/**",
    "**/__pycache__/**",
    "**/*.min.js",
]

_PY_VER_RE = re.compile(
    r"(?:python_requires|requires-python)\s*=\s*['\"]?[^0-9]*([0-9]+\.[0-9]+)"
)
_PYPROJECT_VER_RE = re.compile(r"requires-python\s*=\s*['\"]([^'\"]+)['\"]")
_DOCKER_FROM_RE = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?",
    re.IGNORECASE | re.MULTILINE,
)
_DOCKER_ARG_RE = re.compile(
    r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?\s*$", re.IGNORECASE | re.MULTILINE
)
_DOCKER_VAR_RE = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)"
)
# Model ids like provider/model-name-with-versions, conservative.
_MODEL_RE = re.compile(
    r"['\"]([a-z0-9_.\-]+/[a-z0-9_.\-/@:]*(?:gpt|claude|gemini|llama|mistral|sonnet|opus|haiku)[a-z0-9_.\-/@:]*)['\"]",
    re.IGNORECASE,
)


def glob_match(rel: str, pattern: str) -> bool:
    """fnmatch that lets `**/x` match a root-level `x` (fnmatch has no `**` rule)."""
    if fnmatch.fnmatch(rel, pattern):
        return True
    return pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:])


def _excluded(rel: str, patterns: list[str]) -> bool:
    return any(glob_match(rel, pat) for pat in patterns)


def _iter_files(root: Path, exclude: list[str]):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if _SKIP_DIRS.intersection(p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        if _excluded(rel, exclude):
            continue
        yield p, rel


def build_inventory(
    workspace: str | Path, exclude: list[str] | None = None
) -> dict[str, Any]:
    root = Path(workspace)
    exclude = (exclude or []) + _DEF_EXCLUDE

    files: list[str] = []
    languages: dict[str, int] = {}
    key: dict[str, list[str]] = {
        "config": [],
        "manifests": [],
        "permissions": [],
        "dockerfiles": [],
        "ci": [],
        "tests": [],
        "docs": [],
        "env": [],
    }

    for p, rel in _iter_files(root, exclude):
        files.append(rel)
        ext = p.suffix.lower()
        if ext:
            languages[ext] = languages.get(ext, 0) + 1
        low = rel.lower()
        name = p.name.lower()
        if name in (
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "package.json",
            "poetry.lock",
            "uv.lock",
            "package-lock.json",
        ):
            key["manifests"].append(rel)
        if (
            name.startswith(".env")
            or name == "runtime.txt"
            or name == ".python-version"
        ):
            key["env"].append(rel)
        if (
            name in ("dockerfile",)
            or name.endswith(".dockerfile")
            or name == "containerfile"
        ):
            key["dockerfiles"].append(rel)
        if "permission" in low or "iam" in low or "scopes" in low or "manifest" in name:
            key["permissions"].append(rel)
        if low.startswith(".github/workflows/") or name in (
            ".gitlab-ci.yml",
            "azure-pipelines.yml",
            "jenkinsfile",
        ):
            key["ci"].append(rel)
        if "test" in low or low.endswith("_test.py") or ".spec." in low:
            key["tests"].append(rel)
        if ext == ".md" or low.startswith("docs/"):
            key["docs"].append(rel)
        if name in ("config.py", "settings.py") or ext in (
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
        ):
            key["config"].append(rel)

    return {
        "root": str(root),
        "file_count": len(files),
        "files": files,
        "languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])),
        "key_files": key,
        "python_version": detect_python_version(root),
        "dependencies": extract_dependencies(root),
        "model_ids": extract_model_ids(root, exclude),
        "declared_licenses": extract_declared_licenses(root, exclude),
        "base_images": extract_base_images(root, exclude),
        "base_image_files": base_image_files(root, exclude),
    }


def detect_python_version(root: Path) -> str | None:
    """Best-effort lowest declared Python version (e.g. '3.9')."""
    pv = root / ".python-version"
    if pv.exists():
        m = re.search(r"([0-9]+\.[0-9]+)", pv.read_text())
        if m:
            return m.group(1)
    rt = root / "runtime.txt"
    if rt.exists():
        m = re.search(r"([0-9]+\.[0-9]+)", rt.read_text())
        if m:
            return m.group(1)
    pp = root / "pyproject.toml"
    if pp.exists():
        m = _PYPROJECT_VER_RE.search(pp.read_text())
        if m:
            vm = re.search(r"([0-9]+\.[0-9]+)", m.group(1))
            if vm:
                return vm.group(1)
    for fn in ("setup.py", "setup.cfg"):
        f = root / fn
        if f.exists():
            m = _PY_VER_RE.search(f.read_text())
            if m:
                return m.group(1)
    return None


def _norm_req(spec: str) -> str:
    """'requests>=2.0[extra]' -> 'requests' (lowercased)."""
    return re.split(r"[<>=!~\[ ;@]", spec.strip(), 1)[0].strip().lower()


def extract_dependencies(root: Path) -> list[str]:
    """Normalized lowercase package names declared in manifests."""
    deps: set[str] = set()

    for req in list(root.rglob("requirements*.txt")):
        if _SKIP_DIRS.intersection(req.parts):
            continue
        for line in req.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            name = _norm_req(line)
            if name:
                deps.add(name)

    pp = root / "pyproject.toml"
    if pp.exists() and tomllib:
        try:
            data = tomllib.loads(pp.read_text(errors="ignore"))
        except Exception:
            data = {}
        # PEP 621
        for spec in (data.get("project", {}) or {}).get("dependencies", []) or []:
            n = _norm_req(spec)
            if n:
                deps.add(n)
        for group in (
            (data.get("project", {}) or {}).get("optional-dependencies", {}) or {}
        ).values():
            for spec in group or []:
                n = _norm_req(spec)
                if n:
                    deps.add(n)
        # Poetry
        poetry = (data.get("tool", {}) or {}).get("poetry", {}) or {}
        for key in ("dependencies", "dev-dependencies"):
            for name in poetry.get(key, {}) or {}:
                if name.lower() != "python":
                    deps.add(name.lower())

    pj = root / "package.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text(errors="ignore"))
            for key in ("dependencies", "devDependencies"):
                deps.update(k.lower() for k in (data.get(key, {}) or {}))
        except Exception:
            pass

    return sorted(deps)


_PYPROJECT_LICENSE_RE = re.compile(
    r'^license\s*=\s*(?:\{\s*text\s*=\s*)?["\']([^"\']+)["\']', re.M
)


def extract_declared_licenses(root: Path, exclude: list[str]) -> list[list[str]]:
    """[(manifest rel path, declared SPDX license), ...] from package.json and
    pyproject.toml. Only the repo's own declared license: dependency licenses
    need registry/installed metadata that isn't available offline."""
    out: list[list[str]] = []
    for p, rel in _iter_files(root, exclude):
        if p.name == "package.json":
            try:
                lic = json.loads(p.read_text(errors="ignore")).get("license")
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(lic, str) and lic:
                out.append([rel, lic])
        elif p.name == "pyproject.toml":
            try:
                m = _PYPROJECT_LICENSE_RE.search(p.read_text(errors="ignore"))
            except OSError:
                continue
            if m:
                out.append([rel, m.group(1)])
    return out


def extract_model_ids(root: Path, exclude: list[str]) -> list[str]:
    ids: set[str] = set()
    for p, rel in _iter_files(root, exclude):
        if p.suffix.lower() not in {
            ".py",
            ".ts",
            ".js",
            ".yaml",
            ".yml",
            ".toml",
            ".json",
        }:
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        for m in _MODEL_RE.finditer(text):
            ids.add(m.group(1))
    return sorted(ids)


def _resolve_docker_vars(value: str, args: dict[str, str]) -> str:
    def _sub(m: re.Match[str]) -> str:
        name = m.group(1) or m.group(3)
        resolved = args.get(name) or m.group(2)
        return resolved if resolved is not None else m.group(0)

    return _DOCKER_VAR_RE.sub(_sub, value)


def iter_base_images(root: Path, exclude: list[str] | None = None):
    """Yield (image, dockerfile rel path) for every FROM that names a real image.

    Build args are resolved from their ARG defaults; stage aliases, `scratch`,
    devcontainer Dockerfiles and still-unresolved variables are skipped because
    none of them is an image the policy can judge.
    """
    exclude = (exclude or []) + _DEF_EXCLUDE
    for p, rel in _iter_files(root, exclude):
        if not (p.name.startswith("Dockerfile") or p.suffix.lower() == ".dockerfile"):
            continue
        if ".devcontainer" in p.parts:
            continue
        text = p.read_text(errors="ignore")
        args = {
            m.group(1): (m.group(2) or "").strip().strip("\"'")
            for m in _DOCKER_ARG_RE.finditer(text)
        }
        aliases: set[str] = set()
        for m in _DOCKER_FROM_RE.finditer(text):
            raw, alias = m.group(1), m.group(2)
            img = _resolve_docker_vars(raw, args)
            if alias:
                aliases.add(alias.lower())
            if "$" in img or img.lower() == "scratch" or raw.lower() in aliases:
                continue
            yield img, rel


def extract_base_images(root: Path, exclude: list[str] | None = None) -> list[str]:
    return sorted({img for img, _rel in iter_base_images(root, exclude)})


def base_image_files(
    root: Path, exclude: list[str] | None = None
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for img, rel in iter_base_images(root, exclude):
        out.setdefault(img, []).append(rel)
    return out


def files_matching(inventory: dict[str, Any], globs: list[str]) -> list[str]:
    """Return inventory files matching any of the globs."""
    out = []
    for f in inventory.get("files", []):
        if any(glob_match(f, g) for g in globs):
            out.append(f)
    return out
