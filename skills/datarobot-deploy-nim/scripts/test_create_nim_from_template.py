# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest
from create_nim_from_template import build_nim_create_payload


def test_minimal_payload():
    body = build_nim_create_payload("tpl1", "bundleG")
    assert body == {"templateId": "tpl1", "resourceBundleId": "bundleG"}


def test_optional_fields_included_when_set():
    body = build_nim_create_payload(
        "tpl1", "bundleG", secret_config_id="sec1", container_tag_override="latest"
    )
    assert body["secretConfigId"] == "sec1"
    assert body["nimContainerTagOverride"] == "latest"


def test_requires_template_and_bundle():
    with pytest.raises(ValueError):
        build_nim_create_payload("", "bundleG")
    with pytest.raises(ValueError):
        build_nim_create_payload("tpl1", "")


def test_optional_fields_omitted_when_none():
    body = build_nim_create_payload("tpl1", "bundleG")
    assert "secretConfigId" not in body
    assert "nimContainerTagOverride" not in body
