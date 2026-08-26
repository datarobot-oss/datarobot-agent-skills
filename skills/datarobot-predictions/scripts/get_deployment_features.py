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
    model = dr.Model.get(deployment.model["id"])
    project = dr.Project.get(model.project_id)

    # Get feature information
    features = model.get_features()
    feature_importance = model.get_feature_impact()

    # Build feature list
    feature_list = []
    for feature in features:
        importance = 0.0
        for fi in feature_importance:
            if fi["featureName"] == feature.name:
                importance = fi.get("impactNormalized", 0.0)
                break

        feature_list.append(
            {
                "feature_name": feature.name,
                "feature_type": feature.feature_type,
                "importance": importance,
                "is_target": feature.name == model.target_name,
            }
        )

    # Get time series config if applicable
    time_series_config = None
    if project.use_time_series:
        try:
            time_series_info = project.get_time_series_info()
            time_series_config = {
                "datetime_column": time_series_info.datetime_partition_column,
                "forecast_window_start": time_series_info.forecast_window_start,
                "forecast_window_end": time_series_info.forecast_window_end,
                "series_id_columns": time_series_info.multiseries_id_columns or [],
            }
        except dr.errors.ClientError as e:
            print(
                f"Note: time series info unavailable: {e}",
                file=sys.stderr,
            )

    return {
        "deployment_id": deployment_id,
        "model_type": model.target_type,
        "target": model.target_name,
        "target_type": model.target_type,
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
