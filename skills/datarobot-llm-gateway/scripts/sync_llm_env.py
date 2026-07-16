#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Merge LLM configuration into project .env.

The assistant passes the mode-specific values as CLI args. For external mode,
provider credentials are read from
`$XDG_CONFIG_HOME/datarobot/llm-<provider>.env` (default
`~/.config/datarobot/llm-<provider>.env`) — per-user, reusable across projects,
alongside the DataRobot auth `dr auth login` writes to `drconfig.yaml`.

If the credentials file is missing or incomplete, the script writes a blank
template with the required keys and exits so the user can fill it in.

Usage:
  python sync_llm_env.py --integration gateway \
    --llm-model datarobot/azure/o4-mini

  python sync_llm_env.py --integration blueprint-gateway \
    --llm-model datarobot/azure/o4-mini --llm-llm-id azure-openai-gpt-5-mini

  python sync_llm_env.py --integration deployed \
    --llm-deployment-id 6510c7b7c4f3f9407e24a849

  python sync_llm_env.py --integration external \
    --external-provider azure --llm-model azure-openai-gpt-5-mini
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

INTEGRATION_TO_INFRA = {
    "gateway": "gateway_direct.py",
    "deployed": "deployed_llm.py",
    "external": "blueprint_with_external_llm.py",
    "blueprint-gateway": "blueprint_with_llm_gateway.py",
}

PROVIDER_KEYS = {
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

# Keys owned by this script — stripped from .env on every re-sync so mode
# switches don't leave stale entries (e.g. bedrock → gateway clears AWS_*).
LLM_MANAGED_KEYS = frozenset(
    {
        "INFRA_ENABLE_LLM",
        "LLM_DEFAULT_MODEL",
        "LLM_DEPLOYMENT_ID",
        "LLM_DEFAULT_LLM_ID",
        "LLM_DEFAULT_LLM_NAME",
        "USE_DATAROBOT_LLM_GATEWAY",
    }
    | {k for keys in PROVIDER_KEYS.values() for k in keys}
)


def _config_dir() -> Path:
    root = os.getenv("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(root) / "datarobot"


def _quote(value: str) -> str:
    if not value:
        return '""'
    if "$" in value:
        return "'" + value.replace("'", "'\"'\"'") + "'"
    if re.search(r'[\s#"\\]', value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _read_kv(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
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


def _write_provider_template(provider: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# DataRobot LLM — {provider} provider credentials (per-user).",
        "# Fill each value below. Do not commit this file.",
        "",
    ]
    lines += [f"{key}=" for key in PROVIDER_KEYS[provider]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_dotenv(path: Path) -> list[str]:
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


def build_llm_env(args: argparse.Namespace) -> dict[str, str]:
    integration = args.integration
    env = {"INFRA_ENABLE_LLM": INTEGRATION_TO_INFRA[integration]}

    if integration in ("gateway", "blueprint-gateway"):
        if not args.llm_model:
            raise ValueError("--llm-model is required for gateway modes")
        model = args.llm_model.strip()
        if not model.startswith("datarobot/"):
            model = f"datarobot/{model}"
        env["LLM_DEFAULT_MODEL"] = model
        if integration == "blueprint-gateway" and args.llm_llm_id:
            env["LLM_DEFAULT_LLM_ID"] = args.llm_llm_id.strip()

    elif integration == "deployed":
        dep_id = (args.llm_deployment_id or "").strip()
        if not re.fullmatch(r"[0-9a-f]{24}", dep_id):
            raise ValueError("--llm-deployment-id must be 24 lowercase hex chars")
        env["LLM_DEPLOYMENT_ID"] = dep_id
        env["LLM_DEFAULT_MODEL"] = args.llm_model or "datarobot/datarobot-deployed-llm"
        env["USE_DATAROBOT_LLM_GATEWAY"] = "0"

    else:  # external
        provider = args.external_provider
        if provider not in PROVIDER_KEYS:
            raise ValueError(
                f"--external-provider must be one of: {', '.join(sorted(PROVIDER_KEYS))}"
            )
        if not args.llm_model:
            raise ValueError(
                f"--llm-model is required for external mode (provider: {provider})"
            )
        creds_path = _config_dir() / f"llm-{provider}.env"
        if not creds_path.exists():
            _write_provider_template(provider, creds_path)
            raise ValueError(
                f"Wrote credential template to {creds_path}. "
                f"Fill in {', '.join(PROVIDER_KEYS[provider])} and re-run this "
                "command. Do not paste the values in chat."
            )
        creds = _read_kv(creds_path)
        missing = [k for k in PROVIDER_KEYS[provider] if not creds.get(k)]
        if missing:
            raise ValueError(
                f"{creds_path} is missing values for: {', '.join(missing)}. "
                "Edit the file, then re-run."
            )
        env["LLM_DEFAULT_MODEL"] = args.llm_model.strip()
        for key in PROVIDER_KEYS[provider]:
            env[key] = creds[key]

    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync LLM config into .env")
    parser.add_argument(
        "--integration", required=True, choices=list(INTEGRATION_TO_INFRA)
    )
    parser.add_argument("--llm-model")
    parser.add_argument("--llm-llm-id")
    parser.add_argument("--llm-deployment-id")
    parser.add_argument("--external-provider", choices=list(PROVIDER_KEYS))
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    env_path = Path(args.env_file)

    try:
        llm_vars = build_llm_env(args)
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

    print(
        "\nNext (run in your terminal — these echo secrets):\n"
        "  dr dotenv validate\n"
        "  dr task run infra:up-yes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
