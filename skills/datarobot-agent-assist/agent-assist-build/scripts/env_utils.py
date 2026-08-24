#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for working with .env files."""

import os
import subprocess
import sys
from pathlib import Path


def read_env_variable(env_file: Path, variable_name: str) -> str:
    """
    Read a variable value from a .env file.

    Args:
        env_file: Path to the .env file
        variable_name: Name of the variable to read

    Returns:
        The variable value (stripped of quotes if present)

    Raises:
        FileNotFoundError: If the .env file doesn't exist
        ValueError: If the variable is not found in the file
    """
    if not env_file.exists():
        raise FileNotFoundError(f".env file not found: {env_file}")

    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Split on first = sign
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                if key == variable_name:
                    # Remove surrounding quotes if present
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]
                    return value

    raise ValueError(f"Variable '{variable_name}' not found in {env_file}")


def ensure_env_file(env_file: Path) -> None:
    """
    Ensure .env file exists, creating it via 'dr dotenv setup' if needed.

    If .env file doesn't exist, runs 'dr dotenv setup --yes' in the parent
    directory of env_file. Prints warnings to stderr if setup fails but does not
    raise an error.

    Args:
        env_file: Path to the .env file (e.g. target_dir / ".env")
    """
    env_file = env_file.resolve()
    if env_file.exists():
        return

    target_dir = env_file.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # stderr, not stdout: callers such as list_llm_models.py --json use stdout as a
        # data channel, and a progress line there makes the JSON unparseable.
        print(
            f"No .env file found. Running 'dr dotenv setup --yes' in {target_dir}...",
            file=sys.stderr,
        )
        result = subprocess.run(
            ["dr", "dotenv", "setup", "--yes", "--output", "."],
            cwd=target_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        print(result.stdout, file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to run 'dr dotenv setup': {e.stderr}", file=sys.stderr)
        print("Falling back to environment variables...", file=sys.stderr)
    except FileNotFoundError:
        print(
            "Warning: 'dr' command not found. Falling back to environment variables...",
            file=sys.stderr,
        )


def get_datarobot_credentials(target_dir: Path) -> tuple[str | None, str | None]:
    """
    Get DataRobot credentials from target_dir/.env or environment variables.

    Args:
        target_dir: Project directory containing the .env file

    Returns:
        Tuple of (endpoint, api_token); either value may be None if unset
    """
    env_file = target_dir.resolve() / ".env"
    ensure_env_file(env_file)

    endpoint = None
    api_token = None

    if env_file.exists():
        try:
            endpoint = read_env_variable(env_file, "DATAROBOT_ENDPOINT")
        except ValueError:
            pass

        try:
            api_token = read_env_variable(env_file, "DATAROBOT_API_TOKEN")
        except ValueError:
            pass

    if not endpoint:
        endpoint = os.environ.get("DATAROBOT_ENDPOINT")

    if not api_token:
        api_token = os.environ.get("DATAROBOT_API_TOKEN")

    return endpoint, api_token
