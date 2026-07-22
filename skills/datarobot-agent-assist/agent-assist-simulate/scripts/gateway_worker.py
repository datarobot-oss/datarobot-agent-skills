#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Thin LLMGateway worker adapter.

Invokes `dr opencode run` in an isolated temporary directory, parses the
JSONL event stream, and writes the extracted JSON object to response_path.
The adapter retries transient OpenCode database-lock failures. Authentication
and response-contract retries are owned by the caller (SKILL.md).
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# One project-local log for swarm and convergence workers (relative to agent cwd).
METRICS_PATH = Path(".datarobot/swarm/metrics.jsonl")
PROMPT_ROLE_MAP = {
    "generate-attack.md": "generator/attack",
    "generate-behavior.md": "generator/behavior",
    "generate-persistence.md": "generator/persistence",
    "run-scenario.md": "runner",
    "generate-tool-return.md": "fixture",
    "evaluate-result.md": "evaluator",
    "generate-fix.md": "fixer",
    "diagnose-failure.md": "diagnoser",
}


def _build_message(role_prompt_path: Path, input_path: Path) -> str:
    role_prompt = role_prompt_path.read_text(encoding="utf-8")
    input_json = input_path.read_text(encoding="utf-8")
    return f"{role_prompt}\n\n# Input\n\n{input_json}"


def _extract_response(stdout: str, role: str = "") -> dict[str, object]:
    """Parse JSONL event stream and return the assistant's JSON object.

    opencode --format json emits one event per line:
      {"type":"step_start", "part": {...}}
      {"type":"text",       "part": {"text": "<assistant response>", ...}}
      {"type":"step_finish","part": {...}}

    Concatenate all type=="text" part.text payloads, then parse as JSON.

    For the runner role only, a plain-prose reply (the simulation model declining
    the framing instead of emitting the envelope) is wrapped as an
    `assistant_response` rather than raised as a failure: prose from the simulated
    agent is behaviorally a refusal and should be scored, not discarded.
    """
    text_parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "text":
            chunk = event.get("part", {}).get("text", "")
            if chunk:
                text_parts.append(chunk)

    combined = "".join(text_parts).strip()
    if not combined:
        raise ValueError("no text events found in opencode output")

    if combined.startswith("```"):
        lines = combined.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        combined = inner.strip()
        if not combined:
            raise ValueError("worker returned an empty code block")

    try:
        result = json.loads(combined)
    except json.JSONDecodeError as exc:
        if role == "runner":
            return {"type": "assistant_response", "content": combined}
        raise ValueError(f"worker response is not valid JSON: {exc}") from exc

    if not isinstance(result, dict):
        if role == "runner":
            return {"type": "assistant_response", "content": combined}
        raise ValueError(
            f"expected a JSON object from worker, got {type(result).__name__}"
        )

    return result


def _atomic_write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _scenario_id_from_input(input_path: Path) -> str | None:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    scenario_id = data.get("scenario_id")
    if isinstance(scenario_id, str) and scenario_id:
        return scenario_id
    scenario = data.get("scenario")
    if isinstance(scenario, dict):
        nested_id = scenario.get("scenario_id")
        if isinstance(nested_id, str) and nested_id:
            return nested_id
    breached = data.get("breached_scenarios")
    if isinstance(breached, list) and breached:
        first = breached[0]
        if isinstance(first, dict):
            cluster_id = first.get("scenario_id")
            if isinstance(cluster_id, str) and cluster_id:
                return cluster_id
    return None


def _write_metrics(record: dict[str, object]) -> None:
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with METRICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--role-prompt",
        required=True,
        type=str,
        help="prompt name (e.g. 'generate-attack') or path to a role prompt markdown file",
    )
    parser.add_argument(
        "--input-path",
        required=True,
        type=Path,
        help="path to the worker input JSON package",
    )
    parser.add_argument(
        "--response-path",
        required=True,
        type=Path,
        help="path where extracted JSON response will be written",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="LLMGateway model ID (e.g. datarobot/anthropic/claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--rejection-note",
        default=None,
        help="rejection reason to append to message on retry",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="subprocess timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--server-url",
        default=None,
        help="URL of a running `dr opencode serve` instance (e.g. http://127.0.0.1:4096). "
        "When set, workers attach to it instead of spawning their own process, "
        "eliminating SQLite DB lock contention at high parallelism.",
    )
    args = parser.parse_args()

    role_prompt_path = Path(args.role_prompt)
    if not role_prompt_path.is_file():
        candidate = Path(__file__).parent.parent / "prompts" / args.role_prompt
        if not candidate.suffix:
            candidate = candidate.with_suffix(".md")
        role_prompt_path = candidate
    if not role_prompt_path.is_file():
        print(f"--role-prompt: file not found: {args.role_prompt}", file=sys.stderr)
        sys.exit(1)
    args.role_prompt = role_prompt_path

    if not args.input_path.is_file():
        print(f"--input-path: file not found: {args.input_path}", file=sys.stderr)
        sys.exit(1)

    role = PROMPT_ROLE_MAP.get(args.role_prompt.name, args.role_prompt.stem)
    scenario_id = _scenario_id_from_input(args.input_path)
    message = _build_message(args.role_prompt, args.input_path)
    if args.rejection_note:
        message += (
            f"\n\nYour previous response was rejected: {args.rejection_note}."
            " Correct the response and try again."
        )
    # When attaching to a server, each call creates its own session on the server —
    # no isolated tmpdir needed. Without attach, an isolated dir prevents the
    # subprocess from picking up the project's own opencode config as context.
    isolated_dir = None if args.server_url else tempfile.mkdtemp(prefix="dr-worker-")
    start = time.monotonic()
    success = False
    error: str | None = None

    try:
        cmd = [
            "dr",
            "--skip-plugin-update-check",
            "--plugin-discovery-timeout",
            "30s",
            "opencode",
            "run",
            "--format",
            "json",
            "--model",
            args.model,
        ]
        if args.server_url:
            cmd += ["--attach", args.server_url]
        else:
            cmd += ["--dir", isolated_dir]
        cmd += ["--pure", message]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=args.timeout
            )
        except subprocess.TimeoutExpired:
            error = "timeout"
            print(
                f"worker timed out after {args.timeout}s "
                f"(role-prompt: {args.role_prompt.name})",
                file=sys.stderr,
            )
            sys.exit(1)

        if result.returncode != 0:
            error = f"opencode_exit_{result.returncode}"
            print(
                f"dr opencode run exited {result.returncode}:\n"
                f"{result.stderr or result.stdout}",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            response = _extract_response(result.stdout, role)
        except ValueError as exc:
            error = "parse_failed"
            print(f"response extraction failed: {exc}", file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            sys.exit(1)

        _atomic_write(args.response_path, response)
        success = True

    finally:
        if isolated_dir:
            shutil.rmtree(isolated_dir, ignore_errors=True)
        record: dict[str, object] = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "role": role,
            "run_dir": str(args.response_path.parent),
            "model": args.model,
            "duration_s": round(time.monotonic() - start, 2),
            "success": success,
        }
        if scenario_id is not None:
            record["scenario_id"] = scenario_id
        if error is not None:
            record["error"] = error
        _write_metrics(record)


if __name__ == "__main__":
    main()
