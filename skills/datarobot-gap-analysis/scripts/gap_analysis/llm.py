# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""LLM client protocol for Layer-2/4 reasoning.

The CLI builds an opencode-backed client (see opencode.py) and passes it in; an
embedding may inject any callable(system, user) -> str. There is no standalone
fallback: without the DataRobot CLI the LLM layers are skipped and the report
says so.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from .settings import DEFAULTS, Settings


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        ...


class InjectedClient:
    """Wraps a callable(system, user)->str, e.g. from af-component-llm."""

    def __init__(self, fn: Callable[[str, str], str]):
        self._fn = fn

    def complete(self, system: str, user: str) -> str:
        return str(self._fn(system, user))


def get_client(
    injected: LLMClient | Callable[[str, str], str] | None = None,
    settings: Settings = DEFAULTS,
) -> LLMClient | None:
    """Return an LLM client, or None if none is configured/available."""
    del settings  # the CLI decides the backend; nothing is auto-detected here
    if injected is not None:
        if hasattr(injected, "complete"):
            return injected  # type: ignore[return-value]
        return InjectedClient(injected)  # type: ignore[arg-type]
    return None


def parse_json(text: str) -> dict[str, Any]:
    """The first JSON object in a model response, ignoring fences and any
    commentary the model appended after the closing brace."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError("model response is not a JSON object")
        return loaded
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise
        obj, _end = json.JSONDecoder().raw_decode(text[start:])
        if not isinstance(obj, dict):
            raise ValueError("model response is not a JSON object")
        return obj


def brief_error(e: BaseException, limit: int = 300) -> str:
    """One line of an exception message, capped, for skip reasons and notes."""
    text = " ".join(str(e).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
