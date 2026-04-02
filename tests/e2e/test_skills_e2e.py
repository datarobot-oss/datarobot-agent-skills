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
from dr_agents_tester.pytest_plugin import make_skill_e2e_test

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

pytest_generate_tests, test_skill_quality, _hash_store = make_skill_e2e_test(
    skills_dir=Path(__file__).resolve().parents[2] / "skills",
    hash_file=Path(__file__).resolve().parent / "skill_hashes.json",
)
