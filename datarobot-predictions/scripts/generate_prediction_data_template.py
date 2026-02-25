#!/usr/bin/env python3
"""
Generate a CSV template for prediction data.

Usage:
    python generate_prediction_data_template.py <deployment_id> [n_rows] [output_file]

Generates a CSV template with all required columns and sample values.
"""

import sys
import csv
import os
import datarobot as dr


def generate_prediction_data_template(
    deployment_id: str, n_rows: int = 1, output_file: str = None
) -> str:
    """
    Generate a CSV template for prediction data.

    Args:
        deployment_id: The deployment ID
        n_rows: Number of template rows to generate (default: 1)
        output_file: Optional output file path (default: prints to stdout)

    Returns:
        CSV template content
    """
    # Initialize client
    client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )

    # Get deployment features
    deployment = dr.Deployment.get(deployment_id)
    model = dr.Model.get(deployment.model["id"])
    features = model.get_features()

    # Filter out target feature
    prediction_features = [f for f in features if f.name != model.target_name]

    # Generate template rows with sample values
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[f.name for f in prediction_features])
    writer.writeheader()

    # Generate sample rows based on feature types
    for i in range(n_rows):
        row = {}
        for feature in prediction_features:
            if feature.feature_type == "Numeric":
                row[feature.name] = 0.0
            elif feature.feature_type == "Categorical":
                row[feature.name] = "sample_category"
            elif feature.feature_type == "Text":
                row[feature.name] = "sample text"
            elif feature.feature_type == "Date":
                row[feature.name] = "2024-01-01"
            else:
                row[feature.name] = ""
        writer.writerow(row)

    csv_content = output.getvalue()

    # Add metadata comments
    metadata_comments = f"""# Prediction Data Template for Deployment: {deployment_id}
# Model: {model.project_name}
# Target: {model.target_name}
# Generated: {n_rows} template rows
# 
# Instructions:
# 1. Fill in the values for each feature
# 2. Ensure data types match feature types
# 3. Use validate_prediction_data.py to check before submitting
#
"""

    full_content = metadata_comments + csv_content

    if output_file:
        with open(output_file, "w") as f:
            f.write(full_content)
        return f"Template written to {output_file}"
    else:
        return full_content


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python generate_prediction_data_template.py <deployment_id> [n_rows] [output_file]",
            file=sys.stderr,
        )
        sys.exit(1)

    deployment_id = sys.argv[1]
    n_rows = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    output_file = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        result = generate_prediction_data_template(deployment_id, n_rows, output_file)
        print(result)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
