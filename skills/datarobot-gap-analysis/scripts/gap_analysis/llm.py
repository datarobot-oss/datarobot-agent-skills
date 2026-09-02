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
import re
from typing import Any, Protocol


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
        import litellm  # noqa: F401  (import-time check)

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


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if m:
            return json.loads(m.group(0))
        raise
