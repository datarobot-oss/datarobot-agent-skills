# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from deploy_nim import (
    pick_serverless_pe,
    build_deploy_payload,
    deployment_ready,
    deployment_failed,
)


def test_deployment_ready_and_failed() -> None:
    assert deployment_ready("active") is True
    assert deployment_ready("ACTIVE") is True
    assert deployment_ready("launching") is False
    assert deployment_ready(None) is False
    assert deployment_failed("errored") is True
    assert deployment_failed("inactive") is True
    assert deployment_failed("active") is False


def test_pick_serverless_prefers_datarobot_serverless_platform() -> None:
    pes = [
        {"id": "pe1", "platform": "datarobot", "name": "legacy eks wrapper"},
        {
            "id": "pe2",
            "platform": "datarobotServerless",
            "name": "manufacturing-pod NIMs",
        },
    ]
    chosen = pick_serverless_pe(pes)
    assert chosen is not None and chosen["id"] == "pe2"


def test_pick_serverless_falls_back_to_name() -> None:
    pes = [{"id": "pe1", "platform": "aws", "name": "my serverless env"}]
    chosen = pick_serverless_pe(pes)
    assert chosen is not None and chosen["id"] == "pe1"


def test_pick_serverless_empty_none() -> None:
    assert pick_serverless_pe([]) is None


def test_deploy_payload_shape_and_pe_required() -> None:
    body = build_deploy_payload("pkg1", "my-nim", "pe2")
    assert body == {
        "modelPackageId": "pkg1",
        "label": "my-nim",
        "predictionEnvironmentId": "pe2",
    }
    assert "defaultPredictionServerId" not in body
    with pytest.raises(ValueError):
        build_deploy_payload("pkg1", "my-nim", "")
