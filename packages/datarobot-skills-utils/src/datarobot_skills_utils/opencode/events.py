# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parsing of the `dr opencode run --format json` JSONL event stream."""

from __future__ import annotations

import json


def _obj(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def parse_events(stdout: str) -> tuple[str, dict[str, object]]:
    """Return (text, token_meta) from an opencode JSONL event stream.

    The stream emits one event per line: `text` events carry chunks of the
    assistant response, `step_finish` events carry token counts and cost.
    Raises ValueError when the stream contains no text at all (the session
    died or answered exclusively with tool calls).
    """
    parts: list[str] = []
    input_tokens = output_tokens = cache_read = cache_write = reasoning = 0
    cost = 0.0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        part = _obj(event.get("part"))
        if event.get("type") == "text":
            chunk = part.get("text")
            if isinstance(chunk, str) and chunk:
                parts.append(chunk)
        elif event.get("type") == "step_finish":
            tokens = _obj(part.get("tokens"))
            cache = _obj(tokens.get("cache"))
            input_tokens += _int(tokens.get("input"))
            output_tokens += _int(tokens.get("output"))
            cache_read += _int(cache.get("read"))
            cache_write += _int(cache.get("write"))
            reasoning += _int(tokens.get("reasoning"))
            cost += _float(part.get("cost"))

    meta: dict[str, object] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": reasoning,
        "cost": round(cost, 6),
    }
    text = "".join(parts).strip()
    if not text:
        raise ValueError("no text events found in opencode output")
    return text, meta


def strip_code_fences(text: str) -> str:
    """Unwrap a response fenced as ```...```; raises on an empty fence."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    inner = inner.strip()
    if not inner:
        raise ValueError("worker returned an empty code block")
    return inner
