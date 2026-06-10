#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Thin executor for AF v2 composition.

Receives a pre-selected module list and a pre-collected answers map from the
agent, then runs the dr component sequence: initialize-framework → add-registry
→ add-module (per module) → answer (per answer) → copy → run-tasks.

Component selection and question collection are handled conversationally by the
agent (via `dr component list-available` and `dr component describe`) before
this script is called.

Usage:
    python compose_template.py \\
        --modules '["base", "llm", "datarobot_mcp", "agent"]' \\
        --answers '{"core.agent.1.agent_template_framework": "langgraph"}' \\
        [--target-dir <directory>] \\
        [--registry-uri <uri>] \\
        [--registry-alias <alias>] \\
        [--dry-run]

The --registry-uri defaults to https://af.datarobot.com/registry.yml.
Use file:// for a local registry during early bring-up (registry not yet live).
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

DEFAULT_REGISTRY_URI = "https://af.datarobot.com/registry.yml"
DEFAULT_ALIAS = "core"


def check_guardrails(target_dir: Path) -> tuple[bool, Optional[str]]:
    """Fail fast if the directory already has a git repo or AGENTS.md."""
    print("Running guardrail checks...")

    if (target_dir / ".git").exists():
        return (
            False,
            f"Git repository already initialized in {target_dir}\n"
            f"\tFound: {target_dir / '.git'}\n"
            "\tAborting to prevent overwriting existing repository",
        )

    if (target_dir / "AGENTS.md").exists():
        return (
            False,
            f"AGENTS.md already exists in {target_dir}\n"
            "\tAborting to prevent overwriting existing configuration",
        )

    print("✓ Guardrail checks passed")

    return True, None


def _dr_env() -> dict[str, str]:
    """Return environment with non-interactive flag set for dr commands."""
    env = os.environ.copy()
    env["DATAROBOT_CLI_NON_INTERACTIVE"] = "True"

    return env


def run_dr(
    args: list[str],
    description: str,
    target_dir: Path,
    timeout: int = 120,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Run a `dr component` subcommand and return (success, output).

    In dry-run mode prints the command without executing it.
    """
    cmd = ["dr", "component"] + args
    cmd_str = " ".join(cmd)

    if dry_run:
        print(f"  [dry-run] {cmd_str}")

        return True, ""

    print(f"{description}...")

    try:
        result = subprocess.run(
            cmd,
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=_dr_env(),
        )
        output = result.stdout + result.stderr

        if result.returncode == 0:
            print(f"✓ {description}")
        else:
            print(f"✗ {description}", file=sys.stderr)

        return result.returncode == 0, output

    except subprocess.TimeoutExpired:
        msg = f"Command timed out after {timeout}s: {cmd_str}"
        print(f"✗ {msg}", file=sys.stderr)

        return False, msg

    except Exception as e:
        print(f"✗ {description}: {e}", file=sys.stderr)

        return False, str(e)


def _extract_label(output: str) -> Optional[str]:
    """Parse the label from JSON emitted by `add-module`."""
    try:
        data = json.loads(output)
        label: Optional[str] = data.get("label")

        return label

    except (json.JSONDecodeError, AttributeError):
        return None


def compose(
    target_dir: Path,
    modules: list[str],
    answers: dict[str, object],
    registry_uri: str,
    registry_alias: str,
    dry_run: bool,
) -> int:
    """Execute the AF v2 composition sequence and return an exit code."""
    print()
    print("=" * 60)
    print("AF v2 Composition")
    print(f"  Modules   : {', '.join(modules)}")
    print(f"  Answers   : {len(answers)} question(s) pre-collected")
    print(f"  Registry  : {registry_uri} (alias: {registry_alias})")

    if dry_run:
        print("  Mode      : DRY RUN — commands printed, not executed")

    print("=" * 60)
    print()

    # 1. Initialize framework state
    ok, out = run_dr(
        ["initialize-framework"], "Initialize framework", target_dir, dry_run=dry_run
    )

    if not ok:
        print(out, file=sys.stderr)

        return 1

    # 2. Add registry
    ok, out = run_dr(
        ["add-registry", registry_uri, "--alias", registry_alias],
        f"Add registry {registry_uri}",
        target_dir,
        dry_run=dry_run,
    )

    if not ok:
        print(out, file=sys.stderr)

        return 1

    # 3. Add modules; capture labels returned by add-module
    labels: dict[str, str] = {}  # module short name -> label

    for mod in modules:
        qualified = f"{registry_alias}.{mod}"
        ok, out = run_dr(
            ["add-module", "-m", qualified],
            f"Add module {qualified}",
            target_dir,
            dry_run=dry_run,
        )

        if not ok:
            print(out, file=sys.stderr)

            return 1

        label = _extract_label(out)

        if label:
            labels[mod] = label
        elif not dry_run:
            print(
                f"  ⚠ Could not parse label from add-module output for {mod}",
                file=sys.stderr,
            )

    # 4. Answer module questions using the pre-collected answers map
    # Group answers by label prefix so we can batch them per label
    answers_by_label: dict[str, list[str]] = {}

    for key, value in answers.items():
        # key format: <label>.<question_name> — label itself contains dots (e.g. core.agent.1)
        # Split on the last dot to separate label from question name
        parts = key.rsplit(".", 1)

        if len(parts) != 2:  # noqa: PLR2004
            print(f"  ⚠ Skipping malformed answer key: {key}", file=sys.stderr)

            continue

        label, question = parts[0], parts[1]
        answers_by_label.setdefault(label, [])
        answers_by_label[label].append(f"{question}={value}")

    for label, answer_pairs in answers_by_label.items():
        answer_args: list[str] = []

        for pair in answer_pairs:
            answer_args += ["-a", pair]

        ok, out = run_dr(
            ["answer", "-l", label] + answer_args,
            f"Answer questions for {label}",
            target_dir,
            dry_run=dry_run,
        )

        if not ok:
            print(out, file=sys.stderr)

            return 1

    # 5. Materialize the project
    ok, out = run_dr(
        ["copy"], "Copy (materialize project)", target_dir, timeout=300, dry_run=dry_run
    )

    if not ok:
        print(out, file=sys.stderr)

        return 1

    # 6. Run staged tasks/migrations
    ok, out = run_dr(
        ["run-tasks", str(target_dir)],
        "Run tasks",
        target_dir,
        timeout=300,
        dry_run=dry_run,
    )

    if not ok:
        print(out, file=sys.stderr)

        return 1

    print()
    print("✓ AF v2 composition complete!")

    if not dry_run:
        print(f"  Location: {target_dir}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Thin AF v2 composition executor. Module selection and question collection are handled by the agent.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --modules '["base","llm","datarobot_mcp","agent"]' --answers '{}'
  %(prog)s --modules '["base","llm","datarobot_mcp","agent"]' \\
    --answers '{"core.agent.1.agent_template_framework":"langgraph","core.agent.1.agent_app_name":"my-agent"}' \\
    --dry-run
  %(prog)s --modules '["base","llm","datarobot_mcp","agent"]' --answers '{}' \\
    --registry-uri file:///path/to/registry.yml
        """,
    )
    parser.add_argument(
        "--modules",
        required=True,
        metavar="JSON",
        help="JSON array of module short names in dependency order",
    )
    parser.add_argument(
        "--answers",
        required=True,
        metavar="JSON",
        help="JSON object mapping <label>.<question_name> to answer value",
    )
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Target directory (default: current directory)",
    )
    parser.add_argument(
        "--registry-uri",
        default=DEFAULT_REGISTRY_URI,
        help=f"AF v2 registry URI (default: {DEFAULT_REGISTRY_URI})",
    )
    parser.add_argument(
        "--registry-alias",
        default=DEFAULT_ALIAS,
        help=f"Registry alias (default: {DEFAULT_ALIAS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the dr component command sequence without executing",
    )

    args = parser.parse_args()

    try:
        modules: list[str] = json.loads(args.modules)
    except json.JSONDecodeError as e:
        print(f"Error: --modules is not valid JSON: {e}", file=sys.stderr)

        return 1

    if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules):
        print("Error: --modules must be a JSON array of strings", file=sys.stderr)

        return 1

    try:
        answers_raw = json.loads(args.answers)
    except json.JSONDecodeError as e:
        print(f"Error: --answers is not valid JSON: {e}", file=sys.stderr)

        return 1

    if not isinstance(answers_raw, dict):
        print("Error: --answers must be a JSON object", file=sys.stderr)

        return 1

    answers: dict[str, object] = answers_raw

    target_dir = Path(args.target_dir).resolve()

    # Probe: confirm dr component is available before touching the filesystem
    probe = subprocess.run(
        ["dr", "component", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    if probe.returncode != 0:
        print(
            "Error: AF v2 CLI not available.\n"
            "  Run `dr self update --force` to install the latest DataRobot CLI.",
            file=sys.stderr,
        )

        return 1

    if not args.dry_run:
        passed, error_msg = check_guardrails(target_dir)

        if not passed:
            print(f"Error: {error_msg}", file=sys.stderr)

            return 1

        target_dir.mkdir(parents=True, exist_ok=True)

    return compose(
        target_dir=target_dir,
        modules=modules,
        answers=answers,
        registry_uri=args.registry_uri,
        registry_alias=args.registry_alias,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
