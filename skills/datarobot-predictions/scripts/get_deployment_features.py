#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Get comprehensive information about features required by a deployment.

Usage:
    python get_deployment_features.py <deployment_id>

Outputs JSON with feature information, types, importance, and time series config.
"""

import json
import sys

import datarobot as dr


def get_deployment_features(deployment_id: str) -> dict:
    """
    Get comprehensive information about features required by a deployment.

    Args:
        deployment_id: The deployment ID

    Returns:
        Dictionary with feature information, types, importance, and time series config
    """
    # Initialize client
    dr.Client()

    deployment = dr.Deployment.get(deployment_id)
    target_name = deployment.model.get(
        "target_name"
    )  # None for unsupervised/anomaly deployments
    target_type = deployment.model["target_type"]

    # Get feature information: a list of plain dicts with keys name, feature_type,
    # importance, date_format, known_in_advance. `importance` is a model-independent
    # measure of the feature/target relationship strength (not Feature Impact).
    features = deployment.get_features()

    # Build feature list
    feature_list = []
    for feature in features:
        feature_list.append(
            {
                "feature_name": feature["name"],
                "feature_type": feature["feature_type"],
                "importance": feature["importance"],
                "is_target": feature["name"] == target_name,
            }
        )

    # Get time series config if applicable. deployment.model has "project_id" only
    # for deployments of leaderboard models (absent for custom-model deployments).
    time_series_config = None
    project_id = deployment.model.get("project_id")
    if project_id and dr.Project.get(project_id).use_time_series:
        try:
            partitioning = dr.DatetimePartitioning.get(project_id)
            time_series_config = {
                "datetime_column": partitioning.datetime_partition_column,
                "forecast_window_start": partitioning.forecast_window_start,
                "forecast_window_end": partitioning.forecast_window_end,
                "series_id_columns": partitioning.multiseries_id_columns or [],
            }
        except dr.errors.ClientError as e:
            print(
                f"Note: time series info unavailable: {e}",
                file=sys.stderr,
            )

    return {
        "deployment_id": deployment_id,
        "model_type": target_type,
        "target": target_name,
        "target_type": target_type,
        "features": feature_list,
        "time_series_config": time_series_config,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python get_deployment_features.py <deployment_id>", file=sys.stderr
        )
        sys.exit(1)

    deployment_id = sys.argv[1]
    result = get_deployment_features(deployment_id)
    print(json.dumps(result, indent=2))
