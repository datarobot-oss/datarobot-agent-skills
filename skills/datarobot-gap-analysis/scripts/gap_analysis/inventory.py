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
_DOCKER_FROM_RE = re.compile(r"^\s*FROM\s+([^\s]+)", re.IGNORECASE | re.MULTILINE)
# Model ids like provider/model-name-with-versions, conservative.
_MODEL_RE = re.compile(
    r"['\"]([a-z0-9_.\-]+/[a-z0-9_.\-/@:]*(?:gpt|claude|gemini|llama|mistral|sonnet|opus|haiku)[a-z0-9_.\-/@:]*)['\"]",
    re.IGNORECASE,
)


def _excluded(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


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
        "base_images": extract_base_images(root, exclude),
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


def extract_base_images(root: Path, exclude: list[str] | None = None) -> list[str]:
    imgs: set[str] = set()
    exclude = (exclude or []) + _DEF_EXCLUDE
    for p, _rel in _iter_files(root, exclude):
        if p.name != "Dockerfile" and p.suffix.lower() != ".dockerfile":
            continue
        for m in _DOCKER_FROM_RE.finditer(p.read_text(errors="ignore")):
            img = m.group(1)
            if img.lower() != "scratch":
                imgs.add(img)
    return sorted(imgs)


def files_matching(inventory: dict[str, Any], globs: list[str]) -> list[str]:
    """Return inventory files matching any of the globs."""
    out = []
    for f in inventory.get("files", []):
        if any(fnmatch.fnmatch(f, g) for g in globs):
            out.append(f)
    return out
