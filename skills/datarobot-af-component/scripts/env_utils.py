#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for working with .env files."""

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


def ensure_env_file(env_file: Path = Path(".env")) -> None:
    """
    Ensure .env file exists, creating it via 'dr dotenv setup' if needed.

    If .env file doesn't exist, attempts to run 'dr dotenv setup --yes --output .'
    to create it. Prints warnings to stderr if setup fails but does not raise an error.

    Args:
        env_file: Path to the .env file (default: .env in current directory)
    """
    if not env_file.exists():
        try:
            print("No .env file found. Running 'dr dotenv setup --yes --output .'...")
            result = subprocess.run(
                ["dr", "dotenv", "setup", "--yes", "--output", "."],
                check=True,
                capture_output=True,
                text=True,
            )
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(
                f"Warning: Failed to run 'dr dotenv setup': {e.stderr}", file=sys.stderr
            )
            print("Falling back to environment variables...", file=sys.stderr)
        except FileNotFoundError:
            print(
                "Warning: 'dr' command not found. Falling back to environment variables...",
                file=sys.stderr,
            )
