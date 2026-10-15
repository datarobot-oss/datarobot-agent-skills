#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Create a new DataRobot project from a dataset.

Usage:
    python create_project.py <dataset_id> <project_name> [target_column] [use_case_id]

Creates a project, optionally sets the target, and optionally links the
project to an existing Use Case so it isn't orphaned in the DataRobot UI.
"""

import json
import sys

import datarobot as dr


def create_project(
    dataset_id: str,
    project_name: str,
    target_column: str | None = None,
    use_case_id: str | None = None,
) -> dict:
    """
    Create a new DataRobot project from a dataset.

    Args:
        dataset_id: The dataset ID
        project_name: Name for the project
        target_column: Optional target column name
        use_case_id: Optional existing Use Case ID to link the project to

    Returns:
        Project information
    """
    # Initialize client
    dr.Client()

    use_case = dr.UseCase.get(use_case_id) if use_case_id else None

    # Create project
    project = dr.Project.create_from_dataset(
        dataset_id=dataset_id, project_name=project_name, use_case=use_case
    )

    result = {
        "project_id": project.id,
        "project_name": project.project_name,
        "stage": project.stage,
        "dataset_id": dataset_id,
        "use_case_id": use_case_id,
    }

    # Set target and start AutoPilot if a target was provided.
    # analyze_and_model() replaces the deprecated set_target() in SDK 3.x and both
    # sets the target and launches AutoPilot in one call.
    if target_column:
        try:
            project.analyze_and_model(
                target=target_column, mode=dr.AUTOPILOT_MODE.QUICK, worker_count=-1
            )
            result["target"] = target_column
            result["target_set"] = True
            # AutoPilot has advanced the project past "aim"; refresh the reported stage.
            result["stage"] = project.stage
        except (
            dr.errors.AppPlatformError,
            dr.errors.AsyncTimeoutError,
            dr.errors.AsyncProcessUnsuccessfulError,
        ) as e:
            result["target_set_error"] = str(e)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python create_project.py <dataset_id> <project_name> "
            "[target_column] [use_case_id]",
            file=sys.stderr,
        )
        sys.exit(1)

    dataset_id = sys.argv[1]
    project_name = sys.argv[2]
    target_column = sys.argv[3] if len(sys.argv) > 3 else None
    use_case_id = sys.argv[4] if len(sys.argv) > 4 else None

    result = create_project(dataset_id, project_name, target_column, use_case_id)
    print(json.dumps(result, indent=2))
