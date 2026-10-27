# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parsing of the `dr opencode run --format json` JSONL event stream.

opencode 1.x and 2.x write the same envelope (`type`, `timestamp`,
`sessionID`) and the same `text` and `step_finish` parts. They differ in the
`error` event, and 2.x usually ends the stream before its `step_finish`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator


def _obj(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _events(stdout: str) -> Iterator[dict[str, object]]:
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            yield event


def usage_meta(items: Iterable[object]) -> dict[str, object]:
    """Token meta summed over objects that carry `tokens` and `cost`.

    A `step_finish` part and an opencode 2.x assistant message both have that
    shape, with `tokens` as {input, output, reasoning, cache: {read, write}}.
    """
    input_tokens = output_tokens = cache_read = cache_write = reasoning = 0
    cost = 0.0
    for item in items:
        obj = _obj(item)
        tokens = _obj(obj.get("tokens"))
        cache = _obj(tokens.get("cache"))
        input_tokens += _int(tokens.get("input"))
        output_tokens += _int(tokens.get("output"))
        cache_read += _int(cache.get("read"))
        cache_write += _int(cache.get("write"))
        reasoning += _int(tokens.get("reasoning"))
        cost += _float(obj.get("cost"))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "reasoning_tokens": reasoning,
        "cost": round(cost, 6),
    }


def _error_message(error: object) -> str:
    # opencode 2.x sends {type, message}; 1.x sends {name, data: {message}}.
    err = _obj(error)
    for value in (err.get("message"), _obj(err.get("data")).get("message")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    name = err.get("name")
    return name.strip() if isinstance(name, str) else ""


def stream_error(stdout: str) -> str:
    """The messages of the `error` events in an event stream, joined."""
    messages = (
        _error_message(event.get("error"))
        for event in _events(stdout)
        if event.get("type") == "error"
    )
    return "; ".join(m for m in messages if m)


def session_id(stdout: str) -> str | None:
    """The opencode session an event stream belongs to."""
    for event in _events(stdout):
        value = event.get("sessionID")
        if isinstance(value, str) and value:
            return value
    return None


def parse_events(stdout: str) -> tuple[str, dict[str, object]]:
    """Return (text, token_meta) from an opencode JSONL event stream.

    The stream emits one event per line: `text` events carry chunks of the
    assistant response, `step_finish` events carry token counts and cost.
    Raises ValueError when the stream contains no text at all (the session
    died, answered exclusively with tool calls, or opencode reported an error).
    """
    parts: list[str] = []
    steps: list[dict[str, object]] = []
    finish = ""
    for event in _events(stdout):
        part = _obj(event.get("part"))
        if event.get("type") == "text":
            chunk = part.get("text")
            if isinstance(chunk, str) and chunk:
                parts.append(chunk)
        elif event.get("type") == "step_finish":
            steps.append(part)
            finish = str(part.get("reason") or finish)

    meta = usage_meta(steps)
    text = "".join(parts).strip()
    if not text:
        if finish == "length":
            raise ValueError(
                "the model's reply was cut at its max output tokens before any "
                f"text was emitted ({meta['output_tokens']} output tokens, "
                f"{meta['reasoning_tokens']} of them reasoning); raise the "
                "model's output limit"
            )
        error = stream_error(stdout)
        if error:
            raise ValueError(f"opencode reported an error: {error}")
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
