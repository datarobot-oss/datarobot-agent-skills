#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Compose a DataRobot agent project using Application Framework v2.

Replaces the static git-clone step with an AF v2 composition sequence: initialize
framework state, add a registry, add modules derived from agent_spec.md, answer
module questions, run copy, and run tasks. The resulting directory structure is
equivalent to what the old template clone produced but is managed by the AF v2
update lifecycle.

Usage:
    python compose_template.py \\
        --framework <langgraph|crewai|llamaindex|nat|base> \\
        [--target-dir <directory>] \\
        [--spec <path/to/agent_spec.md>] \\
        [--registry-uri <uri>] \\
        [--registry-alias <alias>] \\
        [--app-name <slug>] \\
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
FRAMEWORKS = ["langgraph", "crewai", "llamaindex", "nat", "base"]

# Modules always added regardless of frontend.type
_CORE_MODULES = ["base", "llm", "datarobot-mcp", "agent"]

# Extra modules added when frontend.type == chat
_CHAT_MODULES = [
    "fastapi-backend",
    "fastapi-memory",
    "fastapi-users",
    "fastapi-auth",
    "fastapi-chat",
    "react",
    "react-auth",
    "react-i18n",
    "react-chat",
]


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


def read_spec(spec_path: Path) -> dict[str, str]:
    """Read key:value pairs from agent_spec.md (plain YAML, no library).

    Only extracts the fields the compose step cares about: frontend.type and
    use_agent_memory. Everything else is validated upstream by SKILL.md before
    this script is called.
    """
    result: dict[str, str] = {}
    if not spec_path.exists():
        return result
    in_frontend = False
    for raw_line in spec_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("frontend:"):
            in_frontend = True
            continue
        if in_frontend:
            if line.startswith("type:") or line.startswith("type "):
                val = line.split(":", 1)[1].strip().strip('"').strip("'")
                result["frontend.type"] = val
                continue
            if not line.startswith("-") and ":" in line and not line.startswith(" "):
                in_frontend = False
        if line.startswith("use_agent_memory:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            result["use_agent_memory"] = val
    return result


def _slugify(name: str) -> str:
    """Convert a directory name to a safe app name slug."""
    slug = name.lower().replace(" ", "-").replace("_", "-")
    return slug or "agent"


def compose(
    target_dir: Path,
    framework: str,
    spec_path: Path,
    registry_uri: str,
    registry_alias: str,
    app_name: str,
    dry_run: bool,
) -> int:
    """Execute the AF v2 composition sequence and return an exit code."""
    spec = read_spec(spec_path)
    frontend_type = spec.get("frontend.type", "chat")
    use_memory = spec.get("use_agent_memory", "false").lower()
    full_chat = frontend_type == "chat"

    modules = list(_CORE_MODULES)
    if full_chat:
        modules += _CHAT_MODULES

    print()
    print("=" * 60)
    print("AF v2 Composition")
    print(f"  Framework : {framework}")
    print(f"  Frontend  : {frontend_type}")
    print(f"  App name  : {app_name}")
    print(f"  Registry  : {registry_uri} (alias: {registry_alias})")
    print(f"  Modules   : {', '.join(modules)}")
    if dry_run:
        print("  Mode      : DRY RUN — commands printed, not executed")
    print("=" * 60)
    print()

    # 1. Initialize framework state
    ok, out = run_dr(["initialize-framework"], "Initialize framework", target_dir, dry_run=dry_run)
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
        extra: list[str] = []
        # Wire agent's dependency labels once llm and datarobot-mcp are known
        if mod == "agent":
            if "llm" in labels:
                extra += ["-d", f"llm={labels['llm']}"]
            if "datarobot-mcp" in labels:
                extra += ["-d", f"datarobot-mcp={labels['datarobot-mcp']}"]
        ok, out = run_dr(
            ["add-module", "-m", qualified] + extra,
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
            print(f"  ⚠ Could not parse label from add-module output for {mod}", file=sys.stderr)

    # 4. Answer module questions
    agent_label = labels.get("agent", f"{registry_alias}.agent.1")
    llm_label = labels.get("llm", f"{registry_alias}.llm.1")
    mcp_label = labels.get("datarobot-mcp", f"{registry_alias}.datarobot-mcp.1")

    answers_agent = [
        "-a", f"agent_template_framework={framework}",
        "-a", f"agent_app_name={app_name}",
        "-a", f"use_agent_memory={use_memory}",
        "-a", "template_name=datarobot-agent",
    ]
    ok, out = run_dr(
        ["answer", "-l", agent_label] + answers_agent,
        f"Answer agent questions ({agent_label})",
        target_dir,
        dry_run=dry_run,
    )
    if not ok:
        print(out, file=sys.stderr)
        return 1

    ok, out = run_dr(
        ["answer", "-l", llm_label, "-a", f"llm_app_name={app_name}-llm"],
        f"Answer llm questions ({llm_label})",
        target_dir,
        dry_run=dry_run,
    )
    if not ok:
        print(out, file=sys.stderr)
        return 1

    ok, out = run_dr(
        ["answer", "-l", mcp_label, "-a", f"mcp_app_name={app_name}-mcp"],
        f"Answer datarobot-mcp questions ({mcp_label})",
        target_dir,
        dry_run=dry_run,
    )
    if not ok:
        print(out, file=sys.stderr)
        return 1

    if full_chat:
        # Chat stack answer stubs — values are placeholders until those
        # components define their final question keys in the registry.
        fastapi_memory_label = labels.get(
            "fastapi-memory", f"{registry_alias}.fastapi-memory.1"
        )
        fastapi_auth_label = labels.get("fastapi-auth", f"{registry_alias}.fastapi-auth.1")
        ok, out = run_dr(
            [
                "answer", "-l", fastapi_memory_label,
                "-a", "memory_space_id=default",
            ],
            f"Answer fastapi-memory questions ({fastapi_memory_label})",
            target_dir,
            dry_run=dry_run,
        )
        if not ok:
            print(out, file=sys.stderr)
            return 1
        ok, out = run_dr(
            [
                "answer", "-l", fastapi_auth_label,
                "-a", "oauth_impl=none",
                "-a", "mock_test_user=true",
            ],
            f"Answer fastapi-auth questions ({fastapi_auth_label})",
            target_dir,
            dry_run=dry_run,
        )
        if not ok:
            print(out, file=sys.stderr)
            return 1

    # 5. Materialize the project
    ok, out = run_dr(["copy"], "Copy (materialize project)", target_dir, timeout=300, dry_run=dry_run)
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
        description="Compose a DataRobot agent project using Application Framework v2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --framework langgraph
  %(prog)s --framework crewai --app-name my-sales-agent
  %(prog)s --framework langgraph --registry-uri file:///path/to/registry.yml --dry-run
        """,
    )
    parser.add_argument(
        "--framework",
        required=True,
        choices=FRAMEWORKS,
        metavar="FRAMEWORK",
        help="Agentic framework ({})".format(", ".join(FRAMEWORKS)),
    )
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Target directory (default: current directory)",
    )
    parser.add_argument(
        "--spec",
        default=None,
        help="Path to agent_spec.md (default: <target-dir>/agent_spec.md)",
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
        "--app-name",
        default=None,
        help="App name slug (default: derived from target directory name)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the dr component command sequence without executing",
    )
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    spec_path = Path(args.spec).resolve() if args.spec else target_dir / "agent_spec.md"
    app_name = args.app_name or _slugify(target_dir.name)

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
        framework=args.framework,
        spec_path=spec_path,
        registry_uri=args.registry_uri,
        registry_alias=args.registry_alias,
        app_name=app_name,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
