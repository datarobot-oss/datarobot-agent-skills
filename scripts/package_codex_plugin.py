#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build a public-upload ZIP for the DataRobot Codex plugin.

The archive deliberately includes only the portable public-plugin manifest,
the Codex compatibility manifest, the listing icon, and tracked skill files.
It excludes repository tooling, local caches, and unsupported app bindings.
"""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

ARCHIVE_ROOT = "datarobot-agent-skills"
PUBLIC_MANIFEST = Path("plugin.json")
CODEX_MANIFEST = Path(".codex-plugin/plugin.json")
ICON_PATH = Path("assets/datarobot-icon.png")
SKILLS_DIR = Path("skills")
REQUIRED_INTERFACE_FIELDS = {
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "defaultPrompt",
    "websiteURL",
    "supportURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
    "logo",
    "composerIcon",
}


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (defaults to the current directory).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Archive path (defaults to dist/datarobot-agent-skills-<version>.zip).",
    )
    return parser.parse_args(argv)


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data: dict[str, Any] = json.load(file)
    return data


def tracked_skill_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "skills"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return [Path(item.decode()) for item in result.stdout.split(b"\0") if item]


def validate_manifest(
    repo_root: Path, manifest: dict[str, Any], codex_manifest: dict[str, Any]
) -> None:
    interface = (
        manifest.get("extensions", {}).get("com.openai", {}).get("interface", {})
    )
    missing_fields = REQUIRED_INTERFACE_FIELDS - interface.keys()
    if missing_fields:
        raise ValueError(
            f"plugin.json is missing interface fields: {sorted(missing_fields)}"
        )
    if manifest.get("name") != ARCHIVE_ROOT:
        raise ValueError(f"plugin.json name must be '{ARCHIVE_ROOT}'")
    if manifest.get("version") != codex_manifest.get("version"):
        raise ValueError(
            "plugin.json and .codex-plugin/plugin.json versions must match"
        )
    if len(interface["displayName"]) > 30 or len(interface["shortDescription"]) > 30:
        raise ValueError(
            "displayName and shortDescription must be at most 30 characters"
        )
    prompts = interface["defaultPrompt"]
    if not isinstance(prompts, list) or not 1 <= len(prompts) <= 3:
        raise ValueError("defaultPrompt must contain one to three prompts")
    if any(
        not prompt.strip() or "\n" in prompt or len(prompt) > 128 for prompt in prompts
    ):
        raise ValueError(
            "defaultPrompt values must be nonblank single lines of at most 128 characters"
        )
    if (
        manifest.get("apps") is not None
        or manifest.get("extensions", {}).get("com.openai", {}).get("apps") is not None
    ):
        raise ValueError("public uploads cannot include app bindings")
    for asset_field in ("logo", "composerIcon"):
        asset_path = repo_root / interface[asset_field].removeprefix("./")
        if not asset_path.is_file():
            raise ValueError(f"missing referenced icon: {asset_path}")


def validate_skills(repo_root: Path, skill_files: list[Path]) -> None:
    if not skill_files or not any(path.name == "SKILL.md" for path in skill_files):
        raise ValueError("the package must contain at least one SKILL.md file")
    for skill_file in skill_files:
        if skill_file.name == "SKILL.md" and not (repo_root / skill_file).is_file():
            raise ValueError(f"tracked skill file is missing: {skill_file}")


def build_archive(repo_root: Path, output: Path) -> Path:
    manifest = read_json(repo_root / PUBLIC_MANIFEST)
    codex_manifest = read_json(repo_root / CODEX_MANIFEST)
    skill_files = tracked_skill_files(repo_root)
    validate_manifest(repo_root, manifest, codex_manifest)
    validate_skills(repo_root, skill_files)

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for relative_path in [PUBLIC_MANIFEST, CODEX_MANIFEST, ICON_PATH, *skill_files]:
            archive.write(repo_root / relative_path, Path(ARCHIVE_ROOT) / relative_path)
    return output


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest = read_json(repo_root / PUBLIC_MANIFEST)
    output = (
        args.output or repo_root / "dist" / f"{ARCHIVE_ROOT}-{manifest['version']}.zip"
    )
    output = output.resolve()
    print(build_archive(repo_root, output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
