# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""End-to-end quality tests for DataRobot agent skills.

Each SKILL.md is evaluated by an LLM judge that checks whether an agent
following the skill would produce coherent, complete results.  Unchanged
skills are skipped via an MD5 hash cache so CI only pays for what changed.

Run locally::

    cp .env.example .env  # fill in DATAROBOT_ENDPOINT + DATAROBOT_API_TOKEN
    uv run --group e2e pytest tests/e2e/ -v

Force-evaluate every skill regardless of hash cache::

    SKILLS_E2E_FORCE_ALL=1 uv run --group e2e pytest tests/e2e/ -v
"""

from pathlib import Path

from dotenv import load_dotenv
from dr_agents_tester import pytest_plugin
from dr_agents_tester.pytest_plugin import make_skill_e2e_test
from skill_verdict import parse_verdict

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

# The plugin's own parser reports a false INCOMPLETE when the judge writes
# `## Overall Verdict`. verdict_passes() looks the name up at call time, so
# replacing it here fixes the gate until the upstream fix is released.
pytest_plugin.parse_verdict = parse_verdict

pytest_generate_tests, test_skill_quality, _hash_store = make_skill_e2e_test(
    skills_dir=Path(__file__).resolve().parents[2] / "skills",
    hash_file=Path(__file__).resolve().parent / "skill_hashes.json",
)
