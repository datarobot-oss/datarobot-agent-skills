#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Generate a CSV template for prediction data.

Usage:
    python generate_prediction_data_template.py <deployment_id> [n_rows] [output_file]

Generates a CSV template with all required columns and sample values.
"""

import csv
import sys
from datetime import datetime

import datarobot as dr


def generate_prediction_data_template(
    deployment_id: str, n_rows: int = 1, output_file: str | None = None
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
    dr.Client()

    # Get deployment features (list of plain dicts with keys name, feature_type,
    # importance, date_format, known_in_advance)
    deployment = dr.Deployment.get(deployment_id)
    try:
        features = deployment.get_features()
    except dr.errors.ClientError as e:
        sys.exit(f"Deployment feature metadata unavailable ({e})")
    target_name = deployment.model.get(
        "target_name"
    )  # None for unsupervised/anomaly deployments

    # Filter out target feature
    prediction_features = [f for f in features if f["name"] != target_name]
    if not prediction_features:
        sys.exit(
            "No feature metadata available for this deployment (custom/unstructured "
            "models do not publish a feature list); cannot generate a template."
        )

    # Look up real training values: categorical levels and numeric ranges. Only
    # DataRobot-built models have a backing project; custom-model deployments — and
    # deployments whose training project was since deleted — fall back to the type
    # placeholders below.
    project_id = deployment.model.get("project_id")
    stats_note = ""
    if project_id:
        try:
            dr.Project.get(project_id)
        except dr.errors.ClientError:
            project_id = None
            stats_note = (
                "# Note: training statistics unavailable (project not accessible); "
                "values below are type placeholders\n"
            )
    categorical_levels: dict[str, list[str]] = {}
    level_notes: dict[str, str] = {}
    numeric_stats: dict[str, dict[str, float]] = {}
    if project_id:
        for feature in prediction_features:
            try:
                if feature["feature_type"] in ("Categorical", "Boolean"):
                    dr_feature = dr.Feature.get(project_id, feature["name"])
                    # Each bin is {"label": <level>, "count": ..., "target": ...};
                    # high-cardinality features get at most 60 bins by default.
                    labels = [b["label"] for b in dr_feature.get_histogram().plot]
                    # The histogram injects aggregate pseudo-buckets that are NOT
                    # real levels: "=All Other=" (levels beyond the bin cap) and
                    # "==Missing==" (the feature had NAs in training). Filter them
                    # out, but surface what they tell us in the header notes.
                    levels = [
                        label
                        for label in labels
                        if not (str(label).startswith("=") and str(label).endswith("="))
                    ]
                    if levels:
                        categorical_levels[feature["name"]] = levels
                    notes = []
                    if "=All Other=" in labels and dr_feature.unique_count:
                        notes.append(
                            f"top {len(levels)} of {dr_feature.unique_count} levels"
                        )
                    if "==Missing==" in labels:
                        notes.append("missing allowed - leave blank")
                    if notes:
                        level_notes[feature["name"]] = "; ".join(notes)
                elif feature["feature_type"] in ("Numeric", "Percentage"):
                    stats = dr.Feature.get(project_id, feature["name"])
                    if isinstance(stats.median, (int, float)):
                        numeric_stats[feature["name"]] = {
                            "min": stats.min,
                            "max": stats.max,
                            "median": stats.median,
                        }
            except Exception:
                pass  # keep the type placeholder for this feature

    # Generate template rows with sample values
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[f["name"] for f in prediction_features])
    writer.writeheader()

    # Generate sample rows based on feature types
    for i in range(n_rows):
        row = {}
        for feature in prediction_features:
            ftype = feature["feature_type"]
            if ftype in ("Numeric", "Percentage"):
                stats = numeric_stats.get(feature["name"])
                row[feature["name"]] = stats["median"] if stats else 0.0
            elif ftype in ("Categorical", "Boolean"):
                levels = categorical_levels.get(feature["name"])
                if levels:
                    row[feature["name"]] = levels[i % len(levels)]
                else:
                    row[feature["name"]] = (
                        "sample_category" if ftype == "Categorical" else "0"
                    )
            elif ftype == "Text":
                row[feature["name"]] = "sample text"
            elif ftype == "Date":
                # Render the sample in the format the deployment expects
                fmt = feature.get("date_format") or "%Y-%m-%d"
                row[feature["name"]] = datetime(2024, 1, 15, 12, 30, 45).strftime(fmt)
            elif ftype in ("Image", "Document"):
                row[feature["name"]] = "path/to/file"
            else:
                row[feature["name"]] = ""
        writer.writerow(row)

    csv_content = output.getvalue()

    # Add metadata comments
    level_comments = "".join(
        f"# Valid values for {name}: {', '.join(levels)}"
        + (f" ({level_notes[name]})" if name in level_notes else "")
        + "\n"
        for name, levels in categorical_levels.items()
    ) + "".join(
        f"# Range for {name}: {s['min']} to {s['max']} (median {s['median']})\n"
        for name, s in numeric_stats.items()
    )
    metadata_comments = f"""# Prediction Data Template for Deployment: {deployment_id}
# Model: {deployment.model.get("project_name", "unknown")}
# Target: {target_name}
# Generated: {n_rows} template rows
{stats_note}{level_comments}#
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

    result = generate_prediction_data_template(deployment_id, n_rows, output_file)
    print(result)
