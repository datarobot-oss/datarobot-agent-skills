#!/usr/bin/env python3
"""
Start AutoML training for a project.

Usage:
    python start_training.py <project_id> [mode]

Modes: Quick, Comprehensive, Manual (default: Quick)
"""

import sys
import json
import os
import datarobot as dr


def start_training(project_id: str, mode: str = "Quick") -> dict:
    """
    Start AutoML training for a project.

    Args:
        project_id: The project ID
        mode: Training mode - "Quick", "Comprehensive", or "Manual"

    Returns:
        Training job information
    """
    # Initialize client
    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )

    project = dr.Project.get(project_id)

    # Set training mode
    if mode == "Quick":
        project.start(autopilot_on=True, max_wait=3600)
    elif mode == "Comprehensive":
        project.start(autopilot_on=True, max_wait=7200)
    else:  # Manual
        project.start(autopilot_on=False)

    return {
        "project_id": project_id,
        "status": project.status,
        "mode": mode,
        "message": f"Training started in {mode} mode",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python start_training.py <project_id> [mode]", file=sys.stderr)
        print("Modes: Quick, Comprehensive, Manual", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "Quick"

    try:
        result = start_training(project_id, mode)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
