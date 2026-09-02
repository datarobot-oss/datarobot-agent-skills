#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / (
    "skills/datarobot-agent-assist/agent-assist-build/scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

from rehearsal import (  # noqa: E402
    DONE_HINT,
    TURN_DECORATION,
    capture_output,
    print_init_banner,
    print_turn_footer,
    print_turn_header,
)


def _read_captured(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_init_banner_includes_turn_footer(tmp_path: Path) -> None:
    session_dir = str(tmp_path / "session")
    Path(session_dir).mkdir()

    with capture_output(session_dir) as output_path:
        print_init_banner(["Model: test-model", "Tools (0):", "  (none)"])

    content = _read_captured(output_path)
    assert content.count(TURN_DECORATION) >= 2
    assert "Type your next message to continue." in content
    assert "Use NOTE: <text> to record a design observation." in content
    assert DONE_HINT in content


def test_turn_footer_lines() -> None:
    session_dir = Path("/tmp/rehearsal-format-test")
    session_dir.mkdir(exist_ok=True)

    with capture_output(str(session_dir)) as output_path:
        print_turn_header()
        print("[You]: hello")
        print()
        print("[Agent]: hi there")
        print_turn_footer()

    content = _read_captured(output_path)
    assert content.count(TURN_DECORATION) == 2
    assert content.strip().endswith(DONE_HINT)
