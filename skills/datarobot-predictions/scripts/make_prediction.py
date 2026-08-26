#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Make a prediction from a deployment, optionally with prediction explanations.

Usage:
    python make_prediction.py <deployment_id> <data_json> [options]

Where <data_json> is either:
    - a JSON object with feature values (single row), or
    - a JSON array of objects (multiple rows).

Options:
    --max-explanations N        Number of top explanations per row (0 disables, default 0).
    --max-ngram-explanations N  Cap text-segment explanations per row (text models only).
    --threshold-high X          Only explain rows with prediction probability above X (0-1).
    --threshold-low X           Only explain rows with prediction probability below X (0-1).
    --explanation-algorithm A   'shap' or 'xemp' (omit to use deployment default).
    --passthrough-columns COLS  'all' or comma-separated input columns to copy through.

Examples:
    # Plain prediction
    python make_prediction.py abc123 '{"feature1": 10, "feature2": 20}'

    # Top-3 SHAP explanations per row
    python make_prediction.py abc123 '{"feature1": 10}' --max-explanations 3 \\
        --explanation-algorithm shap

When --max-explanations > 0, each row in the output includes an `explanations` list
of {feature, value, strength, qualitative_strength} entries describing why the model
produced that prediction.
"""

import argparse
import json
import sys

import datarobot as dr
import pandas as pd
from datarobot_predict.deployment import predict as dr_predict


def make_prediction(
    deployment_id: str,
    data,
    *,
    max_explanations: int = 0,
    max_ngram_explanations: int | None = None,
    threshold_high: float | None = None,
    threshold_low: float | None = None,
    explanation_algorithm: str | None = None,
    passthrough_columns: str | None = None,
) -> dict:
    """Score `data` against `deployment_id`, optionally returning prediction explanations."""
    dr.Client()

    deployment = dr.Deployment.get(deployment_id)

    rows = data if isinstance(data, list) else [data]
    df = pd.DataFrame(rows)

    predict_kwargs = {"deployment": deployment, "data_frame": df}
    if max_explanations and max_explanations > 0:
        predict_kwargs["max_explanations"] = max_explanations
    if max_ngram_explanations is not None:
        predict_kwargs["max_ngram_explanations"] = max_ngram_explanations
    if threshold_high is not None:
        predict_kwargs["threshold_high"] = threshold_high
    if threshold_low is not None:
        predict_kwargs["threshold_low"] = threshold_low
    if explanation_algorithm is not None:
        predict_kwargs["explanation_algorithm"] = explanation_algorithm
    if passthrough_columns is not None:
        predict_kwargs["passthrough_columns"] = (
            "all"
            if passthrough_columns == "all"
            else {c.strip() for c in passthrough_columns.split(",")}
        )

    result = dr_predict(**predict_kwargs)
    predictions_df = result.dataframe

    return {
        "deployment_id": deployment_id,
        "row_count": len(predictions_df),
        "predictions": predictions_df.to_dict(orient="records"),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("deployment_id")
    parser.add_argument(
        "data_json", help="JSON object (single row) or JSON array (multiple rows)"
    )
    parser.add_argument("--max-explanations", type=int, default=0)
    parser.add_argument("--max-ngram-explanations", type=int, default=None)
    parser.add_argument("--threshold-high", type=float, default=None)
    parser.add_argument("--threshold-low", type=float, default=None)
    parser.add_argument(
        "--explanation-algorithm", choices=["shap", "xemp"], default=None
    )
    parser.add_argument("--passthrough-columns", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    try:
        data = json.loads(args.data_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    result = make_prediction(
        args.deployment_id,
        data,
        max_explanations=args.max_explanations,
        max_ngram_explanations=args.max_ngram_explanations,
        threshold_high=args.threshold_high,
        threshold_low=args.threshold_low,
        explanation_algorithm=args.explanation_algorithm,
        passthrough_columns=args.passthrough_columns,
    )
    print(json.dumps(result, indent=2, default=str))
