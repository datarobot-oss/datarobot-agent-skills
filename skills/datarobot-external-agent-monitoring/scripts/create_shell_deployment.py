#!/usr/bin/env python3
"""Create a shell deployment in DataRobot for receiving external agent OTel telemetry.

Uses RegisteredModelVersion.create_for_external (DataRobot Python SDK 3.x).

Usage:
    python create_shell_deployment.py --name "My Agent" --description "OTel sink"

Env vars:
    DATAROBOT_API_TOKEN  - DataRobot API token
    DATAROBOT_ENDPOINT   - DataRobot API endpoint (e.g. https://app.datarobot.com/api/v2)
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import datarobot as dr


def _otel_endpoint(api_endpoint: str) -> str:
    """Derive OTel endpoint from the API endpoint.

    API endpoint:  https://app.datarobot.com/api/v2
    OTel endpoint: https://app.datarobot.com/otel
    """
    base = api_endpoint.rstrip("/")
    if base.endswith("/api/v2"):
        base = base[: -len("/api/v2")]
    return f"{base}/otel"


def _find_or_create_prediction_environment() -> dr.PredictionEnvironment:
    """Find or create a prediction environment for external agent monitoring.

    Not all tenants support platform="external". Try common platforms in order
    of preference: gcp, other, aws, azure. Reuse an existing environment when
    possible to avoid clutter.
    """
    preferred_platforms = ("gcp", "other", "aws", "azure")
    envs = dr.PredictionEnvironment.list()

    for platform in preferred_platforms:
        for env in envs:
            if getattr(env, "platform", None) == platform:
                return env

    # No compatible environment found — create one
    return dr.PredictionEnvironment.create(
        name="External Agent OTel Environment",
        platform="other",
        description="Prediction environment for external agent OTel monitoring",
    )


def create_shell_deployment(name: str, description: str) -> dict:
    """Create a shell deployment in DataRobot for external agent monitoring.

    Creates an external registered model version (target type: AgenticWorkflow)
    and deploys it with prediction row storage and automatic association ID
    generation enabled. The deployment ID is used to route OTel telemetry to
    the correct DataRobot monitoring dashboard.

    Args:
        name: Display name for the deployment
        description: Description of what agent this monitors

    Returns:
        Dict with deployment_id, entity_id, and otel_endpoint
    """
    token = os.getenv("DATAROBOT_API_TOKEN")
    endpoint = os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2")

    if not token:
        print("Error: DATAROBOT_API_TOKEN env var is required", file=sys.stderr)
        sys.exit(1)

    dr.Client(token=token, endpoint=endpoint)

    # --- Prediction environment ---
    pred_env = _find_or_create_prediction_environment()

    # --- Registered model version (external shell) ---
    # Prefer AgenticWorkflow (enables full monitoring dashboards);
    # fall back to TextGeneration if the tenant doesn't support it.
    try:
        model_version = dr.RegisteredModelVersion.create_for_external(
            name="external-agent-shell-v1",
            target={"name": "agent_output", "type": "AgenticWorkflow"},
            registered_model_name=name,
            registered_model_description=description,
        )
    except Exception as e:
        print(
            f"Warning: AgenticWorkflow target type failed ({e}). "
            "Retrying with TextGeneration.",
            file=sys.stderr,
        )
        model_version = dr.RegisteredModelVersion.create_for_external(
            name="external-agent-shell-v1",
            target={"name": "prediction", "type": "TextGeneration"},
            registered_model_name=name,
            registered_model_description=description,
        )

    # --- Deploy ---
    deployment = dr.Deployment.create_from_registered_model_version(
        model_package_id=model_version.id,
        label=name,
        description=description,
        prediction_environment_id=pred_env.id,
    )

    # --- Enable monitoring settings ---
    # Prediction row storage: stores prediction inputs/outputs for monitoring
    try:
        deployment.update_predictions_data_collection_settings(enabled=True)
    except Exception as e:
        print(
            f"Warning: Could not enable prediction row storage: {e}",
            file=sys.stderr,
        )

    # Automatic association ID generation: assigns unique IDs to prediction rows.
    # The API requires a column name alongside autoGenerateId.
    try:
        client = dr.client.get_client()
        resp = client.patch(
            f"deployments/{deployment.id}/settings/",
            json={
                "associationId": {
                    "columnNames": ["association_id"],
                    "autoGenerateId": True,
                    "requiredInPredictionRequests": False,
                },
            },
        )
        from datarobot.utils.waiters import wait_for_async_resolution

        wait_for_async_resolution(client, resp.headers["Location"])
    except Exception as e:
        print(
            f"Warning: Could not enable automatic association ID: {e}",
            file=sys.stderr,
        )

    return {
        "deployment_id": deployment.id,
        "entity_id": f"deployment-{deployment.id}",
        "otel_endpoint": _otel_endpoint(endpoint),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a DataRobot shell deployment for external agent monitoring"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Display name for the deployment",
    )
    parser.add_argument(
        "--description",
        default="External agent OTel telemetry sink",
        help="Description of what agent this monitors",
    )
    args = parser.parse_args()

    try:
        result = create_shell_deployment(args.name, args.description)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
