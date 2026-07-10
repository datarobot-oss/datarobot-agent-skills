#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Merge LLM config + optional credentials file into project .env.

Usage:
  python sync_llm_env.py write-template --provider azure --output .secrets/llm-external.env
  python sync_llm_env.py sync --config .datarobot/llm-config.json --env-file .env
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

INTEGRATION_TO_INFRA = {
    "gateway": "gateway_direct.py",
    "deployed": "deployed_llm.py",
    "external": "blueprint_with_external_llm.py",
    "blueprint-gateway": "blueprint_with_llm_gateway.py",
}

LLM_MANAGED_KEYS = frozenset(
    {
        "INFRA_ENABLE_LLM",
        "LLM_DEFAULT_MODEL",
        "LLM_DEPLOYMENT_ID",
        "LLM_DEFAULT_LLM_ID",
        "LLM_DEFAULT_LLM_NAME",
        "USE_DATAROBOT_LLM_GATEWAY",
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "OPENAI_API_DEPLOYMENT_ID",
        "OPENAI_API_VERSION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION_NAME",
        "VERTEXAI_APPLICATION_CREDENTIALS",
        "VERTEXAI_SERVICE_ACCOUNT",
        "ANTHROPIC_API_KEY",
        "COHERE_API_KEY",
        "TOGETHERAI_API_KEY",
    }
)

PROVIDER_REQUIRED_KEYS = {
    "azure": [
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "OPENAI_API_DEPLOYMENT_ID",
        "OPENAI_API_VERSION",
    ],
    "bedrock": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION_NAME"],
    "vertexai": ["VERTEXAI_APPLICATION_CREDENTIALS", "VERTEXAI_SERVICE_ACCOUNT"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "togetherai": ["TOGETHERAI_API_KEY"],
}


def _template(provider: str) -> str:
    header = f"# {provider} — fill values locally. Do not commit this file.\n"
    return header + "".join(f"{key}=\n" for key in PROVIDER_REQUIRED_KEYS[provider])


def _quote(value: str) -> str:
    """Single-quote if `$` is present (blocks interpolation); otherwise minimal quoting."""
    if not value:
        return '""'
    if "$" in value:
        return "'" + value.replace("'", "'\"'\"'") + "'"
    if re.search(r'[\s#"\\]', value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _read_kv(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        result[k.strip()] = v
    return result


def parse_dotenv(path: Path) -> list[str]:
    """Return .env lines with any managed keys stripped out."""
    if not path.exists():
        return []
    kept = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            if stripped.partition("=")[0].strip() in LLM_MANAGED_KEYS:
                continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    return kept


def build_llm_env(config: dict[str, Any]) -> dict[str, str]:
    integration = config.get("integration", "").strip()
    if integration not in INTEGRATION_TO_INFRA:
        raise ValueError(
            f"integration must be one of: {', '.join(INTEGRATION_TO_INFRA)}"
        )
    env = {"INFRA_ENABLE_LLM": INTEGRATION_TO_INFRA[integration]}

    if integration in ("gateway", "blueprint-gateway"):
        model = (config.get("llm_model") or "").strip()
        if not model:
            raise ValueError("llm_model is required for gateway modes")
        if not model.startswith("datarobot/"):
            model = f"datarobot/{model}"
        env["LLM_DEFAULT_MODEL"] = model
        if integration == "blueprint-gateway" and config.get("llm_llm_id"):
            env["LLM_DEFAULT_LLM_ID"] = config["llm_llm_id"]

    elif integration == "deployed":
        dep_id = (config.get("llm_deployment_id") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{24}", dep_id):
            raise ValueError("llm_deployment_id must be 24 lowercase hex chars")
        env["LLM_DEPLOYMENT_ID"] = dep_id
        env["LLM_DEFAULT_MODEL"] = config.get(
            "llm_model", "datarobot/datarobot-deployed-llm"
        )
        env["USE_DATAROBOT_LLM_GATEWAY"] = "0"

    else:  # external
        provider = (config.get("external_provider") or "").strip()
        if provider not in PROVIDER_REQUIRED_KEYS:
            raise ValueError(
                f"external_provider must be one of: {', '.join(PROVIDER_REQUIRED_KEYS)}"
            )
        model = (config.get("llm_model") or "").strip()
        if not model:
            raise ValueError(
                f"llm_model is required for external mode (provider: {provider})"
            )
        creds_path = Path(config.get("credentials_file", ".secrets/llm-external.env"))
        if not creds_path.exists():
            raise ValueError(f"Credentials file not found: {creds_path}")
        creds = _read_kv(creds_path)
        missing = [k for k in PROVIDER_REQUIRED_KEYS[provider] if not creds.get(k)]
        if missing:
            raise ValueError(f"Missing keys in {creds_path}: {', '.join(missing)}")
        env["LLM_DEFAULT_MODEL"] = model
        for key in PROVIDER_REQUIRED_KEYS[provider]:
            env[key] = creds[key]

    return env


def cmd_write_template(args: argparse.Namespace) -> int:
    if args.provider not in PROVIDER_REQUIRED_KEYS:
        print(f"Unknown provider '{args.provider}'", file=sys.stderr)
        return 1
    output = Path(args.output)
    if output.exists() and not args.force:
        print(f"Refusing to overwrite {output} (use --force)", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_template(args.provider), encoding="utf-8")
    print(f"Wrote credential template: {output}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    env_path = Path(args.env_file)

    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        llm_vars = build_llm_env(config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    preserved = parse_dotenv(env_path)
    out = preserved + ([""] if preserved else [])
    for key in sorted(llm_vars):
        out.append(f"{key}={_quote(llm_vars[key])}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"Synced {len(llm_vars)} LLM variable(s) into {env_path}")
    for key in sorted(llm_vars):
        print(f"  ✓ {key}")

    if args.delete_config:
        config_path.unlink()
        print(f"Deleted {config_path}")

    print(
        "\nNext (user should run in their own terminal — these echo secrets):\n"
        "  dr dotenv validate\n"
        "  dr task run infra:up-yes"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync LLM config into .env")
    sub = parser.add_subparsers(dest="command", required=True)

    wt = sub.add_parser("write-template")
    wt.add_argument("--provider", required=True)
    wt.add_argument("--output", default=".secrets/llm-external.env")
    wt.add_argument("--force", action="store_true")
    wt.set_defaults(func=cmd_write_template)

    sync = sub.add_parser("sync")
    sync.add_argument("--config", default=".datarobot/llm-config.json")
    sync.add_argument("--env-file", default=".env")
    sync.add_argument("--delete-config", action="store_true")
    sync.set_defaults(func=cmd_sync)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
