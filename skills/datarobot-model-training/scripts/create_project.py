#!/usr/bin/env python3
"""
Create a new DataRobot project from a dataset.

Usage:
    python create_project.py <dataset_id> <project_name> [target_column]

Creates a project and optionally sets the target.
"""

import sys
import json
import os
import datarobot as dr


def create_project(
    dataset_id: str, project_name: str, target_column: str = None
) -> dict:
    """
    Create a new DataRobot project from a dataset.

    Args:
        dataset_id: The dataset ID
        project_name: Name for the project
        target_column: Optional target column name

    Returns:
        Project information
    """
    # Initialize client
    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )

    # Create project
    project = dr.Project.create_from_dataset(
        dataset_id=dataset_id, project_name=project_name
    )

    result = {
        "project_id": project.id,
        "project_name": project.project_name,
        "status": project.status,
        "dataset_id": dataset_id,
    }

    # Set target if provided
    if target_column:
        try:
            project.set_target(target=target_column, mode=dr.AUTOPILOT_MODE.QUICK)
            result["target"] = target_column
            result["target_set"] = True
        except Exception as e:
            result["target_set_error"] = str(e)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python create_project.py <dataset_id> <project_name> [target_column]",
            file=sys.stderr,
        )
        sys.exit(1)

    dataset_id = sys.argv[1]
    project_name = sys.argv[2]
    target_column = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        result = create_project(dataset_id, project_name, target_column)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
