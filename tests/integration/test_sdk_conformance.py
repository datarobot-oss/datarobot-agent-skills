# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Gate DataRobot SDK calls in skills against the installed SDK.

Skills document python that agents copy verbatim, but nothing else in this repo
imports ``datarobot``.  A call to a method that does not exist, or one with the
wrong arguments, is therefore invisible to ruff, to mypy (which is configured
with ``ignore_missing_imports``), and to the SKILL.md prose judge alike.
"""

from pathlib import Path

import datarobot as dr
import pytest
from sdk_conformance import analyse_skill, skill_dirs


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "skill_dir" in metafunc.fixturenames:
        dirs = skill_dirs()
        metafunc.parametrize("skill_dir", dirs, ids=[d.name for d in dirs])


def test_sdk_calls_match_installed_sdk(skill_dir: Path) -> None:
    """Every DataRobot SDK call in the skill must exist and take these arguments."""
    findings = analyse_skill(skill_dir)
    if findings:
        # pytest.fail rather than assert: the dataclass repr that assertion
        # introspection appends buries the readable list.
        pytest.fail(
            f"{len(findings)} DataRobot SDK violation(s) in '{skill_dir.name}' "
            f"(datarobot {dr.__version__}):\n  "
            + "\n  ".join(str(f) for f in findings),
            pytrace=False,
        )
