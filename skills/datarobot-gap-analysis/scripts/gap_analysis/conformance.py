# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Layer 3 — conformance of the repo against the merged policy."""

from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import threading

from typing import Any

from .models import Finding
from .taxonomy import Condition, Taxonomy


def _ver_tuple(v: str, width: int = 3) -> tuple[int, ...]:
    """A comparable version tuple, zero-padded: "3.11" and "3.11.0" are equal,
    where the raw split tuples would order the shorter one first."""
    parts = tuple(int(x) for x in v.split(".") if x.isdigit())
    return parts + (0,) * max(0, width - len(parts))


def _glob_any(value: str, patterns: list[str]) -> bool:
    """True when `value` matches any of the patterns (allow/deny lists)."""
    return any(fnmatch.fnmatch(value, p) for p in patterns)


def _matched_by(pattern: str, values: set[str] | list[str]) -> bool:
    """True when any value matches `pattern` (a require entry is the pattern)."""
    return any(fnmatch.fnmatch(v, pattern) for v in values)


_GATEWAY_MODELS: list[str] | None = None
_GATEWAY_LOCK = threading.Lock()


def llm_gateway_models(offline: bool = False) -> list[str]:
    """Model ids served by the org's DataRobot LLM Gateway, via `dr llm-gateway list`.

    Empty when the CLI is missing, unauthenticated, slow, or `offline`. Models
    the gateway serves are governed by the platform, so they count as approved
    alongside the policy allowlist.

    Layer 2 workers and Layer 3 call this from different threads, so the cache
    is only published once the fetch has finished: an empty list means "asked
    and got nothing", never "asking right now".
    """
    global _GATEWAY_MODELS
    if _GATEWAY_MODELS is not None:
        return _GATEWAY_MODELS
    with _GATEWAY_LOCK:
        if _GATEWAY_MODELS is not None:
            return _GATEWAY_MODELS
        models: list[str] = []
        dr = shutil.which("dr")
        if dr and not offline:
            try:
                proc = subprocess.run(
                    [dr, "llm-gateway", "list", "--output-format", "json"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                data = json.loads(proc.stdout or "{}")
                models = sorted(
                    {m.get("model") for m in data.get("llms", []) if m.get("model")}
                )
            except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError):
                models = []
        _GATEWAY_MODELS = models
        return _GATEWAY_MODELS


def _gateway_serves(model_id: str, catalog: list[str]) -> bool:
    return model_id in catalog or any(g.startswith(model_id + "-") for g in catalog)


def check_conformance(
    inventory: dict[str, Any],
    policy: dict[str, Any],
    taxonomy: Taxonomy,
    offline: bool = False,
) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    notes: list[str] = []
    it = policy.get("it_admin", {})

    # ITA-001 — Python minimum version
    cond = taxonomy.get("ITA-001")
    min_v = (it.get("python", {}) or {}).get("min_version")
    repo_v = inventory.get("python_version")
    if cond and min_v:
        if repo_v is None:
            notes.append(
                "ITA-001: no declared Python version found — cannot confirm minimum."
            )
        elif _ver_tuple(repo_v) < _ver_tuple(str(min_v)):
            findings.append(
                _mk(
                    cond,
                    _py_source(inventory),
                    None,
                    f"declared Python {repo_v} < required {min_v}",
                    f"Project targets Python {repo_v}; policy requires >= {min_v}.",
                )
            )

    # ITA-002 — library allow/deny/require
    cond = taxonomy.get("ITA-002")
    libs = it.get("libraries", {}) or {}
    deps = set(inventory.get("dependencies", []))
    if cond:
        allow = [a.lower() for a in libs.get("allow", []) or []]
        deny = [d.lower() for d in libs.get("deny", []) or []]
        require = [r.lower() for r in libs.get("require", []) or []]
        for dep in sorted(deps):
            if dep in deny:
                findings.append(
                    _mk(
                        cond,
                        _manifest(inventory),
                        None,
                        dep,
                        f"Dependency '{dep}' is on the policy deny list.",
                    )
                )
            elif allow and not _glob_any(dep, allow):
                findings.append(
                    _mk(
                        cond,
                        _manifest(inventory),
                        None,
                        dep,
                        f"Dependency '{dep}' is not on the policy allow list.",
                    )
                )
        for req in require:
            if req not in deps and not _matched_by(req, deps):
                findings.append(
                    _mk(
                        cond,
                        _manifest(inventory),
                        None,
                        req,
                        f"Required library '{req}' is missing from dependencies.",
                    )
                )

    # AIG-003 / ITA-003 — approved models
    allow_models = (it.get("models", {}) or {}).get("allow", []) or []
    catalog = (
        llm_gateway_models(offline)
        if allow_models and inventory.get("model_ids")
        else []
    )
    if catalog:
        notes.append(
            f"AIG-003/ITA-003: {len(catalog)} model id(s) served by the DataRobot LLM "
            "Gateway are treated as approved."
        )
    for cid in ("AIG-003", "ITA-003"):
        cond = taxonomy.get(cid)
        if not cond or not allow_models:
            continue
        seen: set[str] = set()
        for mid in inventory.get("model_ids", []):
            if mid in seen:
                continue
            seen.add(mid)
            if not _glob_any(mid, allow_models) and not _gateway_serves(mid, catalog):
                findings.append(
                    _mk(
                        cond,
                        None,
                        None,
                        mid,
                        f"Model '{mid}' is not on the approved-model allowlist.",
                    )
                )

    # ITA-005 — approved base images
    cond = taxonomy.get("ITA-005")
    allow_imgs = (it.get("base_images", {}) or {}).get("allow", []) or []
    if cond and allow_imgs:
        image_files = inventory.get("base_image_files") or {}
        for img in inventory.get("base_images", []):
            if not _glob_any(img, allow_imgs):
                findings.append(
                    _mk(
                        cond,
                        (image_files.get(img) or [_dockerfile(inventory)])[0],
                        None,
                        img,
                        f"Base image '{img}' is not on the approved-image allowlist.",
                    )
                )

    # ITA-004 — offline coverage is limited to the repo's own declared license
    # (package.json / pyproject.toml); dependency licenses need registry or
    # installed-package metadata.
    cond = taxonomy.get("ITA-004")
    deny_licenses = (it.get("licenses", {}) or {}).get("deny") or []
    if cond and deny_licenses:
        for rel, lic in inventory.get("declared_licenses", []) or []:
            if lic in deny_licenses:
                findings.append(
                    _mk(
                        cond,
                        rel,
                        None,
                        lic,
                        f"Manifest declares license '{lic}', which is on the "
                        "org's denied-license list.",
                    )
                )
        notes.append(
            "ITA-004: dependency licenses require installed package metadata; "
            "only the repo's own declared license was checked offline."
        )

    return findings, notes


_PY_FLOOR_FILES = (
    ".python-version",
    "runtime.txt",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
)


def _py_source(inv: dict[str, Any]) -> str | None:
    """The file that declares the lowest Python floor: the manifest in the
    component directory the inventory attributed that floor to."""
    versions = inv.get("python_versions") or {}
    floor = inv.get("python_version")
    files = set(inv.get("files", []))
    dirs = sorted(d for d, v in versions.items() if v == floor) or sorted(versions)
    for d in dirs:
        for name in _PY_FLOOR_FILES:
            rel = name if d in (".", "") else f"{d}/{name}"
            if rel in files:
                return rel
    man = inv.get("key_files", {}).get("manifests", [])
    return str(man[0]) if man else None


def _manifest(inv: dict[str, Any]) -> str | None:
    man = inv.get("key_files", {}).get("manifests")
    return str(man[0]) if man else None


def _dockerfile(inv: dict[str, Any]) -> str | None:
    files = inv.get("key_files", {}).get("dockerfiles")
    return str(files[0]) if files else None


def _mk(
    cond: Condition,
    file: str | None,
    line: int | None,
    evidence: str,
    explanation: str,
) -> Finding:
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
