# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from deploy_nim import pick_serverless_pe, build_deploy_payload


def test_pick_serverless_prefers_datarobot_platform():
    pes = [{"id": "pe1", "platform": "aws", "name": "ext"},
           {"id": "pe2", "platform": "datarobot", "name": "Serverless"}]
    assert pick_serverless_pe(pes)["id"] == "pe2"


def test_pick_serverless_falls_back_to_name():
    pes = [{"id": "pe1", "platform": "aws", "name": "my serverless env"}]
    assert pick_serverless_pe(pes)["id"] == "pe1"


def test_pick_serverless_empty_none():
    assert pick_serverless_pe([]) is None


def test_deploy_payload_shape_and_pe_required():
    body = build_deploy_payload("pkg1", "my-nim", "pe2")
    assert body == {"modelPackageId": "pkg1", "label": "my-nim",
                    "predictionEnvironmentId": "pe2"}
    assert "defaultPredictionServerId" not in body
    with pytest.raises(ValueError):
        build_deploy_payload("pkg1", "my-nim", "")
