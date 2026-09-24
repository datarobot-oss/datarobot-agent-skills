# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reasoning effort for models served through the DataRobot LLM Gateway.

The gateway forwards the OpenAI-style `reasoning_effort` parameter, but the
values each provider accepts differ, and a wrong value fails the request.
Opencode adds the parameter when the model's config carries
`options.reasoningEffort`, which can be injected for a single run through
the `OPENCODE_CONFIG_CONTENT` environment variable without touching the
user's config file.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping

CONFIG_ENV = "OPENCODE_CONFIG_CONTENT"
MAX = "max"
OFF = "off"

# Highest effort each family accepted on the gateway (checked against
# app.datarobot.com). Order matters: the first match wins.
_FAMILY_MAX: list[tuple[re.Pattern[str], str | None]] = [
    (re.compile(r"claude.*haiku", re.I), "high"),  # "max" exceeds the 8k token cap
    (re.compile(r"claude[-.]?(sonnet|opus)[-.]?4|claude-4", re.I), "max"),
    (re.compile(r"gpt-5.*codex", re.I), None),  # rejects reasoning_effort
    (re.compile(r"azure/gpt-5|/o[1-9](-|$)|/gpt-5", re.I), "xhigh"),
    (re.compile(r"gpt-oss", re.I), "high"),
    (re.compile(r"gemini-(2\.5|3)", re.I), "high"),
]


# Output-token ceilings the gateway-served families actually support. The DataRobot
# opencode config declares 8k for every model, and with reasoning enabled the
# thinking counts against that, so a long JSON reply is cut mid-string.
_FAMILY_LIMIT: list[tuple[re.Pattern[str], tuple[int, int]]] = [
    (re.compile(r"claude", re.I), (200_000, 64_000)),
    (re.compile(r"gpt-5|/o[1-9](-|$)", re.I), (400_000, 128_000)),
    (re.compile(r"gemini-(2\.5|3)", re.I), (1_000_000, 65_536)),
    (re.compile(r"gpt-oss", re.I), (128_000, 32_000)),
]


def token_limits(model: str) -> tuple[int, int] | None:
    """(context, output) token limits to declare for `model`, or None to leave
    the provider's own declaration alone."""
    for pattern, limits in _FAMILY_LIMIT:
        if pattern.search(model):
            return limits
    return None


def max_reasoning_effort(model: str) -> str | None:
    """The highest reasoning effort the gateway accepts for `model`, or None
    when the model has no reasoning mode worth requesting."""
    for pattern, effort in _FAMILY_MAX:
        if pattern.search(model):
            return effort
    return None


def resolve_effort(model: str, setting: str | None) -> str | None:
    """Turn a user setting into the value to send: None or "off" sends nothing,
    "max" picks the family maximum, anything else is sent verbatim."""
    if not setting or setting.lower() == OFF:
        return None
    if setting.lower() == MAX:
        return max_reasoning_effort(model)
    return setting


def _split(model: str) -> tuple[str, str]:
    provider, _, rest = model.partition("/")
    return provider, rest


def config_content(
    efforts: Mapping[str, str],
    base: str | None = None,
    limits: Mapping[str, tuple[int, int]] | None = None,
) -> str:
    """OPENCODE_CONFIG_CONTENT JSON setting `options.reasoningEffort` and
    `limit` per `provider/model` id, merged over any JSON already in `base`."""
    try:
        config = json.loads(base) if base else {}
    except ValueError:
        config = {}
    if not isinstance(config, dict):
        config = {}
    providers = config.setdefault("provider", {})

    def entry_for(model: str) -> dict[str, object] | None:
        provider, name = _split(model)
        if not provider or not name:
            return None
        models = providers.setdefault(provider, {}).setdefault("models", {})
        item: dict[str, object] = models.setdefault(name, {})
        return item

    for model, effort in efforts.items():
        entry = entry_for(model) if effort else None
        if entry is not None:
            options = entry.setdefault("options", {})
            if isinstance(options, dict):
                options["reasoningEffort"] = effort
    for model, (context, output) in (limits or {}).items():
        entry = entry_for(model)
        if entry is not None:
            entry["limit"] = {"context": context, "output": output}
    return json.dumps(config)


def worker_env(
    models: Iterable[str],
    setting: str | None,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """(environment for an opencode process, {model: effort} it will apply).

    The environment is a copy of `env` (default: the current process) with
    OPENCODE_CONFIG_CONTENT setting the reasoning effort and the output-token
    limit for every model that gets one; models without either are left alone
    so the request stays valid.
    """
    base = dict(env if env is not None else os.environ)
    models = list(models)
    efforts = {
        m: e for m in models for e in [resolve_effort(m, setting)] if e is not None
    }
    limits = {m: lim for m in models for lim in [token_limits(m)] if lim is not None}
    if efforts or limits:
        base[CONFIG_ENV] = config_content(efforts, base.get(CONFIG_ENV), limits)
    return base, efforts
