# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from register_deployment_tool import tag_as_tool, self_hosted_register_url


class _Deployment:
    """Fake mirroring the real SDK: tags read via `.tags`, added via `create_tag`."""

    def __init__(self, tags):
        self.tags = list(tags)
        self.create_tag_calls = []

    def create_tag(self, name, value):
        self.create_tag_calls.append((name, value))
        tag = {"id": f"t{len(self.tags)}", "name": name, "value": value}
        self.tags.append(tag)
        return tag


def _has_tool(tags):
    return any(t["name"] == "tool" and t["value"] == "tool" for t in tags)


def test_tag_added_when_absent():
    dep = _Deployment(tags=[{"id": "t0", "name": "env", "value": "prod"}])
    result = tag_as_tool(dep)
    assert _has_tool(result)
    assert dep.create_tag_calls == [("tool", "tool")]


def test_tag_not_duplicated_when_present():
    dep = _Deployment(tags=[{"id": "t0", "name": "tool", "value": "tool"}])
    result = tag_as_tool(dep)
    assert sum(1 for t in result if t["name"] == "tool" and t["value"] == "tool") == 1
    assert dep.create_tag_calls == []  # idempotent: no create_tag call needed


class _AlreadyTaggedDeployment:
    """Fake where .tags is empty (SDK quirk) but create_tag 409s: already tagged."""

    def __init__(self):
        self.tags = []

    def create_tag(self, name, value):
        err = Exception("The name is already in use for this deployment.")
        err.status_code = 409
        raise err


def test_tag_swallows_409_already_in_use():
    # .tags empty so pre-check misses it; create_tag 409 must be treated as success
    dep = _AlreadyTaggedDeployment()
    result = tag_as_tool(dep)  # must not raise
    assert result == []


def test_self_hosted_register_url_strips_mcp_mount():
    # registeredDeployments is a sibling of the /mcp mount, not a child of it
    url = self_hosted_register_url(
        "https://app.datarobot.com/deployments/dep1/directAccess/mcp/", "dep1"
    )
    assert url == (
        "https://app.datarobot.com/deployments/dep1/directAccess/"
        "registeredDeployments/dep1"
    )


def test_self_hosted_register_url_local():
    url = self_hosted_register_url("http://127.0.0.1:8080/mcp/", "dep1")
    assert url == "http://127.0.0.1:8080/registeredDeployments/dep1"
