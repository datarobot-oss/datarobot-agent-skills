# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for integration tests."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "skills/datarobot-agent-assist/agent-assist-build/scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

from agent_assist_contracts import (  # noqa: E402
    map_deployed_listing,
    map_gateway_listing,
)


@pytest.fixture(scope="session")
def list_llm_models() -> Any:
    return importlib.import_module("list_llm_models")


@pytest.fixture(scope="session")
def setup_template() -> Any:
    return importlib.import_module("setup_template")


@pytest.fixture(scope="session")
def rehearsal() -> Any:
    return importlib.import_module("rehearsal")


@pytest.fixture
def gateway_listing(list_llm_models: Any) -> dict[str, Any]:
    return map_gateway_listing(list_llm_models)


@pytest.fixture
def deployed_listing(list_llm_models: Any) -> dict[str, Any]:
    return map_deployed_listing(list_llm_models)
