# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Validate that every skill in skills/ has a corresponding entry in docs/.well-known/ai-catalog.json.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
CATALOG_PATH = REPO_ROOT / "docs" / ".well-known" / "ai-catalog.json"


def skill_names() -> list[str]:
    return [
        item.name
        for item in SKILLS_DIR.iterdir()
        if item.is_dir() and (item / "SKILL.md").exists()
    ]


def catalog_display_names() -> list[str]:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    return [entry["displayName"] for entry in catalog.get("entries", [])]


def test_catalog_exists() -> None:
    assert CATALOG_PATH.exists(), f"AI catalog not found at {CATALOG_PATH}"


def test_catalog_is_valid_json() -> None:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    assert "entries" in catalog, "Catalog is missing 'entries' key"


def test_every_skill_has_catalog_entry() -> None:
    skills = skill_names()
    cataloged = catalog_display_names()
    missing = [s for s in skills if s not in cataloged]
    assert not missing, (
        "The following skills are missing from docs/.well-known/ai-catalog.json:\n"
        + "\n".join(f"  - {s}" for s in missing)
    )


def test_no_stale_catalog_entries() -> None:
    skills = set(skill_names())
    cataloged = catalog_display_names()
    stale = [c for c in cataloged if c not in skills]
    assert not stale, (
        "The following catalog entries have no matching skill folder:\n"
        + "\n".join(f"  - {s}" for s in stale)
    )
