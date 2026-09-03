# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic Layer-1 detectors of the datarobot-gap-analysis engine."""

import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "datarobot-gap-analysis"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))

from gap_analysis import scanners  # noqa: E402
from gap_analysis.detect import _result_to_findings, layer2_files  # noqa: E402
from gap_analysis.docs import parse_llms_txt, resolve_docs  # noqa: E402
from gap_analysis.engine import _dedup  # noqa: E402
from gap_analysis.inventory import (  # noqa: E402
    build_inventory,
    detect_agent_frameworks,
    detect_python_version,
    detect_python_versions,
    detect_template_sources,
    evidence_files,
    extract_dependencies,
    glob_match,
    iter_base_images,
)
from gap_analysis.llm import brief_error, parse_json  # noqa: E402
from gap_analysis.models import AnalysisResult, Finding, Severity  # noqa: E402
from gap_analysis.posture import migration_advice  # noqa: E402
from gap_analysis.remediate import (  # noqa: E402
    _locked_version,
    _uv_error_line,
    fix_version_from,
    pin_in_pyproject,
    remediate,
)
from gap_analysis.report import compliance_path, python_label, render_report  # noqa: E402
from gap_analysis.risk_management import (  # noqa: E402
    _detect_iac,
    _finding_for_mitigation,
)
from gap_analysis.scanners import (  # noqa: E402
    gitleaks_findings,
    hadolint_findings,
    leaked_key,
    trivy_findings,
)
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


def test_evidence_files_prefer_source_over_config_and_skip_locks() -> None:
    inventory = {
        "files": [
            "infra/uv.lock",
            "infra/Taskfile.yaml",
            "infra/Pulumi.prod.yaml",
            "infra/pyproject.toml",
            "infra/infra/web.py",
            "infra/__main__.py",
            "web/app/system_prompt.py",
        ]
    }

    chosen = evidence_files(inventory, ["**/infra/**", "**/*.yaml", "**/*prompt*"], 4)

    assert chosen == [
        "infra/__main__.py",
        "infra/infra/web.py",
        "web/app/system_prompt.py",
        "infra/pyproject.toml",
    ]
    assert evidence_files(inventory, ["**/infra/**"], 3, first=["infra/infra/web.py"])[
        0
    ] == ("infra/infra/web.py")


def test_detect_iac_finds_infra_program_behind_a_large_app_tree(tmp_path: Path) -> None:
    for i in range(250):
        _write(tmp_path, f"app/module_{i:03d}.py", "x = 1\n")
    _write(
        tmp_path,
        "infra/__main__.py",
        "import pulumi\nfrom datarobot_pulumi_utils.pulumi import finalize\nfrom infra import *\n",
    )
    _write(
        tmp_path,
        "infra/infra/web.py",
        "import pulumi_datarobot\napp = pulumi_datarobot.CustomApplication('web')\n",
    )

    iac = _detect_iac(tmp_path, build_inventory(tmp_path))

    assert iac is not None
    assert iac["file"] == "infra/__main__.py"
    assert "infra/infra/web.py" in iac["files"]
    assert iac["application"] and not iac["deployment"]


def _pol(cid: str, via: str, requires: str = "", detector: str = "") -> Finding:
    return Finding(
        cid,
        "POL",
        Severity.HIGH,
        f"DataRobot risk-management: {cid.lower()} not satisfied",
        fix_via=via,
        fix_requires=requires,
        detector=detector or f"risk_management:{cid.lower()}",
        docs_topic="Set up data drift monitoring",
    )


def test_compliance_path_groups_gaps_by_what_unblocks_them() -> None:
    result = AnalysisResult(
        findings=[
            _pol("POL-DR-DRIFT-TRACKING", "pulumi", "deployment"),
            _pol("POL-DR-PROMPT-INJECTION-GUARD", "pulumi", "custom_model"),
            _pol("POL-DR-SERVICE-HEALTH", "automatic"),
            _pol(
                "POL-DR-PII-COMPLIANCE-TEST",
                "api",
                detector="risk_management:pii_compliance_test",
            ),
            _pol("POL-DR-RISK-DESCRIPTION-FILLED", "api"),
        ],
        iac={
            "file": "infra/__main__.py",
            "deployment": False,
            "custom_model": False,
            "application": True,
        },
    )
    result.regulatory_coverage = [
        {
            "mitigation_type": f.detector.split(":", 1)[1],
            "title": f.title,
            "status": "gap",
        }
        for f in result.findings
    ] + [{"mitigation_type": "rbac", "title": "Access control", "status": "pass"}]

    steps = compliance_path(result)

    assert [s["title"] for s in steps] == [
        "Put the model or LLM path behind DataRobot",
        "Run the compliance tests in the LLM test suite",
        "Complete in the DataRobot console or API",
    ]
    assert len(steps[0]["items"]) == 3
    report = render_report(result)
    assert "**1. Put the model or LLM path behind DataRobot.**" in report
    assert "Unlocks 3 mitigation(s)" in report
    assert "### Regulatory Policy" not in report
    assert "- ✅ Access control" in report


def test_compliance_path_configures_when_resources_exist() -> None:
    result = AnalysisResult(
        findings=[_pol("POL-DR-DRIFT-TRACKING", "pulumi", "deployment")],
        iac={
            "file": "infra/__main__.py",
            "deployment": True,
            "deployment_file": "infra/llm.py",
        },
    )

    steps = compliance_path(result)

    assert [s["title"] for s in steps] == [
        "Configure the existing Deployment / CustomModel in Pulumi"
    ]


def test_layer4_finding_carries_steps_docs_and_prerequisite() -> None:
    meta = {
        "title": "Data-drift monitoring",
        "default_severity": "high",
        "structural": True,
        "datarobot_feature": "drift monitoring",
        "remediation": "Deploy through DataRobot.",
        "docs_topic": "Set up data drift monitoring",
        "steps": ["Make it a Deployment.", "Set drift_tracking_settings."],
        "fix": {
            "via": "pulumi",
            "requires": "deployment",
            "hint": "h",
            "fix_risk": "plumbing",
        },
    }
    iac = {
        "file": "infra/__main__.py",
        "deployment": False,
        "custom_model": False,
        "application": True,
    }

    f = _finding_for_mitigation(
        "drift_tracking", meta, {"evidence": "no settings"}, iac
    )

    assert f.steps == meta["steps"]
    assert f.docs_topic == "Set up data drift monitoring"
    assert f.fix_via == "pulumi" and f.fix_requires == "deployment"
    assert "CustomApplication only" in f.prerequisite
    assert f.fix_type == "advisory" and f.structural


def test_mitigation_catalog_has_steps_and_docs_for_every_type() -> None:
    catalog = yaml.safe_load((SCRIPTS / "risk_management_mitigations.yaml").read_text())
    for m in catalog["mitigations"]:
        assert m.get("steps"), m["mitigation_type"]
        assert m.get("docs_topic"), m["mitigation_type"]
        assert "docs_url" not in m, "docs pages are resolved at run time, never pinned"


def test_docs_resolver_prefers_current_product_pages() -> None:
    index = parse_llms_txt(
        "# DataRobot docs\n\n## Pages\n\n"
        "- [Data drift](https://docs.datarobot.com/en/docs/classic-ui/mlops/data-drift-settings.html): Classic UI drift settings.\n"
        "- [Set up data drift monitoring](https://docs.datarobot.com/en/docs/workbench/nxt-console/nxt-settings/nxt-data-drift-settings.html): Configure drift tracking.\n"
        "- [Notebooks](https://docs.datarobot.com/en/docs/workbench/notebooks.html): Unrelated page.\n"
    )

    assert resolve_docs("Set up data drift monitoring", index).endswith(
        "nxt-data-drift-settings.html"
    )
    assert resolve_docs("quantum teleportation", index) == ""


def test_template_and_framework_detection(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".datarobot/answers/base.yml",
        "_commit: 8b5e502\n_src_path: https://github.com/datarobot/af-component-base\n",
    )
    _write(
        tmp_path,
        ".datarobot/answers/e2e.yml",
        "_src_path: git@github.com:datarobot/af-component-e2e-tests.git\n",
    )

    choices = {"Base": "base", "LangGraph": "langgraph", "CrewAI": "crewai"}
    sources = detect_template_sources(tmp_path)
    frameworks = detect_agent_frameworks(
        ["fastapi", "pydantic-ai", "langgraph"], choices
    )
    advice = migration_advice(
        {
            "template_sources": sources,
            "agent_frameworks": frameworks,
            "agent_template_choices": choices,
        }
    )

    assert sources == ["af-component-base", "af-component-e2e-tests"]
    assert frameworks == [
        {"name": "LangGraph", "native": True},
        {"name": "pydantic-ai", "native": False},
    ]
    assert "already builds on af-components" in advice
    assert "generic Base flavor" in advice
    assert "LangGraph, CrewAI" in advice
    assert "datarobot-agent-assist" not in advice


def test_migration_advice_without_af_components_hands_off_to_agent_assist() -> None:
    assert "datarobot-agent-assist" in migration_advice(
        {"template_sources": [], "agent_frameworks": []}
    )


def test_parse_json_ignores_trailing_commentary_and_errors_stay_short() -> None:
    assert parse_json('{"status": "found", "findings": []}\nThat is my answer.') == {
        "status": "found",
        "findings": [],
    }
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert len(brief_error(RuntimeError("x" * 5000))) == 300
    assert "\n" not in brief_error(RuntimeError("line one\nline two"))


def test_layer2_excludes_tests_and_iac_for_runtime_checks(taxonomy: Taxonomy) -> None:
    inventory = {
        "files": [
            "app/main.py",
            "app/tests/test_main.py",
            "infra/__main__.py",
            "alembic_migration.py",
            ".github/workflows/ci.yml",
            "core/telemetry.py",
        ]
    }
    ops = taxonomy.get("OPS-002")
    assert ops is not None and ops.scope == "repo" and ops.runtime_only

    assert layer2_files(inventory, ops) == ["app/main.py", "core/telemetry.py"]


def test_repo_scope_findings_collapse_to_one(taxonomy: Taxonomy) -> None:
    ops = taxonomy.get("OPS-002")
    assert ops is not None
    result = {
        "status": "found",
        "findings": [
            {
                "file": "app/a.py",
                "line": 3,
                "evidence": "no spans",
                "confidence": "medium",
            },
            {
                "file": "app/b.py",
                "line": 9,
                "evidence": "no spans",
                "confidence": "high",
            },
            {"file": "app/c.py", "evidence": "no spans", "confidence": "low"},
        ],
    }

    findings = _result_to_findings(ops, result)

    assert len(findings) == 1
    assert findings[0].evidence.startswith(
        "3 location(s): app/a.py:3, app/b.py:9, app/c.py."
    )
    assert findings[0].confidence == "high"


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ('DRAppCtx(api_key="first-user-api-key")', False),
        ('token = "my-super-secret-token"', False),
        ('password = "hunter2hunter2"', False),
        ('API_KEY = "sk-live-9f8e7d6c5b4a39281706f5e4d3c2b1a0"', True),
        ('api_key = "NDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkw"', True),
        ('secret = "3f9a8c7b6d5e4f3a2b1c0d9e8f7a6b5c"', True),
        ('token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef1234"', True),
    ],
)
def test_generic_credential_rule_needs_a_credential_shaped_value(
    line: str, flagged: bool
) -> None:
    hits = scanners._scan_text_for_secrets(line)

    assert bool(hits) is flagged, hits


def test_python_floor_is_the_lowest_across_components(tmp_path: Path) -> None:
    _write(tmp_path, "core/pyproject.toml", '[project]\nrequires-python = ">=3.10"\n')
    _write(
        tmp_path, "web/pyproject.toml", '[project]\nrequires-python = ">=3.12, <3.14"\n'
    )
    _write(
        tmp_path, "web/.venv/pyproject.toml", '[project]\nrequires-python = ">=3.8"\n'
    )

    versions = detect_python_versions(tmp_path)

    assert versions == {"core": "3.10", "web": "3.12"}
    assert detect_python_version(tmp_path) == "3.10"
    assert python_label({"python_version": "3.10", "python_versions": versions}) == (
        "3.10 (core 3.10, web 3.12)"
    )
    assert python_label({}) == "n/a"


def test_dependencies_come_from_every_component_manifest(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "core/pyproject.toml",
        '[project]\nname = "core"\ndependencies = ["Pydantic-AI[ag-ui]>=2.8", "httpx"]\n',
    )
    _write(
        tmp_path,
        "web/requirements.txt",
        "fastapi==0.115.0\n# comment\n-e .\nuvicorn[standard]>=0.30\n",
    )
    _write(
        tmp_path, "web/.venv/pyproject.toml", '[project]\ndependencies = ["ignored"]\n'
    )

    deps = extract_dependencies(tmp_path)

    assert {"pydantic-ai", "httpx", "fastapi", "uvicorn"} <= set(deps)
    assert "ignored" not in deps


def test_fix_version_parsing_and_lock_lookup() -> None:
    assert (
        fix_version_from("3 known vulnerabilities; fixed in: 3.14.2, 3.14.3.")
        == "3.14.2"
    )
    assert fix_version_from("Known vulnerability X; fixed in: 10.2.") == "10.2"
    assert fix_version_from("fixed in: see advisory.") is None
    lock = 'name = "aiohttp"\nversion = "3.14.1"\n\n[[package]]\nname = "zipp"\nversion = "3.23.0"\n'
    assert _locked_version(lock, "aiohttp") == "3.14.1"
    assert _locked_version(lock, "click") is None


def test_selected_advisory_ids_are_reported_not_ignored(tmp_path: Path) -> None:
    finding = Finding(
        "REL-006",
        "REL",
        Severity.MEDIUM,
        "Dependencies not locked",
        fix_type="advisory",
    )

    summary = remediate(
        tmp_path, [finding], {}, "20260903T000000Z", None, selected_ids={"REL-006"}
    )

    assert summary["unfixable_selected"] == ["REL-006"]
    assert summary["branch"] is None


def test_pin_in_pyproject_prefers_manifest_over_lock() -> None:
    direct = '[project]\ndependencies = [\n    "aiohttp[speedups]>=3.9,<4; python_version < \'3.14\'",\n    "httpx",\n]\n'
    text, how = pin_in_pyproject(direct, "aiohttp", "3.14.2")
    assert how == "direct"
    assert "\"aiohttp[speedups]>=3.14.2,<4; python_version < '3.14'\"" in text

    constrained = '[tool.uv]\nconstraint-dependencies = [\n    "tornado>=6.5.7",\n]\n'
    text, how = pin_in_pyproject(constrained, "tornado", "6.5.8")
    assert (how, '"tornado>=6.5.8"' in text) == ("constraint", True)

    text, how = pin_in_pyproject(constrained, "click", "8.3.3")
    assert how == "constraint" and '    "click>=8.3.3",\n    "tornado>=6.5.7",' in text

    text, how = pin_in_pyproject('[project]\nname = "x"\n', "pyasn1", "0.6.4")
    assert text.endswith(
        '[tool.uv]\nconstraint-dependencies = [\n    "pyasn1>=0.6.4",\n]\n'
    )


def test_uv_error_line_skips_the_version_banner() -> None:
    out = "Using CPython 3.13.13\n  × Failed to build `panel-library @ file:///x/web/panel-library`\n  ╰─▶ /x/web/panel-library\n"
    assert _uv_error_line(out).startswith("Failed to build `panel-library")


def test_trivy_report_routes_by_class(taxonomy: Taxonomy) -> None:
    data = {
        "Results": [
            {
                "Target": "infra/uv.lock",
                "Vulnerabilities": [
                    {
                        "PkgName": "aiohttp",
                        "InstalledVersion": "3.14.1",
                        "VulnerabilityID": "CVE-2026-1",
                        "FixedVersion": "3.14.2",
                        "Severity": "HIGH",
                    },
                    {
                        "PkgName": "aiohttp",
                        "InstalledVersion": "3.14.1",
                        "VulnerabilityID": "CVE-2026-2",
                        "FixedVersion": "3.14.3",
                        "Severity": "MEDIUM",
                    },
                ],
                "Licenses": [
                    {"PkgName": "readline", "Name": "GPL-3.0", "Severity": "HIGH"}
                ],
            },
            {
                "Target": "config/prod.yaml",
                "Secrets": [
                    {
                        "RuleID": "aws-access-key-id",
                        "Title": "AWS Access Key ID",
                        "StartLine": 4,
                    }
                ],
            },
            {
                "Target": "app/tests/fixtures/keys.yaml",
                "Secrets": [
                    {"RuleID": "aws-access-key-id", "Title": "AWS", "StartLine": 1}
                ],
            },
            {
                "Target": "Dockerfile",
                "Misconfigurations": [
                    {
                        "ID": "DS002",
                        "Title": "Image user should not be root",
                        "Severity": "HIGH",
                        "CauseMetadata": {"StartLine": 1},
                    }
                ],
            },
        ]
    }

    findings = trivy_findings(data, taxonomy, ["GPL-3.0", "AGPL-3.0"])
    by_id = {}
    for f in findings:
        by_id.setdefault(f.condition_id, []).append(f)

    assert [f.evidence for f in by_id["SEC-010"]] == [
        "aiohttp==3.14.1: CVE-2026-1, CVE-2026-2"
    ]
    assert "fixed in: 3.14.2, 3.14.3" in by_id["SEC-010"][0].explanation
    assert [f.file for f in by_id["SEC-003"]] == ["config/prod.yaml"]
    assert "SEC-002" not in by_id
    assert by_id["ITA-007"][0].evidence.startswith("1 trivy misconfiguration(s): DS002")
    assert by_id["ITA-004"][0].evidence == "readline: GPL-3.0"


def test_gitleaks_and_hadolint_group_per_file(
    taxonomy: Taxonomy, tmp_path: Path
) -> None:
    leaks = gitleaks_findings(
        [
            {
                "RuleID": "generic-api-key",
                "File": ".env",
                "Commit": "abcdef1234",
                "StartLine": 3,
                "Match": "OPENAI_API_KEY=REDACTED",
                "Description": "Generic API Key",
            },
            {
                "RuleID": "generic-api-key",
                "File": ".env",
                "Commit": "1234567abc",
                "StartLine": 2,
                "Match": 'DATAROBOT_API_TOKEN: "REDACTED"',
                "Description": "Generic API Key",
            },
            {
                "RuleID": "generic-api-key",
                "File": ".env",
                "Commit": "1234567abc",
                "StartLine": 7,
                "Match": "DATAROBOT_API_TOKEN=REDACTED",
                "Description": "Generic API Key",
            },
            {
                "RuleID": "private-key",
                "File": ".env",
                "Commit": "abcdef1234",
                "StartLine": 11,
                "Match": "REDACTED",
                "Secret": "REDACTED",
                "Description": "Private Key",
            },
        ],
        taxonomy,
    )
    assert [f.condition_id for f in leaks] == ["SEC-005", "SEC-005"]
    by_rule = {f.evidence.split(" ")[0]: f for f in leaks}
    assert (
        by_rule["DATAROBOT_API_TOKEN"].evidence
        == "DATAROBOT_API_TOKEN (lines 2, 7), OPENAI_API_KEY (line 3)"
        " in 2 commit(s) (1234567a, abcdef12)"
    )
    assert by_rule["DATAROBOT_API_TOKEN"].line == 3
    assert by_rule["private-key"].evidence == (
        "private-key block (line 11) in 1 commit(s) (abcdef12)"
    )

    lint = hadolint_findings(
        [
            {
                "file": str(tmp_path / "svc/Dockerfile"),
                "code": "DL3007",
                "level": "warning",
                "line": 1,
                "message": "Using latest is prone to errors",
            },
            {
                "file": str(tmp_path / "svc/Dockerfile"),
                "code": "DL3002",
                "level": "warning",
                "line": 9,
                "message": "Last USER should not be root",
            },
        ],
        taxonomy,
        tmp_path,
    )
    assert (
        len(lint) == 1
        and lint[0].condition_id == "ITA-007"
        and lint[0].file == "svc/Dockerfile"
    )
    assert lint[0].evidence == "2 hadolint finding(s): DL3002, DL3007"


def test_leaked_key_never_exposes_the_secret() -> None:
    assert leaked_key({"Match": "  export AWS_SECRET='REDACTED'"}) is None
    assert leaked_key({"Match": "AWS_SECRET='REDACTED'"}) == "AWS_SECRET"
    assert leaked_key({"Match": "token=abc123xyz", "Secret": "abc123xyz"}) == "token"
    assert leaked_key({"Match": "AKIAIOSFODNN7EXAMPLE"}) is None
    assert leaked_key({}) is None


def test_policy_fetch_failure_reports_the_http_reason(monkeypatch):
    import urllib.error

    from gap_analysis import risk_management as rm

    def boom(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(rm.urllib.request, "urlopen", boom)
    client = rm.RiskManagementClient("https://x.example/api/v2", "t")
    policy, note = rm.fetch_policy_by_name(client, "EU AI Act")
    assert policy is None
    assert "HTTP 401 Unauthorized" in note
    assert "riskPolicies" in note


def test_policy_fetch_retries_once_on_timeout(monkeypatch):
    import io

    from gap_analysis import risk_management as rm

    calls = []

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def flaky(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError()
        return _Resp(b'{"data": [{"id": "1", "name": "EU AI Act"}]}')

    monkeypatch.setattr(rm.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(rm.time, "sleep", lambda s: None)
    client = rm.RiskManagementClient("https://x.example/api/v2", "t")
    policy, note = rm.fetch_policy_by_name(client, "EU AI Act")
    assert len(calls) == 2
    assert policy["name"] == "EU AI Act"
    assert note is None


def test_policy_name_mismatch_lists_available_policies(monkeypatch):
    from gap_analysis import risk_management as rm

    monkeypatch.setattr(
        rm.RiskManagementClient,
        "get",
        lambda self, path: {"data": [{"id": "1", "name": "Custom framework"}]},
    )
    client = rm.RiskManagementClient("https://x.example/api/v2", "t")
    policy, note = rm.fetch_policy_by_name(client, "EU AI Act")
    assert policy is None
    assert "'Custom framework'" in note
    assert "regulatory.policy_name" in note
