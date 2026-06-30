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


def pick_serverless_pe(pes: list[dict]) -> dict | None:
    if not pes:
        return None
    for pe in pes:
        if (pe.get("platform") or "").lower() == "datarobot":
            return pe
    for pe in pes:
        if "serverless" in (pe.get("name") or "").lower():
            return pe
    return None


def build_deploy_payload(model_package_id: str, label: str,
                         prediction_environment_id: str) -> dict:
    if not prediction_environment_id:
        raise ValueError("a serverless GPU prediction_environment_id is required")
    return {"modelPackageId": model_package_id, "label": label,
            "predictionEnvironmentId": prediction_environment_id}


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("--custom-model-version-id", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--prediction-environment-id")
    args = p.parse_args(argv[1:])

    client = dr.Client(token=os.getenv("DATAROBOT_API_TOKEN"),
                       endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"))

    pkg = client.post("modelPackages/fromCustomModelVersion/",
                      data={"customModelVersionId": args.custom_model_version_id,
                            "name": args.label}).json()
    model_package_id = pkg["id"]

    pe_id = args.prediction_environment_id
    if not pe_id:
        pes = client.get("predictionEnvironments/").json().get("data", [])
        chosen = pick_serverless_pe(pes)
        if not chosen:
            print("No serverless prediction environment found; pass --prediction-environment-id.")
            return 1
        pe_id = chosen["id"]

    body = build_deploy_payload(model_package_id, args.label, pe_id)
    resp = client.post("deployments/fromModelPackage/", data=body)
    out = resp.json()
    print(f"Deployment created: {out.get('id')} (status {resp.status_code}).")
    print("Next: expose it with datarobot-register-mcp-tool (NIM auto-detects as chat).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
