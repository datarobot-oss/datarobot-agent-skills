# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Spec-conformance tests for the claims the `datarobot-workload-api` skill
makes about the published OpenAPI spec.

Covers:
  - Org-set scaling-limit fields (maxConcurrentWorkloads, maxWorkloadReplicas)
    on UserRetrieveResponse / OrganizationRetrieve / OrganizationUserResponse
  - Code-to-Workload schemas (ImageBuildConfig, GeneratedDockerfile,
    ProvidedDockerfile, CodeRef) and their required fields
  - The /api/v2/executionEnvironments/ listing endpoint and its useCases enum
  - The public-spec path-key prefix quirk: workload paths key WITHOUT
    /api/v2/, other namespaces key WITH it

If any of these go missing or get renamed in the published spec, the skill
becomes silently misleading. This test catches that drift.

It fetches the published spec from docs.datarobot.com once per test session.
When the network is unavailable, tests skip cleanly rather than fail.
"""

from __future__ import annotations

from typing import Any

import pytest

PUBLIC_SPEC_URL = (
    "https://docs.datarobot.com/en/docs/api/reference/public-api/openapi.yaml"
)

# The (schema, property) pairs the skill claims the spec exposes.  If any of
# these go missing or get renamed, both this test AND the skill need an update.
REQUIRED_LIMIT_FIELDS: list[tuple[str, str]] = [
    ("OrganizationRetrieve", "maxConcurrentWorkloads"),
    ("OrganizationRetrieve", "maxWorkloadReplicas"),
    ("OrganizationUserResponse", "maxConcurrentWorkloads"),
    ("OrganizationUserResponse", "maxWorkloadReplicas"),
    ("UserRetrieveResponse", "maxConcurrentWorkloads"),
    ("UserRetrieveResponse", "maxWorkloadReplicas"),
]


@pytest.fixture(scope="module")
def public_spec() -> dict[str, Any]:
    """Fetch + parse the public OpenAPI spec.  Skip the test if offline."""
    try:
        import httpx
        import yaml
    except ImportError as e:
        pytest.skip(f"required dependency unavailable: {e}")
    try:
        r = httpx.get(PUBLIC_SPEC_URL, timeout=20.0, follow_redirects=True)
    except httpx.HTTPError as e:
        pytest.skip(f"could not fetch public spec ({type(e).__name__}: {e})")
    if r.status_code != 200:
        pytest.skip(f"public spec fetch returned {r.status_code}")
    return dict(yaml.safe_load(r.text))


@pytest.mark.parametrize(("schema_name", "prop"), REQUIRED_LIMIT_FIELDS)
def test_limit_field_present_in_public_spec(
    public_spec: dict[str, Any], schema_name: str, prop: str
) -> None:
    """The skill claims this (schema, property) pair exists. Verify against the live spec."""
    schemas = public_spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, (
        f"Schema {schema_name!r} not found in the public OpenAPI spec. "
        f"The datarobot-workload-api skill references it in references/schema-reference.md "
        f"and SKILL.md — update both if the schema was renamed."
    )
    props = schemas[schema_name].get("properties") or {}
    assert prop in props, (
        f"Property {schema_name}.{prop} not found in the public OpenAPI spec. "
        f"The datarobot-workload-api skill teaches agents to read this field — update the skill "
        f"if it was renamed or removed."
    )


def test_limit_fields_documented_in_skill() -> None:
    """The skill text should mention both limit field names so an agent searching for them finds the guidance."""
    from pathlib import Path

    skill_md = (
        Path(__file__).resolve().parents[2] / "skills/datarobot-workload-api/SKILL.md"
    ).read_text()
    for field in ("maxConcurrentWorkloads", "maxWorkloadReplicas"):
        assert field in skill_md, (
            f"SKILL.md should mention {field!r} so an agent grepping for it finds the "
            f"org-set scaling limits guidance. If you removed it intentionally, also update "
            f"this test."
        )


# ---------------------------------------------------------------------------
# Code-to-Workload schemas
# ---------------------------------------------------------------------------

C2W_SCHEMAS_WITH_REQUIRED_FIELDS: list[tuple[str, list[str]]] = [
    # The C2W reference teaches agents to construct these shapes.  If a field
    # is missing or renamed in the spec, the agent generates invalid request
    # bodies.
    ("ImageBuildConfig", ["codeRef", "dockerfile"]),
    (
        "GeneratedDockerfile",
        ["executionEnvironmentId", "executionEnvironmentVersionId", "entrypoint"],
    ),
    ("ProvidedDockerfile", ["source"]),
    ("CodeRef", ["datarobot"]),
]


@pytest.mark.parametrize(("schema_name", "fields"), C2W_SCHEMAS_WITH_REQUIRED_FIELDS)
def test_c2w_schema_present(
    public_spec: dict[str, Any], schema_name: str, fields: list[str]
) -> None:
    """C2W relies on these schemas; verify each exists with the fields the skill references."""
    schemas = public_spec.get("components", {}).get("schemas", {})
    assert schema_name in schemas, (
        f"C2W schema {schema_name!r} not in the public spec. references/code-to-workload.md "
        f"teaches agents to construct or expect this shape — update the reference if the "
        f"schema was renamed."
    )
    props = schemas[schema_name].get("properties") or {}
    for f in fields:
        assert f in props, (
            f"{schema_name}.{f} expected by the C2W reference but missing from the public "
            f"spec's schema definition. Update references/code-to-workload.md if the field "
            f"was renamed."
        )


def test_generated_dockerfile_requires_ee_and_entrypoint(
    public_spec: dict[str, Any],
) -> None:
    """The skill teaches that EE id + version + entrypoint are required for the generated path.
    Verify the spec marks them as required."""
    gd = public_spec["components"]["schemas"]["GeneratedDockerfile"]
    required = set(gd.get("required") or [])
    for f in (
        "executionEnvironmentId",
        "executionEnvironmentVersionId",
        "entrypoint",
    ):
        assert f in required, (
            f"GeneratedDockerfile.{f} expected as required by the C2W reference. "
            f"If the spec relaxed this, the reference's prerequisites section needs an update."
        )


# ---------------------------------------------------------------------------
# Execution Environment listing
# ---------------------------------------------------------------------------


def test_execution_environments_list_endpoint(public_spec: dict[str, Any]) -> None:
    """The C2W reference tells agents to discover EEs via /executionEnvironments/.  Verify it exists."""
    paths = public_spec.get("paths", {})
    assert "/api/v2/executionEnvironments/" in paths, (
        "/api/v2/executionEnvironments/ missing from the public spec. "
        "C2W reference's EE-discovery section needs an update."
    )


def test_execution_environments_usecases_enum(public_spec: dict[str, Any]) -> None:
    """The C2W reference quotes the useCases enum.  Verify the values match the spec."""
    ep = public_spec["paths"]["/api/v2/executionEnvironments/"]["get"]
    use_cases_param = next(
        (p for p in (ep.get("parameters") or []) if p.get("name") == "useCases"),
        None,
    )
    assert use_cases_param is not None, (
        "useCases query param missing from EE listing endpoint"
    )
    enum = (use_cases_param.get("schema") or {}).get("enum") or []
    expected = {
        "customModel",
        "notebook",
        "gpu",
        "customApplication",
        "sparkApplication",
        "customJob",
    }
    actual = set(enum)
    assert expected.issubset(actual), (
        f"useCases enum lost values: expected {expected}, got {actual}. "
        f"C2W reference quotes this enum — update it."
    )


# ---------------------------------------------------------------------------
# Public-spec path-key prefix quirk
# ---------------------------------------------------------------------------


def test_workload_paths_keyed_without_api_v2_prefix(
    public_spec: dict[str, Any],
) -> None:
    """The skill warns agents that workload paths key WITHOUT /api/v2/ in the public spec."""
    paths = public_spec.get("paths", {})
    workload_root = "/workloads/{workload_id}"
    assert workload_root in paths, (
        f"{workload_root} expected as a path key (without /api/v2/ prefix) — the public spec's "
        f"path-key prefix quirk has changed. Update references/schema-reference.md."
    )


def test_otel_credentials_bundles_paths_keyed_with_api_v2_prefix(
    public_spec: dict[str, Any],
) -> None:
    """The skill warns that OTEL / credentials / bundles paths key WITH /api/v2/."""
    paths = public_spec.get("paths", {})
    for expected_path in (
        "/api/v2/otel/{entityType}/{entityId}/logs/",
        "/api/v2/credentials/",
        "/api/v2/mlops/compute/bundles/",
    ):
        assert expected_path in paths, (
            f"{expected_path} expected (with /api/v2/ prefix) — the public spec's path-key "
            f"convention has changed. Update references/schema-reference.md and any agent "
            f"grep instructions."
        )
