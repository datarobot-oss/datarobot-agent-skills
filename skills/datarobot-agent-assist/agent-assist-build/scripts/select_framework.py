#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Save the chosen agentic framework for a DataRobot agent project.

Writes agent_template_framework to .datarobot/answers/agent-agent.yml,
preserving all other fields in the file.

Usage:
    python select_framework.py --framework <value> [--target-dir <directory>]

Framework values: langgraph, crewai, llamaindex, nat, base
"""

import argparse
import sys
from pathlib import Path

FRAMEWORKS = ["langgraph", "crewai", "llamaindex", "nat", "base"]

ANSWERS_FILE = Path(".datarobot") / "answers" / "agent-agent.yml"
FIELD_NAME = "agent_template_framework"


def save_framework(target_dir: Path, framework_value: str) -> None:
    """Write agent_template_framework to the answers YAML file.

    Preserves all existing lines; only updates or appends agent_template_framework.

    Args:
        target_dir: Project root directory.
        framework_value: Framework identifier to save.
    """
    answers_path = target_dir / ANSWERS_FILE
    answers_path.parent.mkdir(parents=True, exist_ok=True)

    new_line = f"{FIELD_NAME}: {framework_value}\n"
    prefix = f"{FIELD_NAME}:"

    if answers_path.exists():
        lines = answers_path.read_text().splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.startswith(prefix):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)
        answers_path.write_text("".join(lines))
    else:
        answers_path.write_text(new_line)

    print(f"\n✓ Saved '{framework_value}' to {answers_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Save the agentic framework for a DataRobot agent project."
    )
    parser.add_argument(
        "--framework",
        required=True,
        choices=FRAMEWORKS,
        metavar="FRAMEWORK",
        help="Framework to save ({})".format(", ".join(FRAMEWORKS)),
    )
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Project root directory (default: current working directory)",
    )
    args = parser.parse_args()

    target_dir = Path(args.target_dir).resolve()
    if not target_dir.is_dir():
        print(f"Error: target directory does not exist: {target_dir}", file=sys.stderr)
        return 1

    save_framework(target_dir, args.framework)
    return 0


if __name__ == "__main__":
    sys.exit(main())
