#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Utility functions for working with .env files."""

import os
import subprocess
import sys
from pathlib import Path


class CredentialError(ValueError):
    """Raised when DataRobot credentials cannot be resolved."""


def read_env_variable(env_file: Path, variable_name: str) -> str:
    """Read a variable from a dotenv file without printing it."""
    if not env_file.exists():
        raise FileNotFoundError(f".env file not found: {env_file}")

    with env_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != variable_name:
                continue
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value

    raise ValueError(f"Variable '{variable_name}' not found in {env_file}")


def ensure_env_file(env_file: Path = Path(".env")) -> None:
    """Create a dotenv file through dr-cli when one does not exist."""
    if env_file.exists():
        return
    try:
        subprocess.run(
            ["dr", "dotenv", "setup", "--yes", "--output", str(env_file.parent)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(
            f"Warning: could not create {env_file} with dr-cli; "
            f"falling back to environment variables ({exc})",
            file=sys.stderr,
        )


def load_datarobot_credentials(env_file: Path = Path(".env")) -> tuple[str, str]:
    """Resolve endpoint and token from dotenv, then environment variables."""
    ensure_env_file(env_file)
    endpoint = ""
    api_token = ""
    if env_file.exists():
        try:
            endpoint = read_env_variable(env_file, "DATAROBOT_ENDPOINT").strip()
        except ValueError:
            pass
        try:
            api_token = read_env_variable(env_file, "DATAROBOT_API_TOKEN").strip()
        except ValueError:
            pass

    endpoint = endpoint or os.environ.get("DATAROBOT_ENDPOINT", "").strip()
    api_token = api_token or os.environ.get("DATAROBOT_API_TOKEN", "").strip()

    missing = []
    if not endpoint:
        missing.append("endpoint")
    if not api_token:
        missing.append("API token")
    if missing:
        raise CredentialError(
            f"DataRobot {', '.join(missing)} not configured; run datarobot-setup"
        )
    return endpoint, api_token
