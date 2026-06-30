# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from register_deployment_tool import tag_as_tool, self_hosted_register_url


class _Deployment:
    def __init__(self, tags):
        self.tags = tags
        self.updated_with = None

    def update(self, tags=None):
        self.updated_with = tags


def test_tag_added_when_absent():
    dep = _Deployment(tags=[{"name": "env", "value": "prod"}])
    result = tag_as_tool(dep)
    assert {"name": "tool", "value": "tool"} in result
    assert dep.updated_with == result


def test_tag_not_duplicated_when_present():
    dep = _Deployment(tags=[{"name": "tool", "value": "tool"}])
    result = tag_as_tool(dep)
    assert result.count({"name": "tool", "value": "tool"}) == 1
    assert dep.updated_with is None  # no update needed


def test_self_hosted_register_url():
    url = self_hosted_register_url(
        "https://app.datarobot.com/deployments/dep1/directAccess/mcp/", "dep1")
    assert url == ("https://app.datarobot.com/deployments/dep1/directAccess/mcp/"
                   "registeredDeployments/dep1")
