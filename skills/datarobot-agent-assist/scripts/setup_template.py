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
import secrets
import subprocess
import sys
from pathlib import Path

from env_utils import read_env_variable

# A DataRobot-deployed LLM is selected by deployment id, not by model name: the
# template routes to the deployment and swaps in the deployed-LLM Pulumi config
# instead of the default gateway one. See the template's
# infra/configurations/llm/deployed_llm.py.
DEPLOYED_MODEL_SENTINEL = "datarobot/datarobot-deployed-llm"
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


def create_env_file(
    target_dir: Path, llm_default_model: str, llm_deployment_id: str = ""
) -> tuple[bool, str]:
    """
    Create .env file with the LLM configuration.

    A deployment id switches the template from the default LLM Gateway routing to
    an existing DataRobot text-generation deployment, which needs three extra keys
    beyond the model name.

    Args:
        target_dir: Directory where .env file should be created
        llm_default_model: Value for LLM_DEFAULT_MODEL
        llm_deployment_id: Deployment id of a DataRobot-deployed LLM, if selected

    Returns:
        Tuple of (success, message)
    """
    env_file = target_dir / ".env"

    lines = [
        "DATAROBOT_ENDPOINT=\n",
        "DATAROBOT_API_TOKEN=\n",
        f'LLM_DEFAULT_MODEL="{llm_default_model}"\n',
    ]

    if llm_deployment_id:
        lines.extend(
            [
                f"LLM_DEPLOYMENT_ID={llm_deployment_id}\n",
                f"INFRA_ENABLE_LLM={DEPLOYED_LLM_CONFIGURATION}\n",
                # Without this the app would still route through the gateway and
                # ignore the deployment.
                "USE_DATAROBOT_LLM_GATEWAY=0\n",
            ]
        )

    try:
        print(f"Creating .env file in {target_dir}")

        with open(env_file, "w") as f:
            f.writelines(lines)

        print(f'✓ Created .env file with LLM_DEFAULT_MODEL="{llm_default_model}"')

        if llm_deployment_id:
            print(
                f"✓ Configured DataRobot-deployed LLM {llm_deployment_id} "
                f"(INFRA_ENABLE_LLM={DEPLOYED_LLM_CONFIGURATION}, "
                "USE_DATAROBOT_LLM_GATEWAY=0)"
            )

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

        # The template's deployed-LLM config verifies LLM_DEFAULT_MODEL against the
        # deployment, so a gateway model name here fails later at 'pulumi up'.
        if llm_default_model != DEPLOYED_MODEL_SENTINEL:
            print(
                f"⚠ Warning: --llm-deployment-id is set but --llm-model is "
                f'"{llm_default_model}", not "{DEPLOYED_MODEL_SENTINEL}". '
                "Deployment routing may fail."
            )

    print()

    # Ensure target directory exists
    if not target_dir.exists():
        print(f"Error: Target directory does not exist: {target_dir}")
        return 1

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
        help="Deployment id of a DataRobot-deployed LLM (omit for LLM Gateway models). "
        f'Pair with --llm-model "{DEPLOYED_MODEL_SENTINEL}".',
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

    return setup_and_run(args.llm_model, target_dir, args.llm_deployment_id)


if __name__ == "__main__":
    sys.exit(main())
