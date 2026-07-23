#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check DataRobot Codespace prerequisites for Agent Assist.

Mirrors the `dr assist` CLI init check (dr-agent-cli
``datarobot_assist/initialize/codespace.py``) so the skill gives the same
guidance when run inside a DataRobot Codespace:

1. The working directory must be a subdirectory of ``/home/notebooks/storage/``
   (hard stop -> exit 1).
2. The ports required for local agent testing must be exposed (warning only,
   exit 0).

Outside a DataRobot Codespace this is a silent no-op (exit 0).

Usage:
    python check_codespace.py [--json]

Environment Variables:
    DATAROBOT_NOTEBOOK_IMAGE_VERSION: set inside a Codespace (used for detection)
    NOTEBOOK_ID: the current Codespace id
    DATAROBOT_ENDPOINT: DataRobot API endpoint URL
    DATAROBOT_API_TOKEN: DataRobot API authentication token
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional, TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from env_utils import read_env_variable

# Must be a *subdirectory* of this path. The trailing slash is deliberate: the
# storage root itself (``/home/notebooks/storage``) does not match and is rejected.
CODESPACE_STORAGE_PATH = "/home/notebooks/storage/"

# Ports required for local agent testing. Kept in sync with the dr-agent-cli
# counterpart (datarobot_assist/initialize/codespace.py REQUIRED_PORTS); there is
# no shared module across the two repos.
REQUIRED_PORTS: dict[int, str] = {
    5173: "Frontend (Vite)",
    8080: "Web (FastAPI)",
    8842: "Agent Workflow",
}

PORTS_API_PATH = "/api-gw/nbx/executionEnvironments/{codespace_id}/ports/"


class ExposedPort(TypedDict):
    id: str
    notebookId: str
    port: int
    description: str
    url: str


def is_codespace() -> bool:
    """Return True when running inside a DataRobot Codespace."""
    return bool(os.getenv("DATAROBOT_NOTEBOOK_IMAGE_VERSION"))


def get_codespace_id() -> str:
    """Return the current DataRobot Codespace id (empty string if unset)."""
    return os.getenv("NOTEBOOK_ID", "")


def check_working_directory() -> bool:
    """Return True if the cwd is a subdirectory of the Codespace storage path."""
    return os.getcwd().startswith(CODESPACE_STORAGE_PATH)


def load_credentials() -> tuple[Optional[str], Optional[str]]:
    """Load the DataRobot endpoint and token, preferring the environment.

    Inside a Codespace both values are exported into the environment, so those
    are read first. This avoids triggering ``dr dotenv setup`` (used by the
    other skill scripts), which would be premature at pre-requisite time. An
    existing ``.env`` in the cwd is consulted only as a fallback.

    Returns:
        A ``(endpoint, api_token)`` tuple; either element may be None.
    """
    endpoint = os.getenv("DATAROBOT_ENDPOINT")
    api_token = os.getenv("DATAROBOT_API_TOKEN")

    env_file = Path(".env")
    if (not endpoint or not api_token) and env_file.exists():
        if not endpoint:
            try:
                endpoint = read_env_variable(env_file, "DATAROBOT_ENDPOINT")
            except ValueError:
                pass
        if not api_token:
            try:
                api_token = read_env_variable(env_file, "DATAROBOT_API_TOKEN")
            except ValueError:
                pass

    return endpoint, api_token


def fetch_exposed_ports(
    endpoint: str, api_token: str, codespace_id: str
) -> list[ExposedPort]:
    """Fetch the exposed ports for the current Codespace.

    The ports API lives at the gateway host root (``/api-gw/...``), so only the
    scheme and host of ``endpoint`` are used; any ``/api/v2`` path is dropped.

    Args:
        endpoint: DataRobot API endpoint URL.
        api_token: DataRobot API token for authentication.
        codespace_id: The current Codespace id.

    Returns:
        The list of exposed-port entries for this Codespace.

    Raises:
        RuntimeError: If the request fails or the response cannot be parsed.
    """
    parsed = urlparse(endpoint)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    url = base_url + PORTS_API_PATH.format(codespace_id=codespace_id)

    try:
        request = Request(url, headers={"Authorization": f"Bearer {api_token}"})
        with urlopen(request, timeout=10) as response:  # noqa: S310 - trusted endpoint
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as e:
        raise RuntimeError(f"Failed to fetch exposed ports: {e}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse ports response: {e}") from e

    entries = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise RuntimeError(f"Unexpected ports response format: {type(entries)}")
    ports: list[ExposedPort] = entries
    return ports


def _working_dir_message() -> str:
    """Return the hard-stop message for an invalid Codespace working directory."""
    return (
        "Invalid working directory\n\n"
        "Running Agent Assist from ~/storage or another system directory in a "
        "Codespace is not supported.\n"
        "Create a subdirectory and run Agent Assist from there:\n\n"
        "  cd ~/storage\n"
        "  mkdir my-agent\n"
        "  cd my-agent"
    )


def _missing_ports_message(missing: dict[int, str]) -> str:
    """Return the warning message listing ports that need to be exposed."""
    port_lines = "\n".join(f"  {port} - {name}" for port, name in missing.items())
    return (
        "Expose required ports\n\n"
        "Agent Assist is running in a DataRobot Codespace. The following ports "
        "must be exposed for local development and testing:\n\n"
        f"{port_lines}\n\n"
        "To expose the ports:\n"
        "  - Note the port numbers above\n"
        "  - Stop the Codespace\n"
        '  - Open the "Session environment" section\n'
        '  - Add each port number under "Exposed ports"\n'
        "  - Start the Codespace\n\n"
        "Proceeding without exposing the ports is possible, but functionality "
        "may be limited."
    )


def main() -> int:
    """Run the Codespace checks. See module docstring for exit-code semantics."""
    parser = argparse.ArgumentParser(
        description="Check DataRobot Codespace prerequisites for Agent Assist"
    )
    parser.add_argument("--json", action="store_true", help="Output the result as JSON")
    args = parser.parse_args()

    codespace_id = get_codespace_id()

    # Outside a Codespace there is nothing to check.
    if not is_codespace():
        if args.json:
            print(json.dumps({"in_codespace": False}, indent=2))
        return 0

    # 1. Working-directory hard stop.
    if not check_working_directory():
        if args.json:
            print(json.dumps({"in_codespace": True, "working_dir_ok": False}, indent=2))
        else:
            print(_working_dir_message(), file=sys.stderr)
        return 1

    # 2. Exposed-ports warning (non-blocking, fail-open).
    endpoint, api_token = load_credentials()
    exposed: list[ExposedPort] = []
    missing: dict[int, str] = dict(REQUIRED_PORTS)
    if endpoint and api_token and codespace_id:
        try:
            exposed = fetch_exposed_ports(endpoint, api_token, codespace_id)
            exposed_nums = {entry["port"] for entry in exposed}
            missing = {
                port: name
                for port, name in REQUIRED_PORTS.items()
                if port not in exposed_nums
            }
        except (RuntimeError, KeyError, TypeError):
            # Fail open: if exposed ports cannot be determined, warn about all.
            missing = dict(REQUIRED_PORTS)

    if args.json:
        result: dict[str, object] = {
            "in_codespace": True,
            "working_dir_ok": True,
            "codespace_id": codespace_id,
            "required_ports": REQUIRED_PORTS,
            "exposed_ports": exposed,
            "missing_ports": missing,
        }
        print(json.dumps(result, indent=2))
    elif missing:
        print(_missing_ports_message(missing))

    return 0


if __name__ == "__main__":
    sys.exit(main())
