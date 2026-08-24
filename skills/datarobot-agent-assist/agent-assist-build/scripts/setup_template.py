#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Setup and initialize a DataRobot agent application template.

This script performs initial setup for a DataRobot agent application template by:
1. Running: 'dr dotenv setup --yes' to generate a .env file with the specified LLM model and secrets
   Note: 'dr dotenv setup --yes' is supposed to run in non-interactive mode and generate the .env file with the required variables
2. Initializing a Pulumi stack with the generated passphrase
3. Running the template's start-non-interactive task

Usage:
    python setup_template.py --llm-model <model-name> [--llm-deployment-id <id>]
                             [--target-dir <directory>]

The script generates cryptographically secure random secrets for session
management and Pulumi configuration encryption.
"""

import argparse
import base64
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

from urllib.error import HTTPError

from env_utils import read_env_variable
from list_llm_models import (
    LLMModel,
    _fetch_gateway_models_rest,
    ensure_datarobot_prefix,
    is_deployed_llm_model,
    is_deployment_id,
    normalize_gateway_model,
)

# A DataRobot-deployed LLM is selected by deployment id, not by model name: the
# template swaps in this Pulumi config and calls the deployment's chat endpoint
# directly. See the template's infra/configurations/llm/deployed_llm.py and
# docs/llm.md ("DataRobot Deployed LLM").
DEPLOYED_LLM_CONFIGURATION = "deployed_llm.py"


def generate_random_secret(length: int = 32) -> str:
    """
    Generate a cryptographically random base64-encoded secret.

    Args:
        length: Desired length of the final secret string

    Returns:
        A base64 URL-safe encoded string truncated to specified length
    """
    random_bytes = secrets.token_bytes(length)
    encoded = base64.urlsafe_b64encode(random_bytes).decode("ascii")
    return encoded[:length]


def _env_value(env_file: Path, name: str) -> str | None:
    if not env_file.exists():
        return None
    try:
        return read_env_variable(env_file, name)
    except ValueError:
        return None


def read_credentials(target_dir: Path) -> tuple[str | None, str | None]:
    """Read DataRobot credentials without creating or rewriting anything.

    env_utils.get_datarobot_credentials runs 'dr dotenv setup' when .env is absent.
    That is the wrong side effect here: this runs before create_env_file truncates
    .env, and setup_and_run makes the real setup call a step later regardless.
    """
    env_file = target_dir / ".env"
    endpoint = _env_value(env_file, "DATAROBOT_ENDPOINT") or os.environ.get(
        "DATAROBOT_ENDPOINT"
    )
    api_token = _env_value(env_file, "DATAROBOT_API_TOKEN") or os.environ.get(
        "DATAROBOT_API_TOKEN"
    )
    return endpoint, api_token


_LLM_ID_ERROR = (
    'Error: --llm-model "{value}" is an LLM Gateway model id, not a model name. '
    "The gateway rejects it and the app fails during deployment. Use the "
    "llm_default_model field from list_llm_models.py instead."
)

_NO_GATEWAY_ERROR = (
    'Error: --llm-model "{value}" cannot be used. This instance has no LLM Gateway '
    "catalog, so pick a DataRobot-deployed LLM and pass its --llm-deployment-id "
    "instead."
)

# The value is interpolated into a double-quoted .env line that the template's
# loader re-parses, so a quote, backslash or '$' would end the line early and turn
# the rest into further keys. Every model name in the live catalog is covered by
# this set; ':' and '@' are load-bearing (bedrock/...-v1:0, vertex_ai/...@20250929).
MODEL_VALUE_RE = re.compile(r"[A-Za-z0-9._:@/-]+")


def read_gateway_catalog(target_dir: Path) -> list[LLMModel] | None:
    """The instance's gateway catalog, or None when it could not be read.

    Goes straight to REST rather than through fetch_llm_models, which prefers the
    `dr` CLI. The CLI honors passed credentials only once they verify and otherwise
    falls back to its own stored profile, so it can answer about a different
    instance than the project points at. Tolerable for a listing someone reads,
    wrong for a gate that decides accept or abort.

    An empty list and None mean different things: the instance answered and has no
    gateway models, versus nothing could be learned about it.
    """
    endpoint, api_token = read_credentials(target_dir)
    if not endpoint or not api_token:
        print("Note: no DataRobot credentials found, so the model was not verified.")
        return None
    try:
        return _fetch_gateway_models_rest(endpoint, api_token)
    except (RuntimeError, OSError) as e:
        # OSError as well as RuntimeError: urlopen lets raw ConnectionResetError and
        # RemoteDisconnected past the URLError handling in the fetch helper, and an
        # unreachable instance must not take the whole setup down with it.
        cause = e.__cause__
        if isinstance(cause, HTTPError) and cause.code == 404:
            # The instance answered and said the catalog is not there. That is a
            # disabled gateway, not a failure to reach it, so it gets the same
            # answer as an empty catalog rather than an unverified pass. 403 is
            # excluded on purpose: it means this token may not read the catalog,
            # which says nothing about whether the gateway exists.
            return []
        print(f"Note: could not verify the model against the catalog ({e}).")
        return None


def canonical_gateway_model(value: str, target_dir: Path) -> str | None:
    """Resolve a gateway model choice to the value LLM_DEFAULT_MODEL takes.

    Returns None when the value cannot be a gateway model, having printed why.

    The catalog decides. Where it cannot be read, fall back to shape: a catalog
    model is a ``provider/model`` path, so a value with no slash is a catalog llmId,
    which the gateway answers 404 for. That heuristic never overrules the catalog,
    which is free to carry a model whose name has no slash in it.
    """
    bare = normalize_gateway_model(value.strip())
    catalog = read_gateway_catalog(target_dir)

    if catalog is None:
        if "/" not in bare:
            print(_LLM_ID_ERROR.format(value=value), file=sys.stderr)
            return None
        return ensure_datarobot_prefix(bare)

    for model in catalog:
        if model["api_model"].lower() == bare.lower():
            return model["llm_default_model"]

    if not catalog:
        # No gateway entry at all means the LLM Gateway is disabled or empty, the
        # normal shape of an on-prem install. Listing the empty catalog back would
        # say nothing; the way forward is a deployed LLM instead.
        print(_NO_GATEWAY_ERROR.format(value=value), file=sys.stderr)
        return None

    if "/" not in bare:
        print(_LLM_ID_ERROR.format(value=value), file=sys.stderr)
        return None

    available = "\n  ".join(sorted(m["llm_default_model"] for m in catalog))
    print(
        f'Error: --llm-model "{value}" is not in this instance\'s LLM Gateway '
        f"catalog.\nAvailable:\n  {available}",
        file=sys.stderr,
    )
    return None


def create_env_file(
    target_dir: Path, llm_default_model: str, llm_deployment_id: str = ""
) -> tuple[bool, str]:
    """
    Create .env file with the LLM configuration.

    A deployment id switches the template off its default LLM Gateway routing and
    onto an existing DataRobot text-generation deployment, which takes two extra
    keys beyond the model name.

    Args:
        target_dir: Directory where .env file should be created
        llm_default_model: Value for LLM_DEFAULT_MODEL
        llm_deployment_id: Deployment id of a DataRobot-deployed LLM, if selected

    Returns:
        Tuple of (success, message)
    """
    env_file = target_dir / ".env"

    # Guard here rather than in canonical_gateway_model: this is where the value is
    # interpolated, and it is the one point every path goes through, including the
    # deployed one where the model is only a label.
    if not MODEL_VALUE_RE.fullmatch(llm_default_model):
        error_msg = (
            f'--llm-model "{llm_default_model}" has characters that cannot go in a '
            ".env value. Expected letters, digits, and any of . _ : @ / -"
        )
        print(f"Error: {error_msg}", file=sys.stderr)
        return False, error_msg

    lines = [
        "DATAROBOT_ENDPOINT=\n",
        "DATAROBOT_API_TOKEN=\n",
        f'LLM_DEFAULT_MODEL="{llm_default_model}"\n',
    ]

    if llm_deployment_id:
        lines.extend(
            [
                f'LLM_DEPLOYMENT_ID="{llm_deployment_id}"\n',
                f'INFRA_ENABLE_LLM="{DEPLOYED_LLM_CONFIGURATION}"\n',
                # 'dr dotenv setup' also derives this from INFRA_ENABLE_LLM, but it
                # runs after this file is written and may be skipped entirely, so
                # the deployed .env has to stand on its own.
                'USE_DATAROBOT_LLM_GATEWAY="0"\n',
            ]
        )

    try:
        print(f"Creating .env file in {target_dir}")

        # Write the .env file
        with open(env_file, "w") as f:
            f.writelines(lines)

        if llm_deployment_id:
            print(
                f"✓ Created .env file routed to DataRobot-deployed LLM "
                f"{llm_deployment_id} (INFRA_ENABLE_LLM={DEPLOYED_LLM_CONFIGURATION}, "
                "USE_DATAROBOT_LLM_GATEWAY=0)"
            )
        else:
            print(f'✓ Created .env file with LLM_DEFAULT_MODEL="{llm_default_model}"')

        return True, f"Created {env_file}"

    except OSError as e:
        error_msg = f"Failed to create .env file: {e!s}"
        print(f"Error: {error_msg}")
        return False, error_msg


def initialize_pulumi(
    target_dir: Path, pulumi_passphrase: str = "", timeout: int = 300
) -> tuple[bool, str]:
    """
    Initialize Pulumi stack with a passphrase from .env or generated.

    Args:
        target_dir: Directory where Pulumi command should be executed
        pulumi_passphrase: Optional passphrase for Pulumi config encryption

    Returns:
        Tuple of (success, output)
    """
    # Check if infra subdirectory exists
    infra_dir = target_dir / "infra"
    work_dir = infra_dir if infra_dir.exists() else target_dir

    # Try to read PULUMI_CONFIG_PASSPHRASE from .env file, fall back to provided or generated passphrase
    env_file = target_dir / ".env"
    passphrase = pulumi_passphrase

    if env_file.exists():
        try:
            passphrase = read_env_variable(env_file, "PULUMI_CONFIG_PASSPHRASE")
            print("Using PULUMI_CONFIG_PASSPHRASE from .env file")
        except ValueError:
            # Variable not in .env, use the provided passphrase or generate one
            if not passphrase:
                passphrase = generate_random_secret()
            print(
                "PULUMI_CONFIG_PASSPHRASE not found in .env, using generated passphrase"
            )

    # Generate random string for stack name
    random_suffix = generate_random_secret(8)
    stack_name = f"dev-agent-assist-{random_suffix}"
    command = f"pulumi stack init {stack_name}"

    print(f"\nInitializing Pulumi stack in {work_dir}:")
    print(f"  Stack name: {stack_name}")
    print()

    env = os.environ.copy()
    env["DATAROBOT_CLI_NON_INTERACTIVE"] = "True"
    env["PULUMI_CONFIG_PASSPHRASE"] = passphrase

    try:
        result = subprocess.run(
            command,
            cwd=work_dir,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )

        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        # Print the output
        print("Command output:")
        print("-" * 80)
        print(output)
        print("-" * 80)

        if result.returncode != 0:
            print(f"\n⚠ Command exited with code {result.returncode}")
            return False, output

        print("\n✓ Pulumi stack initialized successfully")
        return True, output

    except subprocess.TimeoutExpired:
        error_msg = f"Pulumi initialization timed out after {timeout} seconds"
        print(f"Error: {error_msg}")
        return False, error_msg
    except OSError as e:
        error_msg = f"Failed to initialize Pulumi: {e!s}"
        print(f"Error: {error_msg}")
        return False, error_msg


def run_command(command: str, target_dir: Path, timeout: int = 300) -> tuple[bool, str]:
    """
    Run a shell command and capture its output.

    Args:
        command: Shell command to execute
        target_dir: Directory where command should be executed
        timeout: Timeout in seconds (default: 300)

    Returns:
        Tuple of (success, output)
    """
    print(f"\nExecuting command in {target_dir}:")
    print(f"  {command}")
    print()

    env = os.environ.copy()
    env["DATAROBOT_CLI_NON_INTERACTIVE"] = "True"

    try:
        result = subprocess.run(
            command,
            cwd=target_dir,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )

        # Combine stdout and stderr
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        # Print the output
        print("Command output:")
        print("-" * 80)
        print(output)
        print("-" * 80)

        if result.returncode != 0:
            print(f"\n⚠ Command exited with code {result.returncode}")
            return False, output

        print("\n✓ Command completed successfully")
        return True, output

    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout} seconds"
        print(f"Error: {error_msg}")
        return False, error_msg
    except OSError as e:
        error_msg = f"Failed to execute command: {e!s}"
        print(f"Error: {error_msg}")
        return False, error_msg


def setup_and_run(
    llm_default_model: str, target_dir: Path, llm_deployment_id: str = ""
) -> int:
    """
    Create .env file and run required setup commands.

    Args:
        llm_default_model: Value for LLM_DEFAULT_MODEL in .env file
        target_dir: Target directory for operations
        llm_deployment_id: Deployment id of a DataRobot-deployed LLM, if selected

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("=" * 80)
    print("Setup and Run Script")
    print("=" * 80)
    print(f"Target directory: {target_dir}")
    print(f"LLM model: {llm_default_model}")

    if llm_deployment_id:
        print(f"LLM deployment: {llm_deployment_id}")

        # The id is written verbatim into a double-quoted .env line that the template's
        # loader re-parses, so a quote, backslash or '$' corrupts it as surely as
        # whitespace does.
        if not re.fullmatch(r"[A-Za-z0-9_-]+", llm_deployment_id):
            print(
                f'Error: --llm-deployment-id "{llm_deployment_id}" is not a plain '
                "identifier. Pass just the deployment id.",
                file=sys.stderr,
            )
            return 1

        # Separate from the check above: this one is about being the wrong value
        # rather than an unwritable one. A spec that wrote `llm_deployment_id: null`
        # yields the literal "null", which would otherwise route the template to a
        # deployment that does not exist and fail at 'pulumi up'.
        if not is_deployment_id(llm_deployment_id):
            print(
                f'Error: --llm-deployment-id "{llm_deployment_id}" is not a DataRobot '
                "deployment id, which is 24 hex characters. Take it from the "
                "deployment_id field of the model listing.",
                file=sys.stderr,
            )
            return 1

        if not is_deployed_llm_model(llm_default_model):
            # Allowed, not an error: the deployment routes by id and treats the model
            # string as a label the endpoint ignores. Do not promise the label
            # survives, though. 'dr dotenv setup' rebuilds .env from
            # .datarobot/cli/llm.yml, whose deployed_llm group has no
            # LLM_DEFAULT_MODEL, so it drops the key and the template falls back to
            # its own placeholder.
            print(
                f'Note: the deployment routes by id, so "{llm_default_model}" acts '
                "only as a label and is not persisted by 'dr dotenv setup'."
            )
    elif is_deployed_llm_model(llm_default_model):
        # The likelier slip, since agent_spec.md always carries `model` while
        # `llm_deployment_id` is the extra field that is easy to drop. Nothing
        # downstream catches it: without the id the template stays on its gateway
        # config, whose verify_llm checks the model against the gateway catalog and
        # dies much later at 'pulumi up' with "Model 'datarobot-deployed-llm' not
        # found in catalog", which points nowhere near the missing id.
        print(
            f'Error: --llm-model "{llm_default_model}" is the DataRobot-deployed-LLM '
            "placeholder, which only resolves with a deployment. Pass "
            "--llm-deployment-id from the spec's llm_deployment_id field, or pick an "
            "LLM Gateway model instead.",
            file=sys.stderr,
        )
        return 1

    print()

    # Ensure target directory exists
    if not target_dir.exists():
        print(f"Error: Target directory does not exist: {target_dir}")
        return 1

    # Canonicalize before anything writes .env: create_env_file truncates the file,
    # taking with it the credentials the catalog check reads. The deployed path is
    # exempt, since there the model is only a label and 'dr dotenv setup' drops it.
    if not llm_deployment_id:
        canonical = canonical_gateway_model(llm_default_model, target_dir)
        if canonical is None:
            return 1
        llm_default_model = canonical

    # Step 1: Create .env file
    success, _ = create_env_file(target_dir, llm_default_model, llm_deployment_id)
    if not success:
        return 1

    # Step 2: Run dr dotenv setup
    success, _ = run_command("dr dotenv setup --yes --output .", target_dir)
    if not success:
        # TODO: DR CLI non-interactive mode MUST be supported for this to work
        print("\n⚠ Command 'dr dotenv setup --yes' failed")
        print("See output above for details")
        return 1

    # Step 3: Initialize Pulumi stack
    success, _ = initialize_pulumi(target_dir)
    if not success:
        print("\n⚠ Pulumi initialization failed")
        print("See output above for details")
        return 1

    # Step 4: Run task start-non-interactive
    success, _ = run_command("task start-non-interactive", target_dir)
    if not success:
        print("\n⚠ Command 'task start-non-interactive' failed")
        print("See output above for details")
        return 1

    print("\n" + "=" * 80)
    print("✓ All operations successful!")
    print("=" * 80)

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create .env file and run setup commands"
    )

    parser.add_argument(
        "--llm-model", required=True, help="LLM model to set in .env file"
    )

    parser.add_argument(
        "--llm-deployment-id",
        default="",
        help="Deployment id of a DataRobot-deployed LLM, from the spec's "
        "llm_deployment_id field (omit for LLM Gateway models)",
    )

    parser.add_argument(
        "--target-dir",
        required=True,
        help="Target directory for operations (required — use the session <target_dir>)",
    )

    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    if not target_dir.is_dir():
        print(f"Error: target directory does not exist: {target_dir}", file=sys.stderr)
        return 1

    return setup_and_run(args.llm_model, target_dir, args.llm_deployment_id.strip())


if __name__ == "__main__":
    sys.exit(main())
