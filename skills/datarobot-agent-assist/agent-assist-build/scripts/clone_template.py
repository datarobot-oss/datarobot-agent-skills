#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Clone the DataRobot agent application template repository.

This script clones the DataRobot agent application template from a hardcoded
GitHub repository URL and branch. It performs guardrail checks to prevent
overwriting existing repositories or configurations, then uses git init, remote
add, fetch, and checkout to clone the template into the target directory.

Usage:
    python clone_template.py [--target-dir <directory>]

The repository URL and branch/tag default to the script constants REPO_URL,
BRANCH, and TAG. AGENT_ASSIST_TEMPLATE_REPO_URL,
AGENT_ASSIST_TEMPLATE_REPO_BRANCH, and AGENT_ASSIST_TEMPLATE_REPO_TAG override
their respective defaults. A branch takes priority over a tag when both are set.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/datarobot-community/datarobot-agent-application.git"
BRANCH: str | None = None
TAG: str | None = "11.10.7"
TEMPLATE_REPO_URL_ENV = "AGENT_ASSIST_TEMPLATE_REPO_URL"
TEMPLATE_REPO_BRANCH_ENV = "AGENT_ASSIST_TEMPLATE_REPO_BRANCH"
TEMPLATE_REPO_TAG_ENV = "AGENT_ASSIST_TEMPLATE_REPO_TAG"


def _environment_override(name: str, default: str | None) -> str | None:
    """Return a non-empty environment override, or the configured default."""
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def template_repository_config() -> tuple[str, str | None, str | None]:
    """Return the effective repository URL, branch, and tag configuration."""
    return (
        _environment_override(TEMPLATE_REPO_URL_ENV, REPO_URL) or REPO_URL,
        _environment_override(TEMPLATE_REPO_BRANCH_ENV, BRANCH),
        _environment_override(TEMPLATE_REPO_TAG_ENV, TAG),
    )


def cleanup_git_dir(target_dir: Path) -> None:
    """Clean up .git directory on failure."""
    git_dir = target_dir / ".git"
    if git_dir.exists():
        print(f"Cleaning up .git directory in {target_dir}")
        import shutil

        shutil.rmtree(git_dir)


def run_git_command(
    command: list[str], description: str, target_dir: Path, timeout: int = 10
) -> tuple[bool, str]:
    """
    Run a git command and return success status and output.

    Args:
        command: Git command as list of strings
        description: Description of the operation
        target_dir: Target directory for the operation
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, output)
    """
    print(f"{description}...")
    try:
        result = subprocess.run(
            command,
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        output = result.stdout + result.stderr

        return bool(not result.returncode), output

    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout} seconds"
    except OSError as e:
        return False, str(e)


def check_guardrails(target_dir: Path) -> tuple[bool, str | None]:
    """
    Check guardrails before cloning.

    Returns:
        Tuple of (passed, error_message)
    """
    print("Running guardrail checks...")

    # Check for existing git repository
    git_dir = target_dir / ".git"
    if git_dir.exists():
        return (
            False,
            f"Git repository already initialized in {target_dir}\n\tFound: {git_dir}\n\tAborting to prevent overwriting existing repository",
        )

    # Check for AGENTS.md
    agents_file = target_dir / "AGENTS.md"
    if agents_file.exists():
        return (
            False,
            f"AGENTS.md file already exists in {target_dir}\n\tAborting to prevent overwriting existing configuration",
        )

    print("✓ Guardrail checks passed")
    return True, None


def clone_repository(repo_url: str, ref: str, ref_type: str, target_dir: Path) -> int:
    """
    Clone a git repository using init, remote add, fetch, and checkout.

    Args:
        repo_url: Git repository URL
        ref: Tag or branch name
        ref_type: Either "tag" or "branch"
        target_dir: Target directory for cloning

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print(f"Cloning repository: {repo_url}")
    print(f"Reference type: {ref_type}")
    print(f"Reference: {ref}")
    print(f"Target directory: {target_dir}")
    print()

    # Run guardrail checks
    passed, error_msg = check_guardrails(target_dir)
    if not passed:
        print(f"Error: {error_msg}")
        return 1

    print()

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Initialize git repository
    success, output = run_git_command(
        ["git", "init"],
        f"Initializing git repository in {target_dir}",
        target_dir,
        timeout=10,
    )

    if not success:
        print(f"Error: Failed to initialize git repository: {output}")
        return 1

    # Step 2: Add remote
    success, output = run_git_command(
        ["git", "remote", "add", "origin", repo_url],
        f"Adding remote origin {repo_url}",
        target_dir,
        timeout=10,
    )

    if not success:
        print(f"Error: Failed to add remote: {output}")
        cleanup_git_dir(target_dir)
        return 1

    # Step 3: Fetch from remote
    success, output = run_git_command(
        ["git", "fetch", "origin"],
        "Fetching from remote repository",
        target_dir,
        timeout=60,
    )

    if not success:
        print(f"Error: Failed to fetch from remote: {output}")
        cleanup_git_dir(target_dir)
        return 1

    # Step 4: Checkout branch or tag
    if ref_type == "tag":
        success, output = run_git_command(
            ["git", "checkout", ref], f"Checking out tag {ref}", target_dir, timeout=10
        )
    else:
        success, output = run_git_command(
            ["git", "checkout", "-t", f"origin/{ref}"],
            f"Checking out and tracking branch {ref}",
            target_dir,
            timeout=10,
        )

    if not success:
        print(f"Error: Failed to checkout {ref_type} {ref}: {output}")
        cleanup_git_dir(target_dir)
        return 1

    print()
    print("✓ Repository cloned successfully!")
    print(f"  Location: {target_dir}")
    print(f"  Checked out: {ref_type} '{ref}'")

    return 0


def main() -> int:
    """Main entry point."""
    repo_url, branch, tag = template_repository_config()

    # Determine which ref to use (branch takes priority over tag).
    if branch:
        ref_type = "branch"
        ref = branch
    elif tag:
        ref_type = "tag"
        ref = tag
    else:
        print("Error: Either TAG or BRANCH must be set in the script configuration")
        return 1

    parser = argparse.ArgumentParser(
        description=f"Clone the DataRobot agent application template from {repo_url}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Repository: {repo_url}
Tag: {tag if tag else "Not set"}
Branch: {branch if branch else "Not set"}

Example:
  %(prog)s
  %(prog)s --target-dir ./my-project
        """,
    )

    parser.add_argument(
        "--target-dir",
        default=".",
        help="Target directory (default: current directory)",
    )

    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()

    return clone_repository(repo_url, ref, ref_type, target_dir)


if __name__ == "__main__":
    sys.exit(main())
