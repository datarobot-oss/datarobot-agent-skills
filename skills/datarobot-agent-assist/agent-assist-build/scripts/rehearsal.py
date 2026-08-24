#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DataRobot Dress Rehearsal engine (datarobot-agent-assist skill)

Init:  python3 rehearsal.py --init [--spec agent_spec.md] --target-dir <directory>
         stdout: session=<session_dir>  output=<output_file>
Turn:  python3 rehearsal.py --session <session_dir> [--target-dir <directory>] "user message"
         stdout: output=<output_file>

From repository root, use:
  python3 skills/datarobot-agent-assist/rehearsal.py ...
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import functools
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from env_utils import get_datarobot_credentials
from list_llm_models import (
    DEPLOYED_LLM_MODEL,
    LLMModel,
    SOURCE_DEPLOYED,
    SOURCE_GATEWAY,
    fetch_llm_models,
    is_deployed_llm_model,
    is_deployment_id,
    normalize_gateway_model,
)

# Model used for spec extraction and tool simulation.
# The agent's own model (from the spec) is used for the main turn loop.
SIMULATION_MODEL = os.environ.get(
    "DR_SIMULATION_MODEL", "bedrock/anthropic.claude-sonnet-4-6"
)

# ── helpers ───────────────────────────────────────────────────────────────────


def progress(msg: str) -> None:
    print(f"[rehearsal] {msg}", file=sys.stderr, flush=True)


def _symmetric_turn_decoration(width: int = 44) -> str:
    center = "★ Agent Dress Rehearsal ★"
    pad = width - len(center)
    left = pad // 2
    return "─" * left + center + "─" * (pad - left)


TURN_DECORATION = _symmetric_turn_decoration()
DONE_HINT = "Type DONE to end the rehearsal session."


def print_turn_header() -> None:
    print(TURN_DECORATION)
    sys.stdout.flush()


def print_turn_footer() -> None:
    print()
    print(TURN_DECORATION)
    print("Type your next message to continue.")
    print("Use NOTE: <text> to record a design observation.")
    print(DONE_HINT)
    print()
    sys.stdout.flush()


def print_agent_response(content: str) -> None:
    """Agent reply plus mandatory turn footer (always printed together)."""
    print(f"[Agent]: {content}")
    print_turn_footer()


def print_init_banner(body_lines: list[str]) -> None:
    description = (
        "A try-before-you-build session: chat with your agent design as if it were "
        "already running. Tool calls return simulated data — no real APIs, no "
        "deployment, and no code written yet."
    )
    print("════════════════════════════════════════════")
    print("  AGENT DRESS REHEARSAL")
    print("════════════════════════════════════════════")
    print(f"  {description}")
    print("════════════════════════════════════════════")
    print()
    for line in body_lines:
        print(line)
    print("════════════════════════════════════════════")
    print(DONE_HINT)
    print()


def print_section(label: str, content: str) -> None:
    if label == "Agent":
        print_agent_response(content)
        return
    first, _, rest = content.partition("\n")
    print(f"[{label}] {first}")
    if rest:
        print(rest)
    print()


def print_model_chosen(requested: str, chosen: ResolvedModel) -> None:
    """Tell the user an available model was selected instead of the requested one."""
    print(f"[Model] '{requested}' is not available.")
    print(f"Using: {chosen.format_display()}")
    print()


def get_credentials(target_dir: Path) -> tuple[str, str]:
    """Get DataRobot credentials from target_dir/.env or environment variables."""
    endpoint, api_token = get_datarobot_credentials(target_dir)

    if not api_token:
        print(
            "Error: DATAROBOT_API_TOKEN not found in .env file or environment variables",
            file=sys.stderr,
        )
        sys.exit(1)

    if not endpoint:
        endpoint = "https://app.datarobot.com/api/v2"

    return api_token, endpoint


def _model_slug(model: str) -> str:
    """Normalized trailing segment for fuzzy gateway catalog matching."""
    slug = normalize_gateway_model(model).split("/")[-1].lower()
    return slug.replace(".", "-").replace("_", "-")


# Anchored to the start of a line so a commented-out key does not match, and
# tolerant of the fence the spec is usually written inside. The trailing comment
# is optional but has to be allowed for: the schema template ships the field with
# one, so filling the id in place keeps it.
SPEC_DEPLOYMENT_ID_RE = re.compile(
    r"^\s*llm_deployment_id\s*:\s*[\"']?([A-Za-z0-9_-]+)[\"']?\s*(?:#.*)?$",
    re.MULTILINE,
)


def _spec_deployment_id(spec_text: str) -> str:
    """Read `llm_deployment_id` straight out of the spec file.

    Deliberately not taken from the model's extraction. It is an opaque id, the
    kind of value a tool call is most likely to drop or garble, and the schema
    cannot make it mandatory without inviting a fabricated id on a gateway spec.
    Either way the rehearsal would silently run against a deployment the user did
    not choose. Reading the literal keeps it exact, and a spec that omits it falls
    through to the announced-substitution path.
    """
    match = SPEC_DEPLOYMENT_ID_RE.search(spec_text)
    if not match:
        return ""

    # Require the id shape rather than trusting whatever followed the colon. An
    # unquoted YAML scalar like `null`, `true` or `no` is otherwise read as an id,
    # and cmd_init prefers the id over `model`, so a gateway spec would resolve to
    # a deployment. Anything unrecognized falls through to `model`.
    value = match.group(1)

    return value if is_deployment_id(value) else ""


@dataclass(frozen=True)
class ResolvedModel:
    source: str
    id: str
    api_model: str
    deployment_id: str
    display: str

    def to_config(self) -> dict[str, str]:
        return {
            "source": self.source,
            "id": self.id,
            "api_model": self.api_model,
            "deployment_id": self.deployment_id,
            "display": self.display,
        }

    @classmethod
    def from_config(
        cls,
        data: dict[str, Any] | str,
        catalog: ModelCatalog | LazyModelCatalog | None = None,
    ) -> ResolvedModel:
        if isinstance(data, str):
            if catalog is not None:
                resolved, _ = catalog.pick_available(data)
                return resolved
            api_model = (
                DEPLOYED_LLM_MODEL
                if data == DEPLOYED_LLM_MODEL
                else normalize_gateway_model(data)
            )
            return cls(
                source=SOURCE_GATEWAY,
                id=data,
                api_model=api_model,
                deployment_id="",
                display=data,
            )
        return cls(
            source=str(data["source"]),
            id=str(data["id"]),
            api_model=str(data["api_model"]),
            deployment_id=str(data.get("deployment_id") or ""),
            display=str(data.get("display") or data["id"]),
        )

    def format_display(self) -> str:
        if self.source == SOURCE_DEPLOYED:
            return f"{self.display} (deployed: {self.id})"
        return f"{self.display} (gateway)"


def _entry_to_resolved(entry: LLMModel) -> ResolvedModel:
    return ResolvedModel(
        source=entry["source"],
        id=entry["id"],
        api_model=entry["api_model"],
        deployment_id=entry["deployment_id"],
        display=entry["name"],
    )


class ModelCatalog:
    """Gateway and deployed LLMs; picks a substitute when the requested ID is missing."""

    def __init__(self, token: str, endpoint: str) -> None:
        self._entries = fetch_llm_models(endpoint, token)
        self._gateway = [m for m in self._entries if m["source"] == SOURCE_GATEWAY]
        self._deployed = [m for m in self._entries if m["source"] == SOURCE_DEPLOYED]
        self._by_id = {m["id"]: m for m in self._entries}
        self._by_name_lower: dict[str, LLMModel] = {}
        self._by_api_model_lower: dict[str, LLMModel] = {}
        # A key that two entries share stops identifying either one. Deployment
        # labels are user-authored and can repeat, so collapse those keys instead of
        # letting the last entry indexed win and be reported as an exact match.
        ambiguous_names: dict[str, set[str]] = {}
        for entry in self._entries:
            name_key = entry["name"].lower()
            claimed = self._by_name_lower.get(name_key)
            if claimed is not None and claimed["id"] != entry["id"]:
                ambiguous_names.setdefault(name_key, {claimed["source"]}).add(
                    entry["source"]
                )
            else:
                self._by_name_lower[name_key] = entry
            # Every deployed entry shares one api_model placeholder, so it names the
            # source rather than a deployment and can never be an exact match. A
            # deployment is addressed by its id (see _by_id) or announced as a
            # substitution, never silently guessed.
            if entry["source"] != SOURCE_DEPLOYED:
                self._by_api_model_lower[entry["api_model"].lower()] = entry
            self._by_id[entry["id"]] = entry
        for name_key in ambiguous_names:
            del self._by_name_lower[name_key]
        # A collapsed key still says which pool it came from when every entry that
        # claimed it shared one source. Without this the fallback drops to the
        # whole-catalog pool, which is gateway-first, so an ambiguity purely among
        # deployments would substitute a gateway model.
        self._ambiguous_name_source: dict[str, str | None] = {
            key: next(iter(sources)) if len(sources) == 1 else None
            for key, sources in ambiguous_names.items()
        }

    def _find_exact(self, requested: str) -> LLMModel | None:
        if requested in self._by_id:
            return self._by_id[requested]
        lowered = requested.lower()
        if lowered in self._by_name_lower:
            return self._by_name_lower[lowered]
        normalized = normalize_gateway_model(requested)
        if normalized.lower() in self._by_api_model_lower:
            return self._by_api_model_lower[normalized.lower()]
        if lowered in self._by_api_model_lower:
            return self._by_api_model_lower[lowered]
        return None

    def _gateway_slug_matches(self, requested: str) -> list[LLMModel]:
        # Strip the routing prefix before reading a provider off the front. A spec
        # carries the `datarobot/`-prefixed form, so without this every request
        # looks like provider "datarobot", matching no entry, and the cross-provider
        # guard below silently stops applying.
        requested = normalize_gateway_model(requested.strip())
        req_slug = _model_slug(requested)
        if not req_slug:
            return []
        requested_prefix = (
            requested.split("/", 1)[0].lower() if "/" in requested else None
        )
        matches: list[LLMModel] = []
        for entry in self._gateway:
            if req_slug != _model_slug(entry["api_model"]):
                continue
            if requested_prefix:
                api_prefix = entry["api_model"].split("/", 1)[0].lower()
                if api_prefix != requested_prefix:
                    continue
            matches.append(entry)
        return matches

    def _fallback(
        self,
        *,
        prefer_source: str | None,
        exclude_id: str | None,
    ) -> ResolvedModel:
        pools: list[list[LLMModel]] = []
        if prefer_source == SOURCE_GATEWAY:
            pools = [self._gateway, self._deployed]
        elif prefer_source == SOURCE_DEPLOYED:
            pools = [self._deployed, self._gateway]
        else:
            pools = [self._entries]

        for pool in pools:
            for entry in pool:
                if exclude_id and entry["id"] == exclude_id:
                    continue
                return _entry_to_resolved(entry)

        if self._entries:
            return _entry_to_resolved(self._entries[0])
        raise RuntimeError("No LLM models available")

    def pick_available(
        self,
        requested: str,
        *,
        prefer_source: str | None = None,
        exclude_id: str | None = None,
    ) -> tuple[ResolvedModel, bool]:
        """Return (resolved model, was_substituted)."""
        requested = requested.strip()
        if not requested:
            return self._fallback(
                prefer_source=prefer_source, exclude_id=exclude_id
            ), True

        exact = self._find_exact(requested)
        if exact and (exclude_id is None or exact["id"] != exclude_id):
            return _entry_to_resolved(exact), False

        slug_matches = self._gateway_slug_matches(requested)
        if slug_matches:
            for entry in slug_matches:
                if exclude_id and entry["id"] == exclude_id:
                    continue
                return _entry_to_resolved(entry), True

        inferred_source = prefer_source
        if inferred_source is None and exact is not None:
            inferred_source = exact["source"]
        if inferred_source is None:
            inferred_source = self._ambiguous_name_source.get(requested.lower())
        if inferred_source is None and is_deployed_llm_model(requested):
            # The spec named the deployed-LLM placeholder without an
            # llm_deployment_id to pin it, so substitute a deployment over a gateway
            # model. Reported as a substitution, since which deployment is a guess.
            inferred_source = SOURCE_DEPLOYED

        return (
            self._fallback(
                prefer_source=inferred_source,
                exclude_id=exclude_id,
            ),
            True,
        )


class LazyModelCatalog:
    """Defers catalog API fetch until pick_available is first called."""

    def __init__(self, token: str, endpoint: str) -> None:
        self._token = token
        self._endpoint = endpoint
        self._catalog: ModelCatalog | None = None

    def pick_available(
        self,
        requested: str,
        *,
        prefer_source: str | None = None,
        exclude_id: str | None = None,
    ) -> tuple[ResolvedModel, bool]:
        if self._catalog is None:
            self._catalog = ModelCatalog(self._token, self._endpoint)
        return self._catalog.pick_available(
            requested,
            prefer_source=prefer_source,
            exclude_id=exclude_id,
        )


def strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    end = -1 if lines[-1].startswith("```") else len(lines)
    return "\n".join(lines[1:end])


@contextlib.contextmanager
def capture_output(session_dir: str) -> Iterator[str]:
    """Redirect stdout to a new temp file inside session_dir; yield the file path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, dir=session_dir
    ) as out:
        path = out.name
        sys.stdout = out
        try:
            yield path
        finally:
            sys.stdout.flush()
            sys.stdout = sys.__stdout__


# ── turn progress tracking ────────────────────────────────────────────────────


class TurnProgress:
    """Tracks per-turn LLM stats and emits progress lines to stderr."""

    def __init__(self) -> None:
        self.n_agent = 0
        self.n_sims = 0
        self.agent_elapsed = 0.0
        self.agent_in_tok = 0
        self.agent_out_tok = 0

    def agent_done(self, elapsed: float, in_tok: int, out_tok: int) -> None:
        self.n_agent += 1
        self.agent_elapsed += elapsed
        self.agent_in_tok += in_tok
        self.agent_out_tok += out_tok
        progress(f"agent responded  {elapsed:.1f}s  {in_tok}→{out_tok} tok")

    def tool_dispatched(self, fn: str, arg_keys: list[str]) -> None:
        progress(f"tool: {fn}({', '.join(arg_keys)})")

    def sim_done(self, fn: str, elapsed: float) -> None:
        self.n_sims += 1
        progress(f"simulated {fn}  {elapsed:.1f}s")

    def summary(self, wall_elapsed: float) -> None:
        tok = (
            f"  {self.agent_in_tok}→{self.agent_out_tok} tok"
            if (self.agent_in_tok or self.agent_out_tok)
            else ""
        )
        sims = f"  {self.n_sims} simulations" if self.n_sims else ""
        progress(
            f"total  wall {wall_elapsed:.1f}s  {self.n_agent} LLM calls{tok}{sims}"
        )


# ── LLM interface ─────────────────────────────────────────────────────────────

# Parameters unsupported by specific models (matched by substring)
_UNSUPPORTED_PARAMS: dict[str, set[str]] = {
    "claude-opus-4": {"temperature"},
}


def _model_params(resolved: ResolvedModel, **kwargs: Any) -> dict[str, Any]:
    """Return kwargs filtered to params supported by the given model."""
    if resolved.source == SOURCE_DEPLOYED:
        return dict(kwargs)
    unsupported: set[str] = set()
    for pattern, fields in _UNSUPPORTED_PARAMS.items():
        if pattern in resolved.api_model:
            unsupported |= fields
    dropped = unsupported & set(kwargs)
    if dropped:
        progress(
            f"note: dropped unsupported params {dropped} for model "
            f"'{resolved.api_model}'"
        )
    return {k: v for k, v in kwargs.items() if k not in unsupported}


def _chat_url(endpoint: str, resolved: ResolvedModel) -> str:
    base = endpoint.rstrip("/")
    if resolved.source == SOURCE_DEPLOYED:
        return f"{base}/deployments/{resolved.deployment_id}/chat/completions"
    return f"{base}/genai/llmgw/chat/completions"


TYPE_MAP = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}

# Tool definition used to extract structured fields from the spec file
EXTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_spec",
        "description": "Extract structured fields from an agent spec file",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "system_prompt": {"type": "string"},
                "tools": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "function_name": {"type": "string"},
                            "inputs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "arg_name": {"type": "string"},
                                        "type": {"type": "string"},
                                        "object_schema": {"type": "string"},
                                    },
                                    "required": ["arg_name", "type"],
                                },
                            },
                            "out": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "arg_name": {"type": "string"},
                                        "type": {"type": "string"},
                                        "object_schema": {"type": "string"},
                                    },
                                    "required": ["arg_name", "type"],
                                },
                            },
                            "auth_spec": {
                                "type": "object",
                                "properties": {
                                    "service_name": {"type": "string"},
                                    "auth_method": {"type": "string"},
                                },
                            },
                        },
                        "required": ["function_name", "inputs", "out"],
                    },
                },
                "examples": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["model", "system_prompt", "tools", "examples"],
        },
    },
}


def _parse_model_not_found(body: str, status: int) -> bool:
    if status != 404:
        return False
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return "not found" in body.lower()
    msg = str(data.get("detail") or data.get("details") or data.get("message") or "")
    combined = f"{msg} {body}".lower()
    return "not found" in combined


def llm_call(
    token: str,
    endpoint: str,
    resolved: ResolvedModel,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] = "auto",
    *,
    catalog: ModelCatalog | LazyModelCatalog | None = None,
    _allow_retry: bool = True,
) -> tuple[dict[str, Any], ResolvedModel]:
    url = _chat_url(endpoint, resolved)
    payload: dict[str, Any] = {
        "model": resolved.api_model,
        "messages": messages,
        **_model_params(resolved, temperature=0.0),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return cast(dict[str, Any], json.loads(resp.read())), resolved
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code in {401, 403}:
            print(f"API error {e.code}: {body}", file=sys.stderr)
            sys.exit(1)
        if _parse_model_not_found(body, e.code) and catalog and _allow_retry:
            chosen, substituted = catalog.pick_available(
                resolved.id,
                prefer_source=resolved.source,
                exclude_id=resolved.id,
            )
            if substituted:
                print_model_chosen(resolved.id, chosen)
            return llm_call(
                token,
                endpoint,
                chosen,
                messages,
                tools,
                tool_choice,
                catalog=catalog,
                _allow_retry=False,
            )
        print(f"API error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)


def build_tool_definitions(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    defs = []
    for tool in tools:
        props = {}
        required = []
        for inp in tool.get("inputs", []):
            name = inp["arg_name"]
            prop = {"type": TYPE_MAP.get(inp["type"], "string")}
            if "object_schema" in inp:
                prop["description"] = inp["object_schema"]
            props[name] = prop
            required.append(name)

        out_parts = [
            f"{o['arg_name']} ({TYPE_MAP.get(o['type'], o['type'])})"
            for o in tool.get("out", [])
        ]
        desc = "Returns: " + ", ".join(out_parts) if out_parts else ""
        auth = tool.get("auth_spec")
        if auth:
            desc += f" | Requires {auth['service_name']} {auth['auth_method']}"

        defs.append(
            {
                "type": "function",
                "function": {
                    "name": tool["function_name"],
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": props,
                        "required": required,
                    },
                },
            }
        )
    return defs


def simulate_tool_return(
    token: str,
    endpoint: str,
    simulation_model: ResolvedModel,
    tool_name: str,
    arguments: dict[str, Any],
    spec_tools: list[dict[str, Any]],
    catalog: ModelCatalog | LazyModelCatalog | None = None,
) -> tuple[dict[str, Any], ResolvedModel]:
    spec_tool = next((t for t in spec_tools if t["function_name"] == tool_name), None)
    if spec_tool:
        out_schema = ", ".join(
            f"{o['arg_name']} ({TYPE_MAP.get(o['type'], o['type'])})"
            + (f": {o['object_schema']}" if "object_schema" in o else "")
            for o in spec_tool.get("out", [])
        )
    else:
        out_schema = "result (string)"

    resp, simulation_model = llm_call(
        token,
        endpoint,
        simulation_model,
        [
            {
                "role": "system",
                "content": (
                    "Generate a realistic return value for the following tool call. "
                    "Return ONLY valid JSON — no explanation, no markdown, no code fences. "
                    "The JSON must contain exactly the output fields listed."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Tool: {tool_name}\nArguments: {json.dumps(arguments)}\n"
                    f"Output fields: {out_schema}"
                ),
            },
        ],
        catalog=catalog,
    )

    content = strip_code_fence(resp["choices"][0]["message"]["content"].strip())
    try:
        return cast(dict[str, Any], json.loads(content)), simulation_model
    except json.JSONDecodeError:
        return {"result": content}, simulation_model


# ── session management ────────────────────────────────────────────────────────


def load_session(session_dir: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    config_file = os.path.join(session_dir, "config.json")
    state_file = os.path.join(session_dir, "messages.json")
    if not os.path.exists(config_file) or not os.path.exists(state_file):
        print(
            f"Error: session not found at {session_dir}. Run with --init first.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(config_file) as f:
        config = json.load(f)
    with open(state_file) as f:
        messages = json.load(f)
    return config, messages, state_file


def _resolved_models_differ(a: ResolvedModel, b: ResolvedModel) -> bool:
    return a.to_config() != b.to_config()


# ── commands ──────────────────────────────────────────────────────────────────


def cmd_init(spec_path: str, session_dir: str, target_dir: Path) -> None:
    if not os.path.exists(spec_path):
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    token, endpoint = get_credentials(target_dir)
    catalog = ModelCatalog(token, endpoint)
    simulation_model, sim_substituted = catalog.pick_available(
        SIMULATION_MODEL,
        prefer_source=SOURCE_GATEWAY,
    )
    if sim_substituted and simulation_model.source == SOURCE_DEPLOYED:
        progress(
            "note: no gateway model matched simulation default; "
            f"using deployed model {simulation_model.id}"
        )
    if sim_substituted:
        print_model_chosen(SIMULATION_MODEL, simulation_model)

    with open(spec_path) as f:
        content = f.read()

    progress("extracting spec...")
    t0 = time.monotonic()
    resp, simulation_model = llm_call(
        token,
        endpoint,
        simulation_model,
        messages=[
            {
                "role": "system",
                "content": "Extract the structured fields from the agent spec provided by the user.",
            },
            {"role": "user", "content": content},
        ],
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "function", "function": {"name": "extract_spec"}},
        catalog=catalog,
    )
    elapsed = time.monotonic() - t0
    usage = resp.get("usage", {})
    progress(
        f"extract spec  {elapsed:.1f}s  {usage.get('prompt_tokens', '?')}→{usage.get('completion_tokens', '?')} tok"
    )

    tool_calls = resp["choices"][0]["message"].get("tool_calls")
    if not tool_calls:
        print(
            "Error: spec extraction failed — model did not return structured data",
            file=sys.stderr,
        )
        sys.exit(1)
    spec = json.loads(tool_calls[0]["function"]["arguments"])
    requested_model = str(spec["model"]).strip()
    # A deployed LLM is identified by its deployment id, not by `model`: every
    # deployment shares one placeholder there. Resolving on the id keeps the
    # rehearsal on the deployment the spec actually chose. Read from the spec text
    # rather than the extraction, see _spec_deployment_id.
    requested_deployment_id = _spec_deployment_id(content)
    if requested_deployment_id:
        agent_model, model_substituted = catalog.pick_available(
            requested_deployment_id, prefer_source=SOURCE_DEPLOYED
        )
    else:
        agent_model, model_substituted = catalog.pick_available(requested_model)
    if model_substituted:
        print_model_chosen(requested_deployment_id or requested_model, agent_model)
    system_prompt = spec["system_prompt"]
    tools = spec.get("tools", [])
    examples = spec.get("examples", [])

    with open(os.path.join(session_dir, "config.json"), "w") as f:
        json.dump(
            {
                "model": agent_model.to_config(),
                "simulation_model": simulation_model.to_config(),
                "system_prompt": system_prompt,
                "tool_definitions": build_tool_definitions(tools),
                "spec_tools": tools,
                "examples": examples,
                "target_dir": str(target_dir.resolve()),
            },
            f,
        )

    with open(os.path.join(session_dir, "messages.json"), "w") as f:
        json.dump([{"role": "system", "content": system_prompt}], f)

    tool_sigs = [
        f"  - {t['function_name']}"
        f"({', '.join(i['arg_name'] + ': ' + i['type'] for i in t.get('inputs', []))})"
        f" → {', '.join(o['arg_name'] + ': ' + o['type'] for o in t.get('out', []))}"
        for t in tools
    ]
    prompt_preview = system_prompt[:200] + ("…" if len(system_prompt) > 200 else "")

    body = [
        f"Model: {agent_model.format_display()}",
        f"System prompt: {prompt_preview}",
        "",
        f"Tools ({len(tools)}):",
        *(tool_sigs if tool_sigs else ["  (none)"]),
        "",
        "Examples:",
        *([f"  - {e}" for e in examples] if examples else ["  (none)"]),
    ]
    print_init_banner(body)


def run_tool_call(
    tc: dict[str, Any],
    token: str,
    endpoint: str,
    simulation_model: ResolvedModel,
    spec_tools: list[dict[str, Any]],
    catalog: ModelCatalog | LazyModelCatalog | None,
    stats: TurnProgress,
    lock: threading.Lock,
) -> tuple[dict[str, Any], ResolvedModel]:
    """Execute one tool call cycle: dispatch → simulate → return tool message."""
    fn = tc["function"]["name"]
    try:
        args = json.loads(tc["function"]["arguments"])
    except json.JSONDecodeError as e:
        print(f"Error: malformed arguments for tool {fn}: {e}", file=sys.stderr)
        sys.exit(1)

    with lock:
        stats.tool_dispatched(fn, list(args.keys()))
        print_section("TOOL CALL", f"{fn}\n{json.dumps(args, indent=2)}")

    t0 = time.monotonic()
    simulated, simulation_model = simulate_tool_return(
        token, endpoint, simulation_model, fn, args, spec_tools, catalog
    )
    elapsed = time.monotonic() - t0

    with lock:
        stats.sim_done(fn, elapsed)
        print_section("SIMULATED RETURN", f"{fn}\n{json.dumps(simulated, indent=2)}")

    return (
        {"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(simulated)},
        simulation_model,
    )


def _save_config(session_dir: str, config: dict[str, Any]) -> None:
    path = os.path.join(session_dir, "config.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(config, f)
    os.replace(tmp, path)


def cmd_turn(session_dir: str, message: str, target_dir: Path | None = None) -> None:
    config, messages, state_file = load_session(session_dir)
    resolved_target_dir = target_dir or Path(config.get("target_dir", "."))
    token, endpoint = get_credentials(resolved_target_dir)

    catalog = LazyModelCatalog(token, endpoint)

    agent_model = ResolvedModel.from_config(config["model"], catalog)
    simulation_model = ResolvedModel.from_config(
        config.get("simulation_model", SIMULATION_MODEL),
        catalog,
    )
    if isinstance(config.get("model"), str) or isinstance(
        config.get("simulation_model"), str
    ):
        config["model"] = agent_model.to_config()
        config["simulation_model"] = simulation_model.to_config()
        _save_config(session_dir, config)
    tool_defs = config["tool_definitions"]
    spec_tools = config["spec_tools"]

    print_turn_header()
    print(f"[You]: {message}")
    print()
    messages.append({"role": "user", "content": message})

    stats = TurnProgress()
    t_wall = time.monotonic()

    max_tool_rounds = 20
    for _round in range(max_tool_rounds):
        t0 = time.monotonic()
        resp, agent_model = llm_call(
            token,
            endpoint,
            agent_model,
            messages,
            tool_defs or None,
            catalog=catalog,
        )
        saved_agent = ResolvedModel.from_config(config["model"], catalog)
        if _resolved_models_differ(agent_model, saved_agent):
            config["model"] = agent_model.to_config()
            _save_config(session_dir, config)
        elapsed = time.monotonic() - t0
        usage = resp.get("usage", {})
        stats.agent_done(
            elapsed, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        )

        msg = resp["choices"][0]["message"]
        finish_reason = resp["choices"][0]["finish_reason"]

        if finish_reason == "tool_calls" or msg.get("tool_calls"):
            messages.append(msg)
            run_tool = functools.partial(
                run_tool_call,
                token=token,
                endpoint=endpoint,
                simulation_model=simulation_model,
                spec_tools=spec_tools,
                catalog=catalog,
                stats=stats,
                lock=threading.Lock(),
            )
            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = list(executor.map(run_tool, msg["tool_calls"]))
            tool_messages = [r[0] for r in results]
            simulation_model = results[-1][1]
            saved_simulation = ResolvedModel.from_config(
                config.get("simulation_model", SIMULATION_MODEL),
                catalog,
            )
            if _resolved_models_differ(simulation_model, saved_simulation):
                config["simulation_model"] = simulation_model.to_config()
                _save_config(session_dir, config)
            messages.extend(tool_messages)
        else:
            content = msg.get("content", "")
            messages.append({"role": "assistant", "content": content})
            print_section("Agent", content)
            break
    else:
        progress(
            f"Warning: reached maximum tool-call rounds ({max_tool_rounds}) without a final response. "
            "The agent may be stuck in a tool-call loop."
        )
        print_turn_footer()

    stats.summary(time.monotonic() - t_wall)

    tmp = state_file + ".tmp"
    with open(tmp, "w") as f:
        json.dump(messages, f)
    os.replace(tmp, state_file)


# ── entry point ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="DataRobot Dress Rehearsal")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--spec", default="agent_spec.md")
    parser.add_argument(
        "--target-dir",
        default=None,
        help="Project directory for .env lookup (required for --init; turns default to session from --init)",
    )
    parser.add_argument("--session", metavar="DIR")
    parser.add_argument("message", nargs="?")
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve() if args.target_dir else None

    if args.init:
        if not target_dir:
            print(
                "Error: --target-dir is required for --init",
                file=sys.stderr,
            )
            return 1
        if not target_dir.is_dir():
            print(
                f"Error: target directory does not exist: {target_dir}",
                file=sys.stderr,
            )
            return 1
        session_dir = tempfile.mkdtemp(prefix="dr_rehearsal_")
        with capture_output(session_dir) as output_path:
            cmd_init(args.spec, session_dir, target_dir)
        print(f"session={session_dir}")
        print(f"output={output_path}")

    elif args.message:
        if not args.session:
            print("Error: --session DIR is required", file=sys.stderr)
            return 1
        with capture_output(args.session) as output_path:
            cmd_turn(args.session, args.message, target_dir)
        print(f"output={output_path}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
