#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""List available LLM models from DataRobot LLM Gateway.

This script fetches and displays active models from the DataRobot LLM Gateway catalog
by delegating to the DataRobot CLI (`dr llm-gateway list`), so the skill and the CLI
always agree on what "available" means.

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

# Kind discriminator on each CLI entry. Only gateway catalog models are returned
# here; a `dr` predating the deployed-LLM support omits the field entirely, so a
# missing value is read as "gateway".
SOURCE_GATEWAY = "gateway"


class LLMModel(TypedDict):
    name: str
    description: str
    provider: str
    context_size: int


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


def _to_llm_model(entry: dict[str, Any]) -> LLMModel:
    """Map one CLI entry onto the LLMModel shape used across the skill."""
    model_name = entry.get("model") or ""
    # Downstream consumers (agent_spec.md, LLM_DEFAULT_MODEL) expect the
    # datarobot/ prefix; the CLI reports the bare gateway model id.
    if model_name and not model_name.startswith("datarobot/"):
        model_name = f"datarobot/{model_name}"

    return {
        "name": model_name,
        "description": entry.get("description") or "",
        "provider": entry.get("provider") or "Unknown",
        "context_size": entry.get("context_size") or 0,
    }


def fetch_llm_models(endpoint: str, api_token: str) -> list[LLMModel]:
    """Fetch active LLM Gateway models via the DataRobot CLI.

    Args:
        endpoint: DataRobot API endpoint URL
        api_token: DataRobot API token for authentication

    Returns:
        List of active LLMModel dictionaries with name, description, provider, and context_size

    Raises:
        RuntimeError: If the CLI call fails or the catalog has no active models
    """
    entries = fetch_cli_llms(endpoint, api_token)

    gateway = [
        _to_llm_model(e)
        for e in entries
        if e.get("source", SOURCE_GATEWAY) == SOURCE_GATEWAY
    ]

    if not gateway:
        raise RuntimeError("No active models found in catalog")

    return gateway


def format_as_table(models: list[LLMModel]) -> str:
    """Format models as a readable table.

    Args:
        models: List of model dictionaries

    Returns:
        Formatted table string
    """
    if not models:
        return "No models available"

    # Calculate column widths
    models_name_width = max(len(m["name"]) for m in models)
    name_width = max(models_name_width, len("Model Name"))
    models_provider_width = max(len(m["provider"]) for m in models)
    provider_width = max(models_provider_width, len("Provider"))
    models_context_width = max(len(str(m["context_size"])) for m in models)
    context_width = max(models_context_width, len("Context Size"))

    # Build table
    lines = []
    header = f"{'Model Name':<{name_width}} | {'Provider':<{provider_width}} | {'Context Size':>{context_width}} | Description"
    separator = "-" * len(header)
    lines.append(header)
    lines.append(separator)

    for m in models:
        name = m["name"]
        provider = m["provider"]
        context = str(m["context_size"])
        description = (
            m["description"][:80] + "..."
            if len(m["description"]) > 80
            else m["description"]
        )
        lines.append(
            f"{name:<{name_width}} | {provider:<{provider_width}} | {context:>{context_width}} | {description}"
        )

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="List available LLM models from DataRobot LLM Gateway"
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
        models = fetch_llm_models(endpoint, api_token)

        if args.json:
            # JSON output
            print(json.dumps(models, indent=2))
        else:
            # Table output (default)
            print(f"\nFound {len(models)} active LLM models:\n")
            print(format_as_table(models))
            print()

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
