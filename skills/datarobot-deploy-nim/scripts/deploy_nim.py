#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Register a NIM custom model version and deploy it to a serverless GPU PE.

REST:
  POST /api/v2/modelPackages/fromCustomModelVersion/  {customModelVersionId, name}
  GET  /api/v2/predictionEnvironments/                 (pick the serverless PE)
  POST /api/v2/deployments/fromModelPackage/           {modelPackageId, label, predictionEnvironmentId}

Usage:
    python deploy_nim.py --custom-model-version-id <id> --label <name> \
        [--prediction-environment-id <id>]
"""

import argparse
import os
import sys
from typing import Any
import time

READY_STATUSES = {"active"}
FAILED_STATUSES = {"errored", "error", "failed", "inactive"}


def deployment_ready(status: str | None) -> bool:
    return (status or "").lower() in READY_STATUSES


def deployment_failed(status: str | None) -> bool:
    return (status or "").lower() in FAILED_STATUSES


def pick_serverless_pe(pes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pes:
        return None
    for pe in pes:
        if (pe.get("platform") or "").lower() == "datarobotserverless":
            return pe
    for pe in pes:
        if "serverless" in (pe.get("name") or "").lower():
            return pe
    return None


def build_deploy_payload(
    model_package_id: str, label: str, prediction_environment_id: str
) -> dict[str, str]:
    if not prediction_environment_id:
        raise ValueError("a serverless GPU prediction_environment_id is required")
    return {
        "modelPackageId": model_package_id,
        "label": label,
        "predictionEnvironmentId": prediction_environment_id,
    }


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("--custom-model-version-id", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--prediction-environment-id")
    p.add_argument("--no-wait", action="store_true", help="don't poll for readiness")
    p.add_argument(
        "--timeout", type=int, default=900, help="seconds to wait for active"
    )
    p.add_argument("--poll-interval", type=int, default=15)
    args = p.parse_args(argv[1:])

    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )

    reg_resp = client.post(
        "modelPackages/fromCustomModelVersion/",
        data={"customModelVersionId": args.custom_model_version_id, "name": args.label},
    )
    reg_resp.raise_for_status()
    pkg = reg_resp.json()
    model_package_id = pkg.get("id")
    if not model_package_id:
        print(f"Failed to register model package: {pkg}", file=sys.stderr)
        return 1

    pe_id = args.prediction_environment_id
    if not pe_id:
        pes = client.get("predictionEnvironments/").json().get("data", [])
        chosen = pick_serverless_pe(pes)
        if not chosen:
            print(
                "No serverless prediction environment found; pass --prediction-environment-id."
            )
            return 1
        pe_id = chosen["id"]

    body = build_deploy_payload(model_package_id, args.label, pe_id)
    resp = client.post("deployments/fromModelPackage/", data=body)
    resp.raise_for_status()
    out = resp.json()
    dep_id = out.get("id")
    print(f"Deployment {dep_id} created (HTTP {resp.status_code}).")
    if not dep_id:
        print(f"No deployment id in response: {out}", file=sys.stderr)
        return 1

    # Provisioning is async (fromModelPackage returns before the deployment is live).
    # Poll status until active, unless --no-wait.
    if not args.no_wait:
        deadline = time.time() + args.timeout
        status = None
        while time.time() < deadline:
            status = client.get(f"deployments/{dep_id}/").json().get("status")
            if deployment_ready(status):
                print(f"Deployment {dep_id} is active.")
                break
            if deployment_failed(status):
                print(f"Deployment {dep_id} failed (status={status}).", file=sys.stderr)
                return 1
            print(f"  ...status={status}; waiting {args.poll_interval}s")
            time.sleep(args.poll_interval)
        else:
            print(
                f"Timed out after {args.timeout}s (last status={status}). "
                f"Check the deployment in DataRobot.",
                file=sys.stderr,
            )
            return 1

    print(
        "Next: expose it with datarobot-register-mcp-tool (NIM auto-detects as chat)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
