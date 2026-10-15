#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Start AutoML training for a project.

Usage:
    python start_training.py <project_id> <target> [mode]

Modes: Quick, Comprehensive, Manual (default: Quick)
"""

import json
import sys

import datarobot as dr


MODE_MAP = {
    "Quick": dr.AUTOPILOT_MODE.QUICK,
    "Comprehensive": dr.AUTOPILOT_MODE.COMPREHENSIVE,
    "Manual": dr.AUTOPILOT_MODE.MANUAL,
}


def start_training(project_id: str, target: str, mode: str = "Quick") -> dict:
    """
    Set the target and start AutoML training for a project.

    Args:
        project_id: The project ID
        target: The target column to model
        mode: Training mode - "Quick", "Comprehensive", or "Manual"

    Returns:
        Training job information
    """
    # Initialize client
    dr.Client()

    project = dr.Project.get(project_id)

    # analyze_and_model() sets the target and launches AutoPilot in the given mode.
    # (It replaces the older set_target()/start() calls; Manual mode sets the
    # target without auto-running blueprints.)
    project.analyze_and_model(
        target=target,
        mode=MODE_MAP.get(mode, dr.AUTOPILOT_MODE.QUICK),
        worker_count=-1,
    )

    return {
        "project_id": project_id,
        "target": target,
        "stage": project.stage,
        "mode": mode,
        "message": f"Training started for target '{target}' in {mode} mode",
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python start_training.py <project_id> <target> [mode]",
            file=sys.stderr,
        )
        print("Modes: Quick, Comprehensive, Manual", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    target = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "Quick"

    result = start_training(project_id, target, mode)
    print(json.dumps(result, indent=2))
