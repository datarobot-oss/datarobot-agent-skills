#!/usr/bin/env python3
"""
Validate prediction data for a deployment.

Usage:
    python validate_prediction_data.py <deployment_id> <file_path>

Returns validation report with errors, warnings, and info messages.
"""

import sys
import csv
import json
import os
import datarobot as dr


def validate_prediction_data(deployment_id: str, file_path: str) -> dict:
    """
    Validate prediction data for a deployment.

    Args:
        deployment_id: The deployment ID
        file_path: Path to CSV file to validate

    Returns:
        Validation report with errors, warnings, and info
    """
    # Initialize client
    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )

    deployment = dr.Deployment.get(deployment_id)
    model = dr.Model.get(deployment.model["id"])
    features = model.get_features()

    # Get required features (exclude target)
    required_features = {
        f.name: f.feature_type for f in features if f.name != model.target_name
    }

    # Read CSV data
    if not os.path.exists(file_path):
        return {"valid": False, "errors": [f"File not found: {file_path}"]}

    with open(file_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return {"valid": False, "errors": ["CSV file is empty"]}

    # Validate
    errors = []
    warnings = []
    info = []

    # Check for missing required features
    csv_columns = set(rows[0].keys())
    missing_features = set(required_features.keys()) - csv_columns

    if missing_features:
        errors.append(
            f"Missing required features: {', '.join(sorted(missing_features))}"
        )

    # Check for extra columns
    extra_columns = csv_columns - set(required_features.keys())
    if extra_columns:
        info.append(
            f"Extra columns (will be ignored): {', '.join(sorted(extra_columns))}"
        )

    # Check data types (simplified - actual validation would be more thorough)
    for row_num, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
        for feature_name, feature_type in required_features.items():
            if feature_name in row:
                value = row[feature_name]
                if value == "":
                    warnings.append(f"Row {row_num}, {feature_name}: Empty value")
                elif feature_type == "Numeric" and value:
                    try:
                        float(value)
                    except ValueError:
                        errors.append(
                            f"Row {row_num}, {feature_name}: Expected numeric, got '{value}'"
                        )

    # Get feature importance for warnings
    try:
        feature_importance = model.get_feature_impact()
        low_importance_features = [
            fi["featureName"]
            for fi in feature_importance
            if fi.get("impactNormalized", 0) < 0.05
        ]

        missing_low_importance = missing_features & set(low_importance_features)
        if missing_low_importance:
            warnings.append(
                f"Missing low-importance features: {', '.join(sorted(missing_low_importance))}"
            )
    except Exception:
        pass

    return {
        "valid": len(errors) == 0,
        "deployment_id": deployment_id,
        "row_count": len(rows),
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "required_features": sorted(required_features.keys()),
        "provided_features": sorted(csv_columns),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python validate_prediction_data.py <deployment_id> <file_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    deployment_id = sys.argv[1]
    file_path = sys.argv[2]

    try:
        result = validate_prediction_data(deployment_id, file_path)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
