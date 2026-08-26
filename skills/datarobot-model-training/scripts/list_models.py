#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
List trained models for a project.

Usage:
    python list_models.py <project_id> [sort_by]

Sort options: AUC, RMSE, accuracy (default: by validation score)
"""

import json
import sys

import datarobot as dr


def list_models(project_id: str, sort_by: str = "validation") -> dict:
    """
    List trained models for a project.

    Args:
        project_id: The project ID
        sort_by: Sort option - "validation", "AUC", "RMSE", etc.

    Returns:
        List of models with metrics
    """
    # Initialize client
    dr.Client()

    models = dr.Model.list(project_id)

    # Get model details with metrics
    model_list = []
    for model in models:
        try:
            metrics = model.metrics
            model_info = {
                "model_id": model.id,
                "model_type": model.model_type,
                "blueprint_id": model.blueprint_id,
                "metrics": metrics,
            }
            model_list.append(model_info)
        except dr.errors.ClientError:
            model_info = {
                "model_id": model.id,
                "model_type": model.model_type,
                "blueprint_id": model.blueprint_id,
            }
            model_list.append(model_info)

    # Sort models. model.metrics maps each metric to a dict of partition scores
    # (e.g. {"AUC": {"validation": 0.81, "crossValidation": 0.80, ...}}), so read
    # the validation score rather than treating the metric value as a scalar.
    def validation_score(model_info: dict, metric: str, default: float) -> float:
        scores = (model_info.get("metrics") or {}).get(metric)
        if not isinstance(scores, dict):
            return default
        score = scores.get("validation")
        # A partition key can exist with a null score; keep the sort key numeric.
        return default if score is None else score

    if sort_by == "AUC" and model_list:
        model_list.sort(key=lambda x: validation_score(x, "AUC", 0), reverse=True)
    elif sort_by == "RMSE" and model_list:
        model_list.sort(key=lambda x: validation_score(x, "RMSE", float("inf")))

    return {
        "project_id": project_id,
        "model_count": len(model_list),
        "models": model_list,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python list_models.py <project_id> [sort_by]", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    sort_by = sys.argv[2] if len(sys.argv) > 2 else "validation"

    result = list_models(project_id, sort_by)
    print(json.dumps(result, indent=2))
