# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve DataRobot SDK calls in skills against the installed SDK.

Every ``dr.*`` call in a ``SKILL.md`` python fence or a skill ``scripts/*.py``
is looked up in the real ``datarobot`` package and its signature checked, so
methods that do not exist and calls with wrong arguments are caught without a
DataRobot account, a coding agent, or an AutoML run.

Run directly to list findings while fixing them::

    uv run --group integration python tests/integration/sdk_conformance.py
"""

from __future__ import annotations

import ast
import inspect
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import datarobot as dr

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

PY_FENCE = re.compile(r"```(?:python|py)\n(.*?)```", re.S)
SDK_ALIASES = {"dr", "datarobot"}

# Nodes that introduce a new variable scope.  Type inference is per-scope so a
# name reused for different SDK types in sibling functions is not conflated.
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)

# Methods assumed to return an instance of their own class, subject to the
# return-annotation check in _infer_var_types.  ``create`` is deliberately
# included but guarded: e.g. PredictionExplanations.create() returns a Job.
FACTORY_PREFIXES = ("create_from", "from_")
FACTORY_NAMES = ("get", "create")

# NOTE: deprecation detection is intentionally absent.  The SDK signals
# deprecations with a runtime decorator rather than docstring text, so a static
# check gives false confidence.  Importing under ``-W error::DeprecationWarning``
# is the right tool for that.


@dataclass(frozen=True)
class Finding:
    """A single SDK conformance violation."""

    file: str
    line: int
    kind: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} [{self.kind}] {self.message}"


def _dotted_name(node: ast.AST) -> str | None:
    """Flatten an attribute chain (``dr.Project.start``) into a dotted string."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _resolve(attr_path: list[str]) -> tuple[Any, bool]:
    """Walk an attribute path from the datarobot module."""
    obj: Any = dr
    for part in attr_path:
        if not hasattr(obj, part):
            return None, False
        obj = getattr(obj, part)
    return obj, True


def _scope_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """Yield nodes belonging to ``scope``, without entering nested scopes."""
    for child in ast.iter_child_nodes(scope):
        if isinstance(child, SCOPE_NODES):
            continue
        yield child
        yield from _scope_nodes(child)


def _nested_scopes(scope: ast.AST) -> Iterator[ast.AST]:
    """Yield the scopes directly nested inside ``scope`` (not their children)."""
    for child in ast.iter_child_nodes(scope):
        if isinstance(child, SCOPE_NODES):
            yield child
        else:
            yield from _nested_scopes(child)


def _infer_var_types(nodes: Iterable[ast.AST], aliases: set[str]) -> dict[str, type]:
    """Map ``x = dr.Foo.get(...)`` to ``x: Foo`` so instance calls can be checked."""
    var_types: dict[str, type] = {}
    for node in nodes:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        name = _dotted_name(node.value.func)
        if not name:
            continue
        parts = name.split(".")
        if parts[0] not in aliases or len(parts) < 3:
            continue
        method = parts[-1]
        if not (method in FACTORY_NAMES or method.startswith(FACTORY_PREFIXES)):
            continue
        cls, ok = _resolve(parts[1:-1])
        if not (ok and inspect.isclass(cls)):
            continue
        # Only infer when the factory really returns its own class.
        try:
            annotation = str(inspect.signature(getattr(cls, method)).return_annotation)
        except (ValueError, TypeError):
            annotation = ""
        if (
            annotation
            and "inspect._empty" not in annotation
            and cls.__name__ not in annotation
        ):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_types[target.id] = cls
    return var_types


def _check_signature(
    call: ast.Call, target: Any, display: str, drop_self: bool
) -> list[tuple[str, str]]:
    """Return (kind, message) pairs for signature violations."""
    out: list[tuple[str, str]] = []
    if not callable(target):
        return out
    try:
        signature = inspect.signature(target)
    except (ValueError, TypeError):
        return out

    params = list(signature.parameters.values())
    if drop_self and params and params[0].name in ("self", "cls"):
        params = params[1:]

    names = {p.name for p in params}
    accepts_kwargs = any(p.kind is p.VAR_KEYWORD for p in params)
    accepts_varargs = any(p.kind is p.VAR_POSITIONAL for p in params)
    passed_kw = {kw.arg for kw in call.keywords if kw.arg}

    unknown = passed_kw - names
    if unknown and not accepts_kwargs:
        out.append(
            (
                "bad-kwarg",
                f"`{display}()` got unexpected keyword(s) {sorted(unknown)}; "
                f"valid: {sorted(names)[:9]}",
            )
        )

    # A named keyword is checkable even alongside a splat, but arity is not:
    # ``f(**opts)`` may well supply every required parameter.
    splatted = any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        kw.arg is None for kw in call.keywords
    )
    if accepts_varargs or splatted:
        return out

    required = [
        p
        for p in params
        if p.default is inspect.Parameter.empty
        and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    n_positional = len(call.args)
    missing = [
        p.name
        for i, p in enumerate(required)
        if p.name not in passed_kw and i >= n_positional
    ]
    if missing and missing[0] in ("self", "cls"):
        # Reached through the class rather than an instance, so the receiver is
        # unbound.  Reporting a literal "self" as missing only confuses.
        out.append(
            (
                "instance-method-on-class",
                f"`{display}()` is an instance method reached through the class, "
                "so there is no receiver; call it on an instance",
            )
        )
    elif missing:
        out.append(("missing-arg", f"`{display}()` missing required arg(s) {missing}"))
    return out


def _check_call(
    call: ast.Call,
    aliases: set[str],
    var_types: dict[str, type],
    rel_path: str,
    line_offset: int,
) -> list[Finding]:
    name = _dotted_name(call.func)
    if not name:
        return []
    parts = name.split(".")
    line = call.lineno + line_offset
    found: list[Finding] = []

    def note(kind: str, message: str) -> None:
        found.append(Finding(rel_path, line, kind, message))

    classmethod_via_instance = False

    if parts[0] in aliases:
        # dr.Foo.bar(...) — resolvable directly against the module.
        target, ok = _resolve(parts[1:])
        if not ok:
            note(
                "missing-symbol",
                f"`{name}` does not exist in datarobot {dr.__version__}",
            )
            return found
        drop_self = False
    elif len(parts) == 2 and parts[0] in var_types:
        # instance.bar(...) — the descriptor kind decides how args bind.
        cls = var_types[parts[0]]
        if not hasattr(cls, parts[1]):
            note("missing-method", f"`{cls.__name__}.{parts[1]}` does not exist")
            return found
        static = inspect.getattr_static(cls, parts[1], None)
        target = getattr(cls, parts[1])
        # getattr() pre-binds cls for classmethods but leaves `self` on plain
        # methods, so only the latter needs its first parameter dropped.
        drop_self = not isinstance(static, (classmethod, staticmethod))
        classmethod_via_instance = isinstance(static, classmethod)
    else:
        return found

    problems = _check_signature(call, target, name, drop_self)

    # Reaching a classmethod through an instance is legal and works when the
    # arguments are supplied, so it is only worth reporting as the explanation
    # for an arity failure.
    if classmethod_via_instance and any(kind == "missing-arg" for kind, _ in problems):
        note(
            "classmethod-on-instance",
            f"`{name}()` calls a CLASSMETHOD on an instance "
            f"({var_types[parts[0]].__name__}.{parts[1]}) — required args are "
            "not auto-filled",
        )

    for kind, message in problems:
        note(kind, message)
    return found


def _analyse_source(
    source: str, rel_path: str, line_offset: int = 0
) -> tuple[list[Finding], bool]:
    """Analyse one code chunk. Returns (findings, parsed_ok)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], False

    aliases = set(SDK_ALIASES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "datarobot" and alias.asname:
                    aliases.add(alias.asname)

    def walk_scope(scope: ast.AST, inherited: dict[str, type]) -> list[Finding]:
        nodes = list(_scope_nodes(scope))
        # Names bound here shadow anything inherited from an enclosing scope.
        var_types = {**inherited, **_infer_var_types(nodes, aliases)}
        findings = [
            finding
            for node in nodes
            if isinstance(node, ast.Call)
            for finding in _check_call(node, aliases, var_types, rel_path, line_offset)
        ]
        for nested in _nested_scopes(scope):
            findings.extend(walk_scope(nested, var_types))
        return findings

    return walk_scope(tree, {}), True


def analyse_skill(skill_dir: Path) -> list[Finding]:
    """Collect SDK conformance findings for one skill directory.

    Nested SKILL.md files are included: agent-assist ships sub-skills in
    subdirectories whose fences need the same checking.
    """
    findings: list[Finding] = []

    for skill_md in sorted(skill_dir.rglob("SKILL.md")):
        text = skill_md.read_text()
        rel = str(skill_md.relative_to(REPO_ROOT))
        for match in PY_FENCE.finditer(text):
            offset = text[: match.start()].count("\n") + 1
            chunk, parsed = _analyse_source(match.group(1), rel, offset)
            if not parsed:
                # Skipping silently would let a fence full of SDK calls go
                # unchecked while this still reported success.
                findings.append(
                    Finding(
                        rel,
                        offset,
                        "unparseable-fence",
                        "python fence does not parse, so its SDK calls cannot be "
                        "checked; fix the snippet or retag the fence",
                    )
                )
                continue
            findings.extend(chunk)

    for script in sorted(skill_dir.rglob("*.py")):
        rel = str(script.relative_to(REPO_ROOT))
        chunk, parsed = _analyse_source(script.read_text(), rel)
        if not parsed:
            findings.append(
                Finding(rel, 1, "unparseable-script", "file does not parse")
            )
            continue
        findings.extend(chunk)

    return findings


def skill_dirs() -> list[Path]:
    return sorted(
        d for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


if __name__ == "__main__":
    total = 0
    for directory in skill_dirs():
        for finding in analyse_skill(directory):
            print(finding)
            total += 1
    print(f"\n{total} finding(s) against datarobot {dr.__version__}")
