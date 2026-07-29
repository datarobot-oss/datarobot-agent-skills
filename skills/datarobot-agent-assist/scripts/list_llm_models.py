#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""List the LLMs available to a DataRobot agent.

Covers both LLM Gateway catalog models and DataRobot-deployed text-generation
models, by delegating to the DataRobot CLI (`dr llm-gateway list`) so the skill and
the CLI always agree on what "available" means. Deployed models matter on
environments where the gateway is disabled or empty, such as on-prem installs.

Usage:
    python list_llm_models.py [--json|--table] [--target-dir <directory>]

Environment Variables:
    DATAROBOT_ENDPOINT: DataRobot API endpoint URL
    DATAROBOT_API_TOKEN: DataRobot API authentication token
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, TypedDict

from env_utils import get_datarobot_credentials

# `dr llm-gateway list --output-format json` prints {"llms": [...]} on stdout.
DR_LLM_LIST_CMD = ["dr", "llm-gateway", "list", "--output-format", "json"]
DR_LLM_LIST_ENVELOPE_KEY = "llms"

# The CLI falls back to an interactive login when the credentials it is handed do
# not verify. stdin is closed so that prompt fails fast instead of blocking, and
# the timeout is the backstop for a prompt that ignores EOF.
DR_LLM_LIST_TIMEOUT = 90

# Kind discriminator on each CLI entry. A `dr` predating the deployed-LLM support
# omits the field entirely, so a missing value is read as "gateway".
SOURCE_GATEWAY = "gateway"
SOURCE_DEPLOYED = "deployed"

# Deployments have no gateway provider; label the column so the source is obvious.
DEPLOYED_PROVIDER_LABEL = "DataRobot deployment"


class LLMModel(TypedDict):
    name: str
    description: str
    provider: str
    context_size: int


class LLMChoice(TypedDict):
    """A selectable LLM, from either source.

    `name` is the value that belongs in the spec's `model` field and in
    LLM_DEFAULT_MODEL. `label` is the human-readable name to show the user, which
    for a deployed model is the only thing distinguishing it -- every deployed
    entry shares the same `name` sentinel. `deployment_id` is empty for gateway
    models and is what setup_template.py needs to write the deployed-model .env.
    """

    name: str
    label: str
    description: str
    provider: str
    context_size: int
    source: str
    deployment_id: str


def _dr_environment(endpoint: str, api_token: str) -> dict[str, str]:
    """Build the subprocess environment for a `dr` invocation.

    The CLI prefers DATAROBOT_ENDPOINT / DATAROBOT_API_TOKEN over its own stored
    profile, so passing the project's credentials through keeps the listing pointed
    at the same DataRobot instance the project's .env targets. It only honors them
    once they verify, and falls back to its stored profile otherwise -- so a stale
    project .env yields the user's own catalog rather than a hard failure.
    """
    env = os.environ.copy()
    env["DATAROBOT_ENDPOINT"] = endpoint
    env["DATAROBOT_API_TOKEN"] = api_token
    env["DATAROBOT_CLI_NON_INTERACTIVE"] = "True"

    return env


def fetch_cli_llms(endpoint: str, api_token: str) -> list[dict[str, Any]]:
    """Return the raw `dr llm-gateway list` entries, unfiltered.

    Args:
        endpoint: DataRobot API endpoint URL
        api_token: DataRobot API token for authentication

    Returns:
        List of CLI entry dicts (id, name, source, provider, model, description,
        context_size, deployment_id, selected)

    Raises:
        RuntimeError: If the CLI is missing, fails, or returns unparseable output
    """
    try:
        result = subprocess.run(
            DR_LLM_LIST_CMD,
            capture_output=True,
            text=True,
            check=False,
            timeout=DR_LLM_LIST_TIMEOUT,
            stdin=subprocess.DEVNULL,
            env=_dr_environment(endpoint, api_token),
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "DataRobot CLI ('dr') not found. Install it with "
            "'curl https://cli.datarobot.com/install | sh' and re-run."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"'{' '.join(DR_LLM_LIST_CMD)}' timed out after {DR_LLM_LIST_TIMEOUT}s. "
            "Check DATAROBOT_ENDPOINT / DATAROBOT_API_TOKEN and 'dr auth check'."
        ) from e

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"'{' '.join(DR_LLM_LIST_CMD)}' failed with exit code {result.returncode}: {detail}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse CLI model list output: {e}") from e

    entries = data.get(DR_LLM_LIST_ENVELOPE_KEY) if isinstance(data, dict) else None
    if not isinstance(entries, list):
        # RuntimeError, not TypeError: it is the single error channel this script's
        # callers and main() handle, and a malformed envelope is a CLI contract
        # failure rather than a caller bug.
        raise RuntimeError(  # noqa: TRY004
            f"Unexpected CLI output: no '{DR_LLM_LIST_ENVELOPE_KEY}' list in response"
        )

    return entries


def _model_name(entry: dict[str, Any]) -> str:
    """The spec/LLM_DEFAULT_MODEL value for one CLI entry."""
    model_name = entry.get("model") or ""
    # Downstream consumers (agent_spec.md, LLM_DEFAULT_MODEL) expect the
    # datarobot/ prefix; the CLI reports the bare gateway model id.
    if model_name and not model_name.startswith("datarobot/"):
        model_name = f"datarobot/{model_name}"

    return model_name


def _to_llm_choice(entry: dict[str, Any]) -> LLMChoice:
    """Map one CLI entry onto the selectable-LLM shape."""
    source = entry.get("source") or SOURCE_GATEWAY
    provider = entry.get("provider") or ""

    if source == SOURCE_DEPLOYED:
        provider = provider or DEPLOYED_PROVIDER_LABEL

    return {
        "name": _model_name(entry),
        "label": entry.get("name") or "",
        "description": entry.get("description") or "",
        "provider": provider or "Unknown",
        "context_size": entry.get("context_size") or 0,
        "source": source,
        "deployment_id": entry.get("deployment_id") or "",
    }


def _to_llm_model(choice: LLMChoice) -> LLMModel:
    """Narrow a selectable LLM to the gateway-model shape."""
    return {
        "name": choice["name"],
        "description": choice["description"],
        "provider": choice["provider"],
        "context_size": choice["context_size"],
    }


def fetch_llm_choices(endpoint: str, api_token: str) -> list[LLMChoice]:
    """Fetch every selectable LLM -- gateway catalog plus DataRobot deployments.

    Args:
        endpoint: DataRobot API endpoint URL
        api_token: DataRobot API token for authentication

    Returns:
        List of LLMChoice dictionaries, in the order the CLI reports them

    Raises:
        RuntimeError: If the CLI call fails or neither source has any model
    """
    choices = [_to_llm_choice(e) for e in fetch_cli_llms(endpoint, api_token)]

    if not choices:
        raise RuntimeError("No active models found in catalog")

    return choices


def fetch_llm_models(endpoint: str, api_token: str) -> list[LLMModel]:
    """Fetch active LLM Gateway models via the DataRobot CLI.

    Gateway-only: callers that speak to the gateway's chat-completions endpoint
    (the dress rehearsal) cannot address a deployed model.

    Args:
        endpoint: DataRobot API endpoint URL
        api_token: DataRobot API token for authentication

    Returns:
        List of active LLMModel dictionaries with name, description, provider, and context_size

    Raises:
        RuntimeError: If the CLI call fails or no gateway model is available
    """
    choices = fetch_llm_choices(endpoint, api_token)
    gateway = [_to_llm_model(c) for c in choices if c["source"] == SOURCE_GATEWAY]

    if not gateway:
        # Distinguish an empty gateway from an empty everything: with deployments
        # present the catalog is not empty, it just holds nothing this caller can
        # address, and saying "no models" sends the user looking in the wrong place.
        deployed = len(choices) - len(gateway)
        if deployed:
            raise RuntimeError(
                f"No LLM Gateway models available. {deployed} DataRobot-deployed "
                "model(s) exist, but they cannot be reached through the gateway's "
                "chat-completions endpoint, so the dress rehearsal cannot use them. "
                "Skip the rehearsal, or enable the LLM Gateway on this instance."
            )

        raise RuntimeError("No active models found in catalog")

    return gateway


DESCRIPTION_TRUNCATE_AT = 80


def _selector(choice: LLMChoice) -> str:
    """What the user has to quote to pick this LLM.

    For a gateway model that is the model name; for a deployed model the name is a
    shared sentinel, so the deployment id is the only usable handle.
    """
    if choice["source"] == SOURCE_DEPLOYED:
        return choice["deployment_id"]

    return choice["name"]


def format_as_table(choices: list[LLMChoice]) -> str:
    """Format selectable LLMs as a readable table.

    Args:
        choices: List of LLMChoice dictionaries

    Returns:
        Formatted table string
    """
    if not choices:
        return "No models available"

    rows = []
    for c in choices:
        description = c["description"]
        if len(description) > DESCRIPTION_TRUNCATE_AT:
            description = description[:DESCRIPTION_TRUNCATE_AT] + "..."

        rows.append(
            [
                c["label"],
                c["source"],
                _selector(c),
                c["provider"],
                # A deployment does not report a context window; "-" reads as
                # unknown where a bare 0 would read as a real token limit.
                str(c["context_size"]) if c["context_size"] > 0 else "-",
                description,
            ]
        )

    headers = ["Name", "Source", "Model / Deployment ID", "Provider", "Context", ""]
    # The trailing description column is left unpadded so it can run long.
    widths = [
        max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers[:-1])
    ]

    def render(cells: list[str]) -> str:
        padded = [f"{cells[i]:<{w}}" for i, w in enumerate(widths)]

        return " | ".join([*padded, cells[-1]]).rstrip()

    header = render([*headers[:-1], "Description"])
    lines = [header, "-" * len(header)]
    lines.extend(render(r) for r in rows)

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="List the LLMs available to a DataRobot agent "
        "(LLM Gateway catalog models and DataRobot-deployed models)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format (default: table)",
    )
    parser.add_argument(
        "--table",
        action="store_true",
        help="Output in table format (default)",
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        help="Project directory for .env lookup (required — use the session <target_dir>)",
    )
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    if not target_dir.is_dir():
        print(f"Error: target directory does not exist: {target_dir}", file=sys.stderr)
        return 1
    endpoint, api_token = get_datarobot_credentials(target_dir)

    if not endpoint and not api_token:
        print("Error: DATAROBOT_ENDPOINT environment variable not set", file=sys.stderr)
        print(
            "Error: DATAROBOT_API_TOKEN environment variable not set", file=sys.stderr
        )
        return 1

    if not endpoint:
        print("Error: DATAROBOT_ENDPOINT environment variable not set", file=sys.stderr)
        return 1

    if not api_token:
        print(
            "Error: DATAROBOT_API_TOKEN environment variable not set", file=sys.stderr
        )
        return 1

    try:
        choices = fetch_llm_choices(endpoint, api_token)

        if args.json:
            # JSON output
            print(json.dumps(choices, indent=2))
        else:
            # Table output (default)
            gateway = sum(1 for c in choices if c["source"] == SOURCE_GATEWAY)
            deployed = len(choices) - gateway
            print(
                f"\nFound {len(choices)} available LLMs "
                f"({gateway} gateway, {deployed} deployed):\n"
            )
            print(format_as_table(choices))
            print()

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
