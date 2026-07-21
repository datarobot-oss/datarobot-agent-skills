# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from typing import Any
from check_tool_gallery_flag import is_tool_gallery_enabled


class _Resp:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _Client:
    def __init__(self, value: bool | str) -> None:
        self._value = value
        self.last: tuple[str, Any] | None = None

    def post(self, url: str, data: Any = None, **kwargs: Any) -> _Resp:
        self.last = (url, data)
        return _Resp(
            {
                "entitlements": [
                    {"name": "ENABLE_MCP_TOOLS_GALLERY_SUPPORT", "value": self._value}
                ]
            }
        )


def test_returns_true_when_entitled() -> None:
    assert is_tool_gallery_enabled(_Client(True)) is True


def test_returns_false_when_not_entitled() -> None:
    assert is_tool_gallery_enabled(_Client(False)) is False


def test_posts_to_entitlements_evaluate() -> None:
    c = _Client(True)
    is_tool_gallery_enabled(c)
    assert c.last is not None
    url, data = c.last
    assert "entitlements/evaluate" in url
    assert "ENABLE_MCP_TOOLS_GALLERY_SUPPORT" in str(data)


def test_returns_true_when_string_value_is_true() -> None:
    assert is_tool_gallery_enabled(_Client("true")) is True


def test_returns_false_when_string_value_is_false() -> None:
    assert is_tool_gallery_enabled(_Client("false")) is False
