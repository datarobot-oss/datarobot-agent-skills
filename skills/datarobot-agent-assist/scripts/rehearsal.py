#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
DataRobot Dress Rehearsal engine (datarobot-agent-assist skill)

Init:  python3 rehearsal.py --init [--spec agent_spec.md]
         stdout: session=<session_dir>  output=<output_file>
Turn:  python3 rehearsal.py --session <session_dir> "user message"
         stdout: output=<output_file>

From repository root, use:
  python3 skills/datarobot-agent-assist/rehearsal.py ...
"""

import argparse
import concurrent.futures
import contextlib
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from env_utils import ensure_env_file, read_env_variable
from list_llm_models import fetch_llm_models


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


def print_model_chosen(requested: str, chosen: str) -> None:
    """Tell the user an available model was selected instead of the requested one."""
    print(f"[Model] '{requested}' is not available in your LLM Gateway catalog.")
    print(f"Using: {chosen}")
    print()


def get_credentials() -> tuple[str, str]:
    """Get DataRobot credentials from .env file or environment variables.

    If .env file doesn't exist, attempts to run 'dr dotenv setup'.
    Falls back to environment variables if .env is not available.

    Returns:
        tuple: (api_token, endpoint)
    """
    env_file = Path(".env")

    # Ensure .env file exists (run dr dotenv setup if needed)
    ensure_env_file(env_file)

    endpoint = None
    api_token = None

    # Try .env file first
    if env_file.exists():
        try:
            endpoint = read_env_variable(env_file, "DATAROBOT_ENDPOINT")
        except ValueError:
            pass  # Variable not in .env, will try environment

        try:
            api_token = read_env_variable(env_file, "DATAROBOT_API_TOKEN")
        except ValueError:
            pass  # Variable not in .env, will try environment

    # Fall back to environment variables if not found in .env
    if not endpoint:
        endpoint = os.environ.get(
            "DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2"
        )

    if not api_token:
        api_token = os.environ.get("DATAROBOT_API_TOKEN")

    if not api_token:
        print(
            "Error: DATAROBOT_API_TOKEN not found in .env file or environment variables",
            file=sys.stderr,
        )
        sys.exit(1)

    return (api_token, endpoint)


def strip_model_prefix(model: str) -> str:
    while model.startswith("datarobot/"):
        model = model[len("datarobot/") :]
    return model


def _model_slug(model: str) -> str:
    """Normalized trailing segment for fuzzy catalog matching."""
    slug = strip_model_prefix(model).split("/")[-1].lower()
    return slug.replace(".", "-").replace("_", "-")


class ModelCatalog:
    """Active LLM Gateway models; picks a substitute when the requested ID is missing."""

    def __init__(self, token: str, endpoint: str) -> None:
        models = fetch_llm_models(endpoint, token)
        self._names = [strip_model_prefix(m["name"]) for m in models]
        self._by_lower = {name.lower(): name for name in self._names}

    def pick_available(self, requested: str) -> tuple[str, bool]:
        """Return (catalog model ID, was_substituted)."""
        requested = strip_model_prefix(requested)
        if requested in self._names:
            return requested, False

        canonical = self._by_lower.get(requested.lower())
        if canonical:
            return canonical, False

        req_slug = _model_slug(requested)
        if not req_slug:
            pass
        else:
            requested_prefix = (
                requested.split("/", 1)[0].lower() if "/" in requested else None
            )
            slug_matches: list[str] = []
            for name in self._names:
                if req_slug == _model_slug(name):
                    slug_matches.append(name)
            if slug_matches:
                if requested_prefix:
                    for name in slug_matches:
                        if name.split("/", 1)[0].lower() == requested_prefix:
                            return name, True
                return slug_matches[0], True

        return self._names[0], True


class LazyModelCatalog:
    """Defers catalog API fetch until pick_available is first called."""

    def __init__(self, token: str, endpoint: str) -> None:
        self._token = token
        self._endpoint = endpoint
        self._catalog: ModelCatalog | None = None

    def pick_available(self, requested: str) -> tuple[str, bool]:
        if self._catalog is None:
            self._catalog = ModelCatalog(self._token, self._endpoint)
        return self._catalog.pick_available(requested)


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


def _model_params(model: str, **kwargs: Any) -> dict[str, Any]:
    """Return kwargs filtered to params supported by the given model."""
    unsupported: set[str] = set()
    for pattern, fields in _UNSUPPORTED_PARAMS.items():
        if pattern in model:
            unsupported |= fields
    dropped = unsupported & set(kwargs)
    if dropped:
        progress(f"note: dropped unsupported params {dropped} for model '{model}'")
    return {k: v for k, v in kwargs.items() if k not in unsupported}


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
        return False
    msg = str(data.get("detail") or data.get("details") or data.get("message") or "")
    return "not found" in msg.lower() and "catalog" in msg.lower()


def llm_call(
    token: str,
    endpoint: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] = "auto",
    *,
    catalog: ModelCatalog | LazyModelCatalog | None = None,
    _allow_retry: bool = True,
) -> tuple[dict[str, Any], str]:
    url = f"{endpoint.rstrip('/')}/genai/llmgw/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        **_model_params(model, temperature=0.0),
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
            return cast(dict[str, Any], json.loads(resp.read())), model
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if _parse_model_not_found(body, e.code) and catalog and _allow_retry:
            chosen, substituted = catalog.pick_available(model)
            if substituted:
                print_model_chosen(model, chosen)
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
    simulation_model: str,
    tool_name: str,
    arguments: dict[str, Any],
    spec_tools: list[dict[str, Any]],
    catalog: ModelCatalog | LazyModelCatalog | None = None,
) -> tuple[dict[str, Any], str]:
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
                "content": f"Tool: {tool_name}\nArguments: {json.dumps(arguments)}\nOutput fields: {out_schema}",
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


# ── commands ──────────────────────────────────────────────────────────────────


def cmd_init(spec_path: str, session_dir: str) -> None:
    if not os.path.exists(spec_path):
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    token, endpoint = get_credentials()
    catalog = ModelCatalog(token, endpoint)
    simulation_model, sim_substituted = catalog.pick_available(SIMULATION_MODEL)
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
    requested_model = strip_model_prefix(spec["model"])
    model, model_substituted = catalog.pick_available(requested_model)
    if model_substituted:
        print_model_chosen(requested_model, model)
    system_prompt = spec["system_prompt"]
    tools = spec.get("tools", [])
    examples = spec.get("examples", [])

    with open(os.path.join(session_dir, "config.json"), "w") as f:
        json.dump(
            {
                "model": model,
                "simulation_model": simulation_model,
                "system_prompt": system_prompt,
                "tool_definitions": build_tool_definitions(tools),
                "spec_tools": tools,
                "examples": examples,
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
        f"Model: {model}",
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
    simulation_model: str,
    spec_tools: list[dict[str, Any]],
    catalog: ModelCatalog | LazyModelCatalog | None,
    stats: TurnProgress,
    lock: threading.Lock,
) -> tuple[dict[str, Any], str]:
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


def cmd_turn(session_dir: str, message: str) -> None:
    token, endpoint = get_credentials()
    catalog = LazyModelCatalog(token, endpoint)
    config, messages, state_file = load_session(session_dir)

    model = config["model"]
    simulation_model = config.get("simulation_model", SIMULATION_MODEL)
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
        resp, model = llm_call(
            token, endpoint, model, messages, tool_defs or None, catalog=catalog
        )
        if model != config["model"]:
            config["model"] = model
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
            lock = threading.Lock()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = list(
                    executor.map(
                        lambda tc: run_tool_call(
                            tc,
                            token,
                            endpoint,
                            simulation_model,
                            spec_tools,
                            catalog,
                            stats,
                            lock,
                        ),
                        msg["tool_calls"],
                    )
                )
            tool_messages = [r[0] for r in results]
            simulation_model = results[-1][1]
            if simulation_model != config.get("simulation_model"):
                config["simulation_model"] = simulation_model
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
    parser.add_argument("--session", metavar="DIR")
    parser.add_argument("message", nargs="?")
    args = parser.parse_args()

    if args.init:
        session_dir = tempfile.mkdtemp(prefix="dr_rehearsal_")
        with capture_output(session_dir) as output_path:
            cmd_init(args.spec, session_dir)
        print(f"session={session_dir}")
        print(f"output={output_path}")

    elif args.message:
        if not args.session:
            print("Error: --session DIR is required", file=sys.stderr)
            return 1
        with capture_output(args.session) as output_path:
            cmd_turn(args.session, args.message)
        print(f"output={output_path}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
