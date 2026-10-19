#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Print the real LLM options from the project's DataRobot CLI config.

`.datarobot/cli/llm.yml` is rendered into the project by `dr component add`
(af-component-llm) and committed, so it is the source of truth for which
integrations that project actually supports, what they are called, and which
env vars each one needs. Reading it here keeps this skill correct across
component versions instead of hardcoding lists that go stale.

Usage:
  python read_llm_config.py                                  # INFRA_ENABLE_LLM help + options
  python read_llm_config.py --option gateway_direct.py       # env vars that option needs
  python read_llm_config.py --option OpenAI --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_YML = ".datarobot/cli/llm.yml"


def load(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML is required. Install it: pip install pyyaml")
    if not path.exists():
        sys.exit(
            f"{path} not found. The LLM component is not applied to this "
            "project — run `dr component add` to add af-component-llm."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        sys.exit(f"{path} is not a YAML mapping.")
    return data


def entries(config: dict[str, Any], section: str) -> list[dict[str, Any]]:
    raw = config.get(section)
    return [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []


def options(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = entry.get("options")
    if not isinstance(raw, list):
        return []
    # Older configs omit `value` on nested choices and carry only name+requires.
    return [o for o in raw if isinstance(o, dict) and ("value" in o or "requires" in o)]


def selector(option: dict[str, Any]) -> str:
    """What to pass back as --option. Falls back when `value` is absent."""
    return str(option.get("value") or option.get("name") or option.get("requires"))


def find_key(config: dict[str, Any], section: str, key: str) -> dict[str, Any]:
    for entry in entries(config, section):
        if entry.get("env") == key or entry.get("key") == key:
            return entry
    sys.exit(f"No entry {key!r} in section {section!r}.")


def resolve(config: dict[str, Any], value: str) -> str:
    """Map an option value to the section it requires, at any nesting level."""
    for section in config:
        for entry in entries(config, section):
            for option in options(entry):
                names = {
                    option.get("value"),
                    option.get("name"),
                    option.get("requires"),
                }
                if value in {str(n) for n in names if n is not None}:
                    required = option.get("requires")
                    if not required:
                        sys.exit(f"Option {value!r} declares no `requires`.")
                    return str(required)
    sys.exit(f"Unknown option {value!r}.")


def describe(entry: dict[str, Any]) -> str:
    """One line of flags for an env var: type, whether it's needed, default."""
    flags = [str(entry.get("type", "string"))]
    if entry.get("hidden"):
        flags.append("hidden")
    elif entry.get("optional") is False:
        flags.append("required")
    else:
        flags.append("optional")
    if entry.get("type") == "secret_string":
        flags.append("SECRET - never accept in chat")
    if entry.get("default") is not None:
        flags.append(f"default: {entry['default']}")
    return ", ".join(flags)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-yml", default=DEFAULT_YML)
    parser.add_argument("--section", default="root")
    parser.add_argument("--key", default="INFRA_ENABLE_LLM")
    parser.add_argument("--option", help="Option value to describe")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    config = load(Path(args.llm_yml))

    if not args.option:
        entry = find_key(config, args.section, args.key)
        payload = {
            "key": args.key,
            "default": entry.get("default"),
            "help": (entry.get("help") or "").strip(),
            "options": options(entry),
        }
        if args.as_json:
            print(json.dumps(payload, indent=2))
            return 0
        print(f"{args.key}  (default: {payload['default']})\n")
        print(payload["help"], "\n")
        print("options:")
        for option in options(entry):
            print(f"  {option.get('name', selector(option))}")
            print(f"      select: {selector(option)}")
        return 0

    section = resolve(config, args.option)
    fields = entries(config, section)

    if args.as_json:
        print(
            json.dumps(
                {"option": args.option, "section": section, "fields": fields}, indent=2
            )
        )
        return 0

    print(f"{args.option}  ->  section: {section}\n")
    for entry in fields:
        if options(entry):
            print(f"  further choice: {entry.get('key') or entry.get('env')}")
            for option in options(entry):
                print(f"      {option.get('name', selector(option))}")
                print(f"          select: {selector(option)}")
            print("      re-run with --option <select> for its env vars")
        elif entry.get("env"):
            print(f"  {entry['env']}  ({describe(entry)})")
            if entry.get("help"):
                print(f"      {str(entry['help']).strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
