#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""List available LLM models from DataRobot LLM Gateway.

This script fetches and displays active models from the DataRobot LLM Gateway catalog.
Designed to be used by AI agents to discover available LLM models.

Usage:
    python list_llm_models.py [--json|--table]

Environment Variables:
    DATAROBOT_ENDPOINT: DataRobot API endpoint URL
    DATAROBOT_API_TOKEN: DataRobot API authentication token
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from env_utils import ensure_env_file, read_env_variable


class LLMModel(TypedDict):
    name: str
    description: str
    provider: str
    context_size: int


def fetch_llm_models(endpoint: str, api_token: str) -> list[LLMModel]:
    """Fetch active LLM models from DataRobot Gateway.

    Args:
        endpoint: DataRobot API endpoint URL
        api_token: DataRobot API token for authentication

    Returns:
        List of active LLMModel dictionaries with name, description, provider, and context_size

    Raises:
        RuntimeError: If the API request fails
    """
    endpoint = endpoint.rstrip("/")
    url = f"{endpoint}/genai/llmgw/catalog/"

    try:
        request = Request(
            url,
            headers={"Authorization": f"Bearer {api_token}"},
        )
        with urlopen(request, timeout=30) as response:  # noqa: S310 - trusted DataRobot endpoint
            data = json.loads(response.read().decode("utf-8"))

        # Handle both list and dict responses
        if isinstance(data, dict) and "data" in data:
            models_list = data["data"]
        elif isinstance(data, list):
            models_list = data
        else:
            raise RuntimeError(f"Unexpected response format: {type(data)}")

        # Client-side filtering for active models
        active_models = [m for m in models_list if m.get("isActive", False)]

        if not active_models:
            raise RuntimeError("No active models found in catalog")

        # Extract key information
        result: list[LLMModel] = []
        for m in active_models:
            model_name = m.get("model", "")
            # Ensure model name has datarobot/ prefix
            if model_name and not model_name.startswith("datarobot/"):
                model_name = f"datarobot/{model_name}"

            result.append(
                {
                    "name": model_name,
                    "description": m.get("description", ""),
                    "provider": m.get("provider", "Unknown"),
                    "context_size": m.get("contextSize", 0),
                }
            )

        return result

    except (HTTPError, URLError) as e:
        raise RuntimeError(f"Failed to fetch model catalog: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse model catalog response: {e}") from e


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
    args = parser.parse_args()

    # Try to get credentials from .env file first, then fall back to environment
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
        endpoint = os.getenv("DATAROBOT_ENDPOINT")

    if not api_token:
        api_token = os.getenv("DATAROBOT_API_TOKEN")

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
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
