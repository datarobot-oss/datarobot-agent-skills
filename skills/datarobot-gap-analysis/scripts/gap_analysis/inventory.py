# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build a file/manifest inventory of a cloned repo.

Pure-stdlib extraction used by the conformance layer and to scope file globs
for the LLM layer. Conservative: when something can't be determined it is left
absent rather than guessed.
"""

from __future__ import annotations

import fnmatch
import os
import json
import re
import urllib.request
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
    "**/htmlcov/**",
    "**/coverage/**",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.ruff_cache/**",
    "**/*.pyc",
    "**/*.tar",
    "**/*.lock",
    "**/package-lock.json",
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

    deps = extract_dependencies(root)
    model_ids = extract_model_ids(root, exclude)
    agent_frameworks = detect_agent_frameworks(deps)
    llm_usage = detect_llm_usage(root, files, deps, model_ids)
    model_code = detect_model_code(root, files, deps)
    return {
        "root": str(root),
        "file_count": len(files),
        "files": files,
        "languages": dict(sorted(languages.items(), key=lambda kv: -kv[1])),
        "key_files": key,
        "python_version": detect_python_version(root),
        "python_versions": detect_python_versions(root),
        "dependencies": deps,
        "model_ids": model_ids,
        "declared_licenses": extract_declared_licenses(root, exclude),
        "base_images": extract_base_images(root, exclude),
        "base_image_files": base_image_files(root, exclude),
        "template_sources": detect_template_sources(root),
        "datarobot_app": detect_datarobot_app(root, files),
        "llm_usage": llm_usage,
        "model_code": model_code,
        "deploy_target": infer_deploy_target(agent_frameworks, llm_usage, model_code),
        "agent_template_choices": agent_template_choices(),
        "agent_frameworks": agent_frameworks,
    }


def detect_python_versions(root: Path) -> dict[str, str]:
    """Declared Python floor per component ({relative dir: '3.12'}), from
    .python-version, runtime.txt, pyproject.toml, setup.py and setup.cfg
    anywhere in the repo. Multi-component templates declare one per component
    and often nothing at the root."""
    found: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or _SKIP_DIRS.intersection(p.parts):
            continue
        rel = p.parent.relative_to(root)
        # Hidden directories (docs/.bin, backend/.internals) hold tooling, not components.
        if any(part.startswith(".") for part in rel.parts):
            continue
        rel_dir = rel.as_posix() or "."
        if rel_dir in found:
            continue
        m: re.Match[str] | None
        if p.name in (".python-version", "runtime.txt"):
            m = re.search(r"([0-9]+\.[0-9]+)", p.read_text(errors="ignore"))
        elif p.name == "pyproject.toml":
            m = _PYPROJECT_VER_RE.search(p.read_text(errors="ignore"))
            m = re.search(r"([0-9]+\.[0-9]+)", m.group(1)) if m else None
        elif p.name in ("setup.py", "setup.cfg"):
            m = _PY_VER_RE.search(p.read_text(errors="ignore"))
        else:
            continue
        if m:
            found[rel_dir] = m.group(1)
    return found


def detect_python_version(root: Path) -> str | None:
    """The lowest Python floor declared anywhere in the repo (e.g. '3.10'), the
    version a minimum-version policy has to be judged against."""
    versions = detect_python_versions(root)
    if not versions:
        return None
    return min(versions.values(), key=lambda v: tuple(int(x) for x in v.split(".")))


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

    pyprojects = [
        pp
        for pp in root.rglob("pyproject.toml")
        if not _SKIP_DIRS.intersection(pp.parts)
    ]
    for pp in pyprojects if tomllib else []:
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


_EVIDENCE_RANK = {
    ".py": 0,
    ".ts": 1,
    ".tsx": 1,
    ".js": 1,
    ".jsx": 1,
    ".go": 1,
    ".md": 2,
    ".txt": 2,
    ".toml": 3,
    ".yaml": 4,
    ".yml": 4,
    ".json": 5,
    ".cfg": 5,
    ".ini": 5,
}
_EVIDENCE_SKIP = (
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
)


def _is_catch_all(glob: str) -> bool:
    """`**/*.py`-style globs name a file type, not a file or directory; they rank last."""
    segments = glob.split("/")
    if any(not any(ch in seg for ch in "*?[") for seg in segments):
        return False
    base = segments[-1]
    return base in ("*", "**") or (base.startswith("*.") and "*" not in base[2:])


def evidence_files(
    inventory: dict[str, Any],
    globs: list[str],
    limit: int,
    first: list[str] | None = None,
) -> list[str]:
    """The files an LLM judge should read for a condition, best evidence first.

    Files matched by a named glob (`**/*prompt*`, `**/infra/**`) come before
    files matched only by a file-type glob (`**/*.py`); within each group source
    outranks config and config outranks data, and lockfiles never make the cut.
    `first` pins known-relevant files to the front.
    """
    catch_all = [g for g in globs if _is_catch_all(g)]
    specific = [g for g in globs if not _is_catch_all(g)]

    def _key(f: str) -> tuple[int, int, int, str]:
        named = 0 if any(glob_match(f, g) for g in specific) else 1
        return (named, _EVIDENCE_RANK[Path(f).suffix.lower()], f.count("/"), f)

    ranked = sorted(
        (
            f
            for f in files_matching(inventory, specific + catch_all)
            if Path(f).name not in _EVIDENCE_SKIP
            and Path(f).suffix.lower() in _EVIDENCE_RANK
        ),
        key=_key,
    )
    out: list[str] = []
    for f in [*(first or []), *ranked]:
        if f not in out:
            out.append(f)
        if len(out) >= limit:
            break
    return out


_SRC_PATH_RE = re.compile(r"^_src_path:\s*(\S+)", re.MULTILINE)

# Agent framework packages a repo may depend on: package -> (display name, the
# af-component-agent `agent_template_framework` value it corresponds to).
_AGENT_PACKAGES: dict[str, tuple[str, str]] = {
    "langgraph": ("LangGraph", "langgraph"),
    "langchain": ("LangChain", "langchain"),
    "crewai": ("CrewAI", "crewai"),
    "llama-index": ("LlamaIndex", "llamaindex"),
    "llama-index-core": ("LlamaIndex", "llamaindex"),
    "nvidia-nat": ("NVIDIA NAT", "nat"),
    "pydantic-ai": ("pydantic-ai", "pydantic-ai"),
    "pydantic-ai-slim": ("pydantic-ai", "pydantic-ai"),
    "deepagents": ("deepagents", "deepagents"),
    "autogen-agentchat": ("AutoGen", "autogen"),
    "pyautogen": ("AutoGen", "autogen"),
    "smolagents": ("smolagents", "smolagents"),
    "openai-agents": ("OpenAI Agents SDK", "openai-agents"),
    "semantic-kernel": ("Semantic Kernel", "semantic-kernel"),
    "agno": ("Agno", "agno"),
}

# The flavors DataRobot's agent application template offers are read from the
# template itself; this is the snapshot used when the fetch is off or offline.
_AGENT_TEMPLATE_COPIER_URL = "https://raw.githubusercontent.com/datarobot-community/af-component-agent/main/copier.yml"
_AGENT_TEMPLATE_CHOICES_FALLBACK: dict[str, str] = {
    "Base": "base",
    "CrewAI": "crewai",
    "LangGraph": "langgraph",
    "LlamaIndex": "llamaindex",
    "NeMo Agent Toolkit (NAT)": "nat",
}
_agent_template_choices_cache: dict[str, str] | None = None


def agent_template_choices() -> dict[str, str]:
    """{label: value} of `agent_template_framework` in af-component-agent's copier.yml.

    Set GAP_AGENT_TEMPLATE_CATALOG=off to skip the network and use the snapshot.
    """
    global _agent_template_choices_cache
    if _agent_template_choices_cache is not None:
        return _agent_template_choices_cache
    choices: dict[str, str] = {}
    if os.environ.get("GAP_AGENT_TEMPLATE_CATALOG", "").lower() != "off":
        try:
            with urllib.request.urlopen(_AGENT_TEMPLATE_COPIER_URL, timeout=8) as resp:
                text = resp.read().decode("utf-8", "ignore")
            block = re.search(
                r"^agent_template_framework:\n(.*?)(?=^\S)", text, re.S | re.M
            )
            if block:
                for m in re.finditer(
                    r'^\s{4}"?([^":\n]+)"?:\s*([A-Za-z0-9_-]+)\s*$',
                    block.group(1),
                    re.M,
                ):
                    choices[m.group(1).strip()] = m.group(2).strip()
        except (OSError, ValueError):
            choices = {}
    _agent_template_choices_cache = choices or dict(_AGENT_TEMPLATE_CHOICES_FALLBACK)
    return _agent_template_choices_cache


_DR_APP_RESOURCE_RE = re.compile(r"\b(ApplicationSource|CustomApplication)(?:Args)?\(")
_PULUMI_IMPORT_RE = re.compile(
    r"pulumi_datarobot|pulumi-datarobot|datarobot_pulumi_utils"
)


def detect_datarobot_app(root: Path, files: list[str]) -> dict[str, str] | None:
    """{file, resource} when a Pulumi program deploys this repo as a DataRobot
    custom application, else None. Only .py files that import the DataRobot
    Pulumi provider count, so a docs mention does not qualify."""
    for rel in files:
        if not rel.endswith(".py"):
            continue
        try:
            text = (root / rel).read_text(errors="ignore")
        except OSError:
            continue
        if not _PULUMI_IMPORT_RE.search(text):
            continue
        m = _DR_APP_RESOURCE_RE.search(text)
        if m:
            return {"file": rel, "resource": m.group(1)}
    return None


_LLM_CLIENT_PACKAGES = {
    "openai",
    "anthropic",
    "litellm",
    "langchain-openai",
    "langchain-anthropic",
    "langchain-google-genai",
    "google-generativeai",
    "google-genai",
    "cohere",
    "mistralai",
    "groq",
    "together",
    "ollama",
    "instructor",
    "dspy",
    "dspy-ai",
    "datarobot-genai",
}
_LLM_GATEWAY_RE = re.compile(
    r"genai/llmgw|\bllmgw\b|llm[_-]gateway|USE_DATAROBOT_LLM_GATEWAY|LLMGateway",
    re.IGNORECASE,
)
_LLM_GATEWAY_EXTS = (".py", ".ts", ".tsx", ".js", ".toml", ".yaml", ".yml", ".env")
_TEST_PART_RE = re.compile(r"(^|/)(tests?|__tests__|fixtures)(/|$)|(^|/)test_[^/]*$")
_MODEL_HOOK_RE = re.compile(r"^def (score|load_model|chat|transform|fit)\(", re.M)


def detect_llm_usage(
    root: Path, files: list[str], deps: list[str], model_ids: list[str]
) -> dict[str, Any]:
    """Whether the repo calls an LLM at all, and whether those calls go through
    the DataRobot LLM Gateway.

    {present, gateway, evidence, gateway_evidence}. `present` comes from agent
    framework or LLM client packages among the declared dependencies, or model
    ids in code; `gateway` from a gateway URL or flag anywhere outside tests.
    """
    norm = {d.lower().replace("_", "-") for d in deps}
    evidence = next(
        (d for d in sorted(norm) if d in _LLM_CLIENT_PACKAGES or d in _AGENT_PACKAGES),
        None,
    )
    present = evidence is not None or bool(model_ids)
    gateway_evidence = None
    for rel in files:
        name = rel.rsplit("/", 1)[-1]
        if not (rel.endswith(_LLM_GATEWAY_EXTS) or name.startswith(".env")):
            continue
        if _TEST_PART_RE.search(rel):
            continue
        try:
            text = (root / rel).read_text(errors="ignore")
        except OSError:
            continue
        if _LLM_GATEWAY_RE.search(text):
            gateway_evidence = rel
            break
    return {
        "present": present or gateway_evidence is not None,
        "gateway": gateway_evidence is not None,
        "evidence": evidence or (model_ids[0] if model_ids else None),
        "gateway_evidence": gateway_evidence,
    }


def detect_model_code(
    root: Path, files: list[str], deps: list[str]
) -> dict[str, str] | None:
    """{file} when the repo carries a model meant to be served (a DRUM-style
    custom.py with score/load_model/chat hooks, a model-metadata.yaml, or the
    datarobot-drum package), else None."""
    norm = {d.lower().replace("_", "-") for d in deps}
    for rel in files:
        if _TEST_PART_RE.search(rel):
            continue
        name = rel.rsplit("/", 1)[-1]
        if name in ("model-metadata.yaml", "model-metadata.yml"):
            return {"file": rel}
        if name == "custom.py":
            try:
                text = (root / rel).read_text(errors="ignore")
            except OSError:
                continue
            if _MODEL_HOOK_RE.search(text):
                return {"file": rel}
    if "datarobot-drum" in norm:
        return {"file": "datarobot-drum dependency"}
    return None


PREDICTIVE_TARGET = "Predictive"


def infer_deploy_target(
    agent_frameworks: list[dict[str, Any]],
    llm_usage: dict[str, Any],
    model_code: dict[str, str] | None,
) -> str | None:
    """The DataRobot target type this repo's model or LLM path would deploy as:
    AgenticWorkflow for an agent, TextGeneration for a plain LLM app, the
    Predictive placeholder for a scoring model (the exact type is not knowable
    from code), None when the repo has neither."""
    if agent_frameworks:
        return "AgenticWorkflow"
    if llm_usage.get("present"):
        return "TextGeneration"
    if model_code:
        return PREDICTIVE_TARGET
    return None


def detect_template_sources(root: Path) -> list[str]:
    """Copier templates this repo was generated from (repo names), from
    `.datarobot/answers/*.yml` and `.copier-answers.yml`."""
    sources: set[str] = set()
    files = list((root / ".datarobot" / "answers").glob("*.y*ml")) + [
        root / ".copier-answers.yml"
    ]
    for f in files:
        if not f.is_file():
            continue
        for m in _SRC_PATH_RE.finditer(f.read_text(errors="ignore")):
            name = m.group(1).rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            sources.add(name[:-4] if name.endswith(".git") else name)
    return sorted(sources)


def detect_agent_frameworks(
    deps: list[str], choices: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """[{name, native}] for every agent framework among the declared dependencies.

    `native` means the af-component-agent template offers a flavor for it (per
    `choices`, the template's `agent_template_framework` values); anything else
    deploys through the generic Base flavor.
    """
    native_values = set((choices or agent_template_choices()).values())
    seen: dict[str, bool] = {}
    for dep in deps:
        hit = _AGENT_PACKAGES.get(dep.lower().replace("_", "-"))
        if hit:
            seen.setdefault(hit[0], hit[1] in native_values)
    return [{"name": n, "native": native} for n, native in sorted(seen.items())]
