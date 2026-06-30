# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from check_tool_gallery_flag import is_tool_gallery_enabled


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, value):
        self._value = value
        self.last = None

    def post(self, url, data=None, **kwargs):
        self.last = (url, data)
        return _Resp({"entitlements": [{"name": "ENABLE_MCP_TOOLS_GALLERY_SUPPORT",
                                        "value": self._value}]})


def test_returns_true_when_entitled():
    assert is_tool_gallery_enabled(_Client(True)) is True


def test_returns_false_when_not_entitled():
    assert is_tool_gallery_enabled(_Client(False)) is False


def test_posts_to_entitlements_evaluate():
    c = _Client(True)
    is_tool_gallery_enabled(c)
    url, data = c.last
    assert "entitlements/evaluate" in url
    assert "ENABLE_MCP_TOOLS_GALLERY_SUPPORT" in str(data)
