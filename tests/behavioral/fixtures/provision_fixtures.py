# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Provision the long-lived DataRobot fixture resources behavioral scenarios need.

Some scenarios assert against pre-existing DataRobot state instead of paying
for AutoML inside every run: the predictions-template scenario needs a healthy
deployment, feature-impact needs a trained model with Feature Impact computed,
and drift needs a deployment that has actually served predictions. This script
builds that state once per account and prints the resource ids as
``BEHAVIORAL_FIXTURE_*`` env-var lines that scenarios consume via their
``requires_env`` declarations.

Everything is named with the ``bfix-`` prefix — deliberately OUTSIDE the
``drat-`` family that per-run teardown and ``dr-agent eval sweep`` match, so
cleanup can never delete the fixtures. Delete them with ``--recreate`` or by
hand.

Requires DATAROBOT_API_TOKEN / DATAROBOT_ENDPOINT and the datarobot SDK
(``uv run --group behavioral``). The full pipeline waits on a Quick-mode
AutoML run (~15-20 min) the first time; subsequent runs find and reuse
everything by name in seconds.

Usage (from the repo root):
    uv run --group behavioral python tests/behavioral/fixtures/provision_fixtures.py
        [--check]            validate-only: exit 0 iff every fixture exists and
                             is healthy (CI preflight; prints the id lines)
        [--recreate]         delete existing bfix- fixtures first, then build
        [--refresh-traffic]  rescore the holdout through the deployment so
                             drift windows have recent traffic, then exit
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent
TRAIN_CSV = FIXTURES_DIR / "churn_train.csv"
HOLDOUT_CSV = FIXTURES_DIR / "churn_holdout.csv"

#: bfix- = "behavioral fixture". Must never start with "drat-" (the sweeper's
#: family prefix) or these resources would be deleted by cleanup.
PREFIX = "bfix-"
USE_CASE_NAME = f"{PREFIX}churn-use-case"
DATASET_NAME = f"{PREFIX}churn-train"
PROJECT_NAME = f"{PREFIX}churn-project"
DEPLOYMENT_NAME = f"{PREFIX}churn-deployment"
TARGET = "churn"


def _resilient(
    fn: Callable[[], Any], attempts: int = 5, delay_seconds: int = 20
) -> Any:
    """Retry through transient connection drops during long server-side waits."""
    import requests

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except requests.exceptions.ConnectionError as exc:
            if attempt == attempts:
                raise
            print(f"transient connection error (attempt {attempt}/{attempts}): {exc}")
            time.sleep(delay_seconds)


def _client() -> Any:
    import datarobot as dr

    token = os.environ.get("DATAROBOT_API_TOKEN")
    endpoint = os.environ.get("DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2")
    if not token:
        sys.exit("DATAROBOT_API_TOKEN is not set")
    dr.Client(token=token, endpoint=endpoint)
    return dr


def _find_use_case(dr: Any) -> Any:
    return next((u for u in dr.UseCase.list() if u.name == USE_CASE_NAME), None)


def _find_project(dr: Any) -> Any:
    matches = dr.Project.list(search_params={"project_name": PROJECT_NAME})
    return next((p for p in matches if p.project_name == PROJECT_NAME), None)


def _find_deployment(dr: Any) -> Any:
    matches = dr.Deployment.list(search=DEPLOYMENT_NAME)
    return next((d for d in matches if d.label == DEPLOYMENT_NAME), None)


def _recommended_model(dr: Any, project: Any) -> Any:
    return dr.ModelRecommendation.get(project.id).get_model()


def _ensure_use_case(dr: Any) -> Any:
    use_case = _find_use_case(dr)
    if use_case is None:
        use_case = dr.UseCase.create(
            name=USE_CASE_NAME,
            description="Long-lived fixture for behavioral scenario runs — do not delete.",
        )
        print(f"created use case {use_case.id}")
    else:
        print(f"reusing use case {use_case.id}")
    return use_case


def _ensure_project(dr: Any, use_case: Any) -> Any:
    project = _find_project(dr)
    if project is not None:
        project = dr.Project.get(project.id)
        print(f"reusing project {project.id} (stage={project.stage})")
        if project.stage != "modeling":
            # Target-setting may still be resolving from an interrupted run.
            deadline = time.monotonic() + 300
            while project.stage != "modeling" and time.monotonic() < deadline:
                print(f"  stage={project.stage!r}; waiting for target-setting ...")
                time.sleep(20)
                project = dr.Project.get(project.id)
            if project.stage != "modeling":
                sys.exit(
                    f"project {project.id} stuck at stage {project.stage!r}; "
                    "run --recreate to rebuild it"
                )
        _resilient(lambda: project.wait_for_autopilot())
        print("autopilot finished")
        return project

    print(f"uploading {TRAIN_CSV.name} ...")
    dataset = dr.Dataset.create_from_file(
        file_path=str(TRAIN_CSV), use_cases=[use_case]
    )
    dataset.modify(name=DATASET_NAME)
    print(f"created dataset {dataset.id}")

    project = dr.Project.create_from_dataset(
        dataset_id=dataset.id, project_name=PROJECT_NAME, use_case=use_case
    )
    print(f"created project {project.id}; starting Quick autopilot on {TARGET!r} ...")
    _resilient(
        lambda: project.analyze_and_model(target=TARGET, mode="quick", worker_count=-1)
    )
    _resilient(lambda: project.wait_for_autopilot())
    print("autopilot finished")
    return dr.Project.get(project.id)


def _ensure_feature_impact(dr: Any, project: Any) -> Any:
    model = _recommended_model(dr, project)
    print(f"recommended model {model.id} ({model.model_type})")
    # The feature-impact scenario asserts on a model whose Feature Impact is
    # already computed — the skill under test never calls
    # request_feature_impact itself.
    model.get_or_request_feature_impact(max_wait=600)
    print("feature impact computed")
    return model


def _ensure_deployment(dr: Any, model: Any) -> Any:
    deployment = _find_deployment(dr)
    if deployment is None:
        version = dr.RegisteredModelVersion.create_for_leaderboard_item(
            model_id=model.id,
            registered_model_name=f"{PREFIX}churn-registered-model",
        )
        servers = dr.PredictionServer.list()
        deployment = dr.Deployment.create_from_registered_model_version(
            model_package_id=version.id,
            label=DEPLOYMENT_NAME,
            description="Long-lived fixture for behavioral scenario runs — do not delete.",
            default_prediction_server_id=servers[0].id if servers else None,
        )
        print(f"created deployment {deployment.id}")
    else:
        print(f"reusing deployment {deployment.id}")
    deployment.update_drift_tracking_settings(
        target_drift_enabled=True, feature_drift_enabled=True
    )
    print("drift tracking enabled (target + feature)")
    return deployment


def _score_holdout(dr: Any, deployment: Any) -> None:
    """Push the holdout through the deployment so drift windows have traffic."""
    print(f"scoring {HOLDOUT_CSV.name} through deployment {deployment.id} ...")
    started = time.monotonic()
    predictions = deployment.predict_batch(str(HOLDOUT_CSV))
    print(f"scored {len(predictions)} rows in {time.monotonic() - started:.0f}s")


def _emit_ids(project_id: str, model_id: str, deployment_id: str) -> None:
    print()
    print("# Export these (e.g. append to .env) for fixture-dependent scenarios:")
    print(f"BEHAVIORAL_FIXTURE_PROJECT_ID={project_id}")
    print(f"BEHAVIORAL_FIXTURE_MODEL_ID={model_id}")
    print(f"BEHAVIORAL_FIXTURE_DEPLOYMENT_ID={deployment_id}")


def cmd_check(dr: Any) -> int:
    """Validate-only: report each fixture; exit non-zero if any is missing."""
    use_case = _find_use_case(dr)
    project = _find_project(dr)
    deployment = _find_deployment(dr)
    ok = True

    for label, resource in (
        ("use case", use_case),
        ("project", project),
        ("deployment", deployment),
    ):
        if resource is None:
            print(f"MISSING: {label} ({PREFIX}...)")
            ok = False
        else:
            print(f"ok: {label} {resource.id}")

    model_id = None
    if project is not None:
        try:
            model_id = _recommended_model(dr, project).id
            print(f"ok: recommended model {model_id}")
        except Exception as exc:  # autopilot unfinished / project broken
            print(f"MISSING: recommended model ({type(exc).__name__}: {exc})")
            ok = False

    if not ok or project is None or deployment is None or model_id is None:
        print("\nRun provision_fixtures.py (no flags) to build the missing fixtures.")
        return 1
    _emit_ids(project.id, str(model_id), deployment.id)
    return 0


def cmd_recreate(dr: Any) -> None:
    """Delete existing bfix- fixtures (children before parents)."""
    deployment = _find_deployment(dr)
    if deployment is not None:
        print(f"deleting deployment {deployment.id}")
        deployment.delete()
    project = _find_project(dr)
    if project is not None:
        print(f"deleting project {project.id}")
        project.delete()
    for dataset in dr.Dataset.list():
        if (dataset.name or "").startswith(PREFIX):
            print(f"deleting dataset {dataset.id}")
            dr.Dataset.delete(dataset.id)
    use_case = _find_use_case(dr)
    if use_case is not None:
        print(f"deleting use case {use_case.id}")
        dr.UseCase.delete(use_case.id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="validate-only (CI preflight)"
    )
    parser.add_argument(
        "--recreate", action="store_true", help="delete and rebuild fixtures"
    )
    parser.add_argument(
        "--refresh-traffic",
        action="store_true",
        help="rescore the holdout through the fixture deployment, then exit",
    )
    args = parser.parse_args()

    dr = _client()

    if args.check:
        sys.exit(cmd_check(dr))

    if args.refresh_traffic:
        deployment = _find_deployment(dr)
        if deployment is None:
            sys.exit(f"no deployment labelled {DEPLOYMENT_NAME!r}; provision first")
        _score_holdout(dr, deployment)
        return

    if args.recreate:
        cmd_recreate(dr)

    use_case = _ensure_use_case(dr)
    project = _ensure_project(dr, use_case)
    model = _ensure_feature_impact(dr, project)
    deployment = _ensure_deployment(dr, model)
    _score_holdout(dr, deployment)
    _emit_ids(project.id, model.id, deployment.id)


if __name__ == "__main__":
    main()
