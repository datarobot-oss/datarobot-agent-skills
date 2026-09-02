# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic Layer-1 detectors of the datarobot-gap-analysis engine."""

import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "datarobot-gap-analysis"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

from gap_analysis import scanners  # noqa: E402
from gap_analysis.engine import _dedup  # noqa: E402
from gap_analysis.inventory import glob_match, iter_base_images  # noqa: E402
from gap_analysis.models import Finding, Severity  # noqa: E402
from gap_analysis.taxonomy import Taxonomy  # noqa: E402


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return Taxonomy.load(SCRIPTS / "taxonomy.yaml")


def _write(root: Path, rel: str, text: str = "") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_glob_match_reaches_root_level_paths() -> None:
    assert glob_match("infra/__main__.py", "**/infra/**")
    assert glob_match("agent.py", "**/*.py")
    assert glob_match("tests/e2e/a.cy.ts", "**/tests/**")
    assert not glob_match("src/app.py", "**/infra/**")


@pytest.mark.parametrize(
    ("check_id", "expected"),
    [
        (
            "yaml.github-actions.security.github-actions-mutable-action-tag",
            ("SEC-014", "high"),
        ),
        ("package_managers.uv.uv-missing-dependency-cooldown", ("SEC-014", "high")),
        (
            "python.lang.security.audit.exec-detected.exec-detected",
            ("SEC-011", "medium"),
        ),
        ("python.django.security.injection.sql.sql-injection", ("SEC-011", "high")),
        (
            "python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure",
            ("SEC-004", "medium"),
        ),
        ("python.lang.best-practice.open-never-closed", None),
    ],
)
def test_semgrep_rules_route_by_family(
    check_id: str, expected: tuple[str, str] | None
) -> None:
    assert scanners._classify_semgrep(check_id) == expected


def test_secret_scan_ignores_fixtures_bundles_and_structured_values(
    tmp_path: Path, taxonomy: Taxonomy
) -> None:
    _write(
        tmp_path,
        "app/config.py",
        'API_KEY = "sk-live-9f8e7d6c5b4a39281706f5e4d3c2b1a0"\n',
    )
    _write(tmp_path, "app/tests/test_api.py", 'token = "abcdefghijklmnop123456"\n')
    _write(
        tmp_path,
        "app/static/assets/index-Ab12Cd34.js",
        'var password="x".repeat(9);' * 300,
    )
    _write(tmp_path, "app/handlers.py", 'secret = "compute({id: ror()})"\n')

    findings, _notes = scanners.run_secret_scan(tmp_path, taxonomy)

    assert [f.file for f in findings] == ["app/config.py"]
    assert findings[0].condition_id == "SEC-002"
    assert "sk-live" not in findings[0].evidence


def test_looks_env_requires_env_extension_for_stage_names() -> None:
    assert scanners._looks_env(".env.prod")
    assert scanners._looks_env("config/prod.yaml")
    assert not scanners._looks_env("tests/fixtures/config.yaml")
    assert not scanners._looks_env("deploy/prod/main.py")


def test_dockerfile_args_are_resolved_and_aliases_skipped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "svc/Dockerfile",
        "ARG BASE_IMAGE=datarobot/mirror_chainguard_datarobot.com_python-fips:3.12-dev\n"
        "FROM ${BASE_IMAGE} AS base\n"
        "FROM base AS runtime\n"
        "FROM ${UNSET_IMAGE}\n",
    )
    _write(
        tmp_path,
        ".devcontainer/Dockerfile",
        "FROM mcr.microsoft.com/devcontainers/python:3.12\n",
    )

    images = list(iter_base_images(tmp_path))

    assert images == [
        (
            "datarobot/mirror_chainguard_datarobot.com_python-fips:3.12-dev",
            "svc/Dockerfile",
        )
    ]


def test_engineering_baseline_flags_a_bare_repo(
    tmp_path: Path, taxonomy: Taxonomy
) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "x"\ndependencies = ["requests"]\n',
    )
    _write(tmp_path, "web/package.json", '{"name": "web"}\n')
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        "jobs:\n  t:\n    steps:\n      - uses: actions/checkout@main\n",
    )

    findings, _notes = scanners.check_engineering_baseline(tmp_path, taxonomy)
    ids = sorted(f.condition_id for f in findings)

    assert ids == [
        "ITA-006",
        "REL-005",
        "REL-006",
        "REL-006",
        "SEC-014",
        "SEC-015",
        "SEC-016",
    ]
    pinning = next(f for f in findings if f.condition_id == "SEC-014")
    assert "actions/checkout@main" in pinning.evidence


def test_engineering_baseline_passes_a_template_shaped_repo(
    tmp_path: Path, taxonomy: Taxonomy
) -> None:
    _write(
        tmp_path,
        "core/pyproject.toml",
        '[project]\nname = "core"\n[tool.ruff]\n[tool.mypy]\nstrict = true\n',
    )
    _write(tmp_path, "core/uv.lock", "")
    _write(tmp_path, "web/package.json", '{"name": "web"}\n')
    _write(tmp_path, "web/package-lock.json", "{}\n")
    _write(
        tmp_path,
        "core/Taskfile.yaml",
        "tasks:\n  lint-check:\n    cmds:\n      - uv run ruff check .\n",
    )
    _write(
        tmp_path,
        ".github/workflows/core.yml",
        "jobs:\n  t:\n    steps:\n      - uses: actions/checkout@v7\n",
    )
    _write(tmp_path, ".github/dependabot.yml", "version: 2\n")
    _write(tmp_path, ".github/CODEOWNERS", "* @datarobot/applications\n")
    _write(tmp_path, "trivy-ignore.rego", "package trivy\n")

    findings, _notes = scanners.check_engineering_baseline(tmp_path, taxonomy)

    assert findings == []


def test_ci_presence_knows_harness(tmp_path: Path, taxonomy: Taxonomy) -> None:
    _write(tmp_path, ".harness/security/pipeline.yml", "pipeline: {}\n")
    _write(tmp_path, "tests/test_x.py", "def test_x(): pass\n")

    findings, _notes = scanners.check_presence(tmp_path, taxonomy)

    assert findings == []


def test_dedup_keeps_distinct_file_level_findings() -> None:
    def mk(evidence: str) -> Finding:
        return Finding(
            "SEC-010", "SEC", Severity.HIGH, "CVEs", file="uv.lock", evidence=evidence
        )

    kept = _dedup(
        [mk("litellm==1.80.0"), mk("starlette==0.40.0"), mk("litellm==1.80.0")]
    )

    assert [f.evidence for f in kept] == ["litellm==1.80.0", "starlette==0.40.0"]
