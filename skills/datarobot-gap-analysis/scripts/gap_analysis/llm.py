# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pluggable LLM client for Layer-2/4 reasoning.

In the deployed DataRobot agent, the af-component-llm client is injected. For
standalone runs, a litellm-backed client talks to the DataRobot LLM Gateway
(or any provider) when configured via env. When no client is available the
LLM layers are cleanly skipped — the engine still runs Layers 1 and 3.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

try:
    import litellm
except ImportError:  # optional: only standalone runs need it
    litellm = None


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:  # pragma: no cover - interface
        ...


class LiteLLMClient:
    """Standalone client. Reads model + credentials from env.

    Env:
      GAP_LLM_MODEL        model id (default: datarobot/anthropic/claude-sonnet-4-6)
      DATAROBOT_API_TOKEN  + DATAROBOT_ENDPOINT for the DataRobot gateway, or any
      provider key litellm understands.
    """

    def __init__(self, model: str | None = None):
        if litellm is None:
            raise ImportError("litellm is not installed")
        self._litellm = litellm
        self.model = model or os.environ.get(
            "GAP_LLM_MODEL", "datarobot/anthropic/claude-sonnet-4-6"
        )

    def complete(self, system: str, user: str) -> str:
        resp = self._litellm.completion(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=2000,
        )
        return resp["choices"][0]["message"]["content"]


class InjectedClient:
    """Wraps a callable(system, user)->str, e.g. from af-component-llm."""

    def __init__(self, fn):
        self._fn = fn

    def complete(self, system: str, user: str) -> str:
        return self._fn(system, user)


def get_client(injected=None) -> LLMClient | None:
    """Return an LLM client, or None if none is configured/available."""
    if injected is not None:
        return (
            InjectedClient(injected) if not hasattr(injected, "complete") else injected
        )
    if os.environ.get("GAP_DISABLE_LLM"):
        return None
    try:
        return LiteLLMClient()
    except Exception:
        return None


def parse_json(text: str) -> dict[str, Any]:
    """The first JSON object in a model response, ignoring fences and any
    commentary the model appended after the closing brace."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        return json.loads(text)
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
