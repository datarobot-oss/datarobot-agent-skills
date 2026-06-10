# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Contract test for scripts/wait_for_build.py from the datarobot-workload-api skill.

The real-world bug: agents that treated `BUILT` as terminal-success ended up
scheduling workloads before the image was pushed to the registry, getting
HTTP 422 `runtime_image_uri ... None`.  `wait_for_build.py` must:

  - Keep polling on `BUILT` (image built locally, not yet pushed)
  - Keep polling on `PENDING` / `IN_PROGRESS` / `in-progress`
  - Exit success ONLY on `COMPLETED` / `completed`
  - Exit failure on `FAILED` / `failed`

Status comparison happens via `.upper()` normalization in the script, so both
lowercase (C2W) and uppercase (image-first) variants must work.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills/datarobot-workload-api/scripts/wait_for_build.py"
)


@pytest.fixture(scope="module")
def wait_for_build_module() -> Any:
    """Load the script as a module so we can call its functions directly."""
    spec = importlib.util.spec_from_file_location("_wfb", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_wfb"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeResponse:
    """Minimal stand-in for an httpx.Response with the surface wait_for_build uses."""

    def __init__(self, json_body: dict[str, Any] | None = None, text: str = "") -> None:
        self._json = json_body or {}
        self.text = text or str(json_body)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._json


def _make_httpx_get(
    status_sequence: list[str], logs_text: str = "build log lines"
) -> Any:
    """Returns an httpx.get stub that returns each status from the sequence in order.

    Falls through to a logs response after the build endpoint is exhausted, so the
    FAILED path (which fetches /logs/) doesn't trip on an empty queue.
    """
    statuses = iter(status_sequence)

    def fake_get(url: str, *_args: Any, **_kwargs: Any) -> _FakeResponse:
        if url.endswith("/logs/"):
            return _FakeResponse(text=logs_text)
        try:
            status = next(statuses)
        except StopIteration:
            pytest.fail(f"httpx.get called more times than expected (url={url})")
        return _FakeResponse({"status": status})

    return fake_get


def test_completed_uppercase_terminates_successfully(
    wait_for_build_module: Any,
) -> None:
    """COMPLETED (uppercase, image-first style) exits success on the first poll."""
    with (
        patch.object(wait_for_build_module, "httpx") as mock_httpx,
        patch.object(wait_for_build_module.time, "sleep"),
    ):
        mock_httpx.get = _make_httpx_get(["COMPLETED"])
        result = wait_for_build_module.wait_for_build(
            "base", {"h": "v"}, "art-1", "build-1", timeout=60, interval=1
        )
    assert result["status"] == "COMPLETED"


def test_completed_lowercase_terminates_successfully(
    wait_for_build_module: Any,
) -> None:
    """`completed` (lowercase, C2W flow) is normalized to uppercase and exits success."""
    with (
        patch.object(wait_for_build_module, "httpx") as mock_httpx,
        patch.object(wait_for_build_module.time, "sleep"),
    ):
        mock_httpx.get = _make_httpx_get(["completed"])
        result = wait_for_build_module.wait_for_build(
            "base", {"h": "v"}, "art-2", "build-2", timeout=60, interval=1
        )
    assert (result.get("status") or "").upper() == "COMPLETED"


def test_built_keeps_polling_until_completed(wait_for_build_module: Any) -> None:
    """BUILT must NOT be treated as terminal success — image is not yet pushed.
    The script must continue polling until COMPLETED."""
    with (
        patch.object(wait_for_build_module, "httpx") as mock_httpx,
        patch.object(wait_for_build_module.time, "sleep"),
    ):
        mock_httpx.get = _make_httpx_get(["IN_PROGRESS", "BUILT", "BUILT", "COMPLETED"])
        result = wait_for_build_module.wait_for_build(
            "base", {"h": "v"}, "art-3", "build-3", timeout=60, interval=1
        )
    assert result["status"] == "COMPLETED", (
        "BUILT must be treated as intermediate, not terminal — the image hasn't been pushed yet. "
        "If this test fails, scripts/wait_for_build.py likely treats BUILT as terminal success, "
        "which causes the field bug Slack reported: workload create returns "
        "`422 runtime_image_uri ... None` because the registry can't resolve the imageUri."
    )


def test_failed_raises_runtime_error(wait_for_build_module: Any) -> None:
    """FAILED triggers a RuntimeError so the CLI exits with code 2."""
    with (
        patch.object(wait_for_build_module, "httpx") as mock_httpx,
        patch.object(wait_for_build_module.time, "sleep"),
    ):
        mock_httpx.get = _make_httpx_get(["IN_PROGRESS", "FAILED"], logs_text="boom")
        with pytest.raises(RuntimeError, match="FAILED"):
            wait_for_build_module.wait_for_build(
                "base", {"h": "v"}, "art-4", "build-4", timeout=60, interval=1
            )


def test_failed_lowercase_raises_runtime_error(wait_for_build_module: Any) -> None:
    """C2W's lowercase `failed` is normalized to uppercase and raises the same way."""
    with (
        patch.object(wait_for_build_module, "httpx") as mock_httpx,
        patch.object(wait_for_build_module.time, "sleep"),
    ):
        mock_httpx.get = _make_httpx_get(["in-progress", "failed"], logs_text="boom")
        with pytest.raises(RuntimeError, match="FAILED"):
            wait_for_build_module.wait_for_build(
                "base", {"h": "v"}, "art-5", "build-5", timeout=60, interval=1
            )


def test_success_set_contains_only_completed(wait_for_build_module: Any) -> None:
    """The SUCCESS set must contain COMPLETED and NOT contain BUILT.
    Direct test against the module constant — the most direct regression check
    against the BUILT-vs-COMPLETED confusion that caused the field bug."""
    assert "COMPLETED" in wait_for_build_module.SUCCESS
    assert "BUILT" not in wait_for_build_module.SUCCESS, (
        "SUCCESS must not include BUILT. BUILT means the image is built locally but "
        "NOT yet pushed to the registry — workloads scheduled on a BUILT artifact get "
        "`422 runtime_image_uri ... None`. Only COMPLETED is deployable."
    )
