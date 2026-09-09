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


def config_content(efforts: Mapping[str, str], base: str | None = None) -> str:
    """OPENCODE_CONFIG_CONTENT JSON setting `options.reasoningEffort` per
    `provider/model` id, merged over any JSON already in `base`."""
    try:
        config = json.loads(base) if base else {}
    except ValueError:
        config = {}
    if not isinstance(config, dict):
        config = {}
    providers = config.setdefault("provider", {})
    for model, effort in efforts.items():
        provider, name = _split(model)
        if not provider or not name or not effort:
            continue
        entry = (
            providers.setdefault(provider, {})
            .setdefault("models", {})
            .setdefault(name, {})
        )
        entry.setdefault("options", {})["reasoningEffort"] = effort
    return json.dumps(config)


def worker_env(
    models: Iterable[str],
    setting: str | None,
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """(environment for an opencode process, {model: effort} it will apply).

    The environment is a copy of `env` (default: the current process) with
    OPENCODE_CONFIG_CONTENT set for every model that gets an effort; models
    without one are left alone so the request stays valid.
    """
    base = dict(env if env is not None else os.environ)
    efforts = {
        m: e for m in models for e in [resolve_effort(m, setting)] if e is not None
    }
    if efforts:
        base[CONFIG_ENV] = config_content(efforts, base.get(CONFIG_ENV))
    return base, efforts
