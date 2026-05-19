"""
Validate DataRobot skill folders:
1. All skill folders must start with 'datarobot-'
2. Each skill folder must have a SKILL.md file
3. The 'name' field in SKILL.md frontmatter must match the folder name
"""

from pathlib import Path

import frontmatter
import pytest
from datarobot_genai.core.utils.token_tracking import estimate_tokens

REPO_ROOT = Path(__file__).parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"


def skill_dirs() -> list[Path]:
    return [
        item
        for item in SKILLS_DIR.iterdir()
        if item.is_dir() and (item / "SKILL.md").exists()
    ]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "skill_dir" in metafunc.fixturenames:
        dirs = skill_dirs()
        metafunc.parametrize("skill_dir", dirs, ids=[d.name for d in dirs])


def test_skills_dir_exists() -> None:
    assert SKILLS_DIR.exists(), "skills/ directory not found"


def test_at_least_one_skill() -> None:
    assert skill_dirs(), "No skill folders with SKILL.md found in skills/"


def test_skill_folder_naming(skill_dir: Path) -> None:
    assert skill_dir.name.startswith("datarobot-"), (
        f"Skill folder '{skill_dir.name}' does not start with 'datarobot-'"
    )


def test_skill_frontmatter_has_name(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    with open(skill_md, encoding="utf-8") as f:
        post = frontmatter.load(f)
    assert post.metadata.get("name"), (
        f"Skill '{skill_dir.name}/SKILL.md' is missing 'name' field in frontmatter"
    )


def test_skill_frontmatter_name_matches_folder(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    with open(skill_md, encoding="utf-8") as f:
        post = frontmatter.load(f)
    skill_name = post.metadata.get("name", "")
    assert skill_name == skill_dir.name, (
        f"Skill '{skill_dir.name}' has mismatched name in SKILL.md: "
        f"expected '{skill_dir.name}', got '{skill_name}'"
    )


def test_skill_frontmatter_description_has_use_when(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    with open(skill_md, encoding="utf-8") as f:
        post = frontmatter.load(f)
    description = post.metadata.get("description", "")
    assert "Use when" in description, (
        f"Skill '{skill_dir.name}/SKILL.md' description must contain 'Use when'"
    )


def test_skill_context_window_warn(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    tokens = estimate_tokens(content)
    assert tokens <= 2500, (
        f"Skill '{skill_dir.name}/SKILL.md' estimated token count ({tokens}) "
        f"exceeds the 2500-token warning threshold. "
        f"Consider reducing the skill's content to stay within context window best practices."
    )


def test_skill_context_window_error(skill_dir: Path) -> None:
    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    tokens = estimate_tokens(content)
    assert tokens <= 5000, (
        f"Skill '{skill_dir.name}/SKILL.md' estimated token count ({tokens}) "
        f"exceeds the 5000-token hard limit. "
        f"This skill is too large and must be reduced before use."
    )
