#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Create a NIM custom model + version from a NIM container template.

REST: POST /api/v2/customModels/fromModelTemplate/  (requires feature flag NIM_MODELS).
Returns {"customModelId": ..., "customModelVersionId": ...}. The NGC API key must
already be stored as a secureConfig and passed as secret_config_id.

Usage:
    python create_nim_from_template.py --template-id <id> --resource-bundle-id <id> \
        [--secret-config-id <id>] [--container-tag-override <tag>]
"""

import argparse
import os
import sys


def build_nim_create_payload(
    template_id, resource_bundle_id, secret_config_id=None, container_tag_override=None
) -> dict:
    if not template_id or not resource_bundle_id:
        raise ValueError("template_id and resource_bundle_id are required")
    body = {"templateId": template_id, "resourceBundleId": resource_bundle_id}
    if secret_config_id is not None:
        body["secretConfigId"] = secret_config_id
    if container_tag_override is not None:
        body["nimContainerTagOverride"] = container_tag_override
    return body


def main(argv: list[str]) -> int:
    import datarobot as dr

    p = argparse.ArgumentParser()
    p.add_argument("--template-id", required=True)
    p.add_argument("--resource-bundle-id", required=True)
    p.add_argument("--secret-config-id")
    p.add_argument("--container-tag-override")
    args = p.parse_args(argv[1:])

    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )
    body = build_nim_create_payload(
        args.template_id,
        args.resource_bundle_id,
        args.secret_config_id,
        args.container_tag_override,
    )
    resp = client.post("customModels/fromModelTemplate/", data=body)
    out = resp.json()
    print(
        f"customModelId={out.get('customModelId')} "
        f"customModelVersionId={out.get('customModelVersionId')}"
    )
    print("Next: register + deploy with deploy_nim.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
