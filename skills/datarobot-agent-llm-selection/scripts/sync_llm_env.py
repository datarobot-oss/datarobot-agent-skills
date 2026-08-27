#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Merge LLM configuration into project .env.

Everything this script knows about integrations, env var names, and credential
keys comes from the project's own `.datarobot/cli/llm.yml` — the file
`dr component add` rendered from af-component-llm. Nothing is hardcoded here,
so a project generated from a newer component picks up its new integrations
without changing this script.

Values are passed as `--set KEY=VALUE` using the env var names that config
declares (they carry a per-project prefix from `llm_app_name`). Secrets are
never passed on the command line: for a provider that needs credentials, they
are read from `$XDG_CONFIG_HOME/datarobot/llm-<section>.env` (default
`~/.config/datarobot/llm-<section>.env`), which this script creates as a blank
template if it is missing.

Usage:
  python sync_llm_env.py --infra-enable-llm gateway_direct.py \
    --set LLM_DEFAULT_MODEL=datarobot/azure/gpt-5-mini

  python sync_llm_env.py --infra-enable-llm deployed_llm.py \
    --set LLM_DEPLOYMENT_ID=6510c7b7c4f3f9407e24a849

  python sync_llm_env.py --infra-enable-llm blueprint_with_external_llm.py \
    --provider "Azure with OpenAI" --set LLM_DEFAULT_MODEL=azure/gpt-5-mini
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

from read_llm_config import DEFAULT_YML, entries, find_key, load, options, resolve

INFRA_KEY = "INFRA_ENABLE_LLM"


def config_dir() -> Path:
    root = os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(root) / "datarobot"


def quote(value: str) -> str:
    if not value:
        return '""'
    if "$" in value:
        return "'" + value.replace("'", "'\"'\"'") + "'"
    if re.search(r'[\s#"\\]', value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def managed_keys(config: dict[str, Any]) -> set[str]:
    """Every env var this config can own, so mode switches clear stale keys."""
    keys = {INFRA_KEY}
    for section in config:
        for entry in entries(config, section):
            if entry.get("env"):
                keys.add(str(entry["env"]))
    return keys


def preserved_lines(path: Path, owned: set[str]) -> list[str]:
    if not path.exists():
        return []
    kept = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            if stripped.partition("=")[0].strip() in owned:
                continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    return kept


def write_template(section: str, fields: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# DataRobot LLM — {section} credentials (per-user).",
        "# Fill each value below. Do not commit this file.",
        "",
    ]
    for field in fields:
        if field.get("help"):
            lines.append(f"# {str(field['help']).strip()}")
        lines.append(f"{field['env']}=")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect(
    config: dict[str, Any], section: str, provider: str | None, supplied: dict[str, str]
) -> dict[str, str]:
    """Resolve one integration's env vars from the config plus --set values."""
    env: dict[str, str] = {}
    missing: list[str] = []
    credential_section: str | None = None

    for entry in entries(config, section):
        if options(entry):
            if not provider:
                choices = ", ".join(
                    str(o.get("value") or o.get("name")) for o in options(entry)
                )
                raise ValueError(
                    f"{section} requires a choice for "
                    f"{entry.get('key') or entry.get('env')}. Pass --provider "
                    f"with one of: {choices}"
                )
            credential_section = resolve(config, provider)
            continue

        name = entry.get("env")
        if not name:
            continue
        name = str(name)

        if entry.get("hidden"):
            env[name] = str(entry.get("default", ""))
            continue

        value = supplied.pop(name, None)
        if value is None and entry.get("default") is not None:
            value = str(entry["default"])
        if value is None:
            if entry.get("optional") is False:
                missing.append(f"{name} — {str(entry.get('help', '')).strip()}")
            continue

        # The config marks gateway catalog fields with its own type, so this
        # stays correct without naming any integration.
        if entry.get("type") == "llmgw_catalog" and not value.startswith("datarobot/"):
            value = f"datarobot/{value}"
        if name.endswith("_DEPLOYMENT_ID") and not re.fullmatch(r"[0-9a-f]{24}", value):
            raise ValueError(
                f"{name} must be 24 lowercase hex characters, got {value!r}"
            )

        env[name] = value

    if missing:
        raise ValueError("Missing required --set values:\n  " + "\n  ".join(missing))

    if credential_section:
        env.update(load_credentials(config, credential_section))

    if supplied:
        raise ValueError(
            f"These --set keys are not declared for {section}: "
            f"{', '.join(sorted(supplied))}"
        )
    return env


def load_credentials(config: dict[str, Any], section: str) -> dict[str, str]:
    fields = [e for e in entries(config, section) if e.get("env")]
    path = config_dir() / f"llm-{section}.env"

    if not path.exists():
        write_template(section, fields, path)
        raise ValueError(
            f"Wrote a credential template to {path}. Fill it in your own "
            "editor, then re-run this command. Do not paste values in chat. "
            "(If you used an earlier version of this skill, rename your "
            "existing llm-<provider>.env file to this path.)"
        )

    stored = read_kv(path)
    # Only `optional: false` is mandatory. Fields the config marks optional
    # (AWS_SESSION_TOKEN, GOOGLE_REGION) merge if filled and are skipped if not.
    required = [str(f["env"]) for f in fields if f.get("optional") is False]
    absent = [key for key in required if not stored.get(key)]
    if absent:
        raise ValueError(
            f"{path} is missing values for: {', '.join(absent)}. Edit the file, then re-run."
        )
    return {
        str(f["env"]): stored[str(f["env"])]
        for f in fields
        if stored.get(str(f["env"]))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync LLM config into .env")
    parser.add_argument("--llm-yml", default=DEFAULT_YML)
    parser.add_argument("--infra-enable-llm", required=True, dest="infra")
    parser.add_argument("--provider", help="Choice for a nested selector, if any")
    parser.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", dest="values"
    )
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    config = load(Path(args.llm_yml))

    valid = {
        str(o.get("value") or o.get("name"))
        for o in options(find_key(config, "root", INFRA_KEY))
    }
    if args.infra not in valid:
        print(
            f"Error: --infra-enable-llm must be one of: {', '.join(sorted(valid))}",
            file=sys.stderr,
        )
        return 1

    supplied: dict[str, str] = {}
    for item in args.values:
        key, sep, value = item.partition("=")
        if not sep:
            print(f"Error: --set expects KEY=VALUE, got {item!r}", file=sys.stderr)
            return 1
        supplied[key.strip()] = value

    try:
        llm_vars = collect(config, resolve(config, args.infra), args.provider, supplied)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    llm_vars[INFRA_KEY] = args.infra

    env_path = Path(args.env_file)
    kept = preserved_lines(env_path, managed_keys(config))
    out = kept + ([""] if kept else [])
    out += [f"{key}={quote(llm_vars[key])}" for key in sorted(llm_vars)]
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"Synced {len(llm_vars)} LLM variable(s) into {env_path}")
    for key in sorted(llm_vars):
        print(f"  ✓ {key}")
    print(
        "\nNext (run in your terminal — these echo secrets):\n"
        "  dr dotenv validate\n"
        "  dr task run infra:up-yes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
