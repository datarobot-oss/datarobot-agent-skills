#!/usr/bin/env python3
"""
Make a prediction from a deployment using the SDK-supported batch API.

Usage:
    python make_prediction.py <deployment_id> <data_json>

Where data_json is a JSON object with feature values.
"""

import sys
import json
import os
import datarobot as dr
import pandas as pd


def make_prediction(deployment_id: str, data: dict) -> dict:
    """
    Make a prediction (single-row batch prediction).

    Args:
        deployment_id: The deployment ID
        data: Dictionary with feature values

    Returns:
        Prediction results
    """
    # Initialize client
    _client = dr.Client(
        token=os.getenv("DATAROBOT_API_TOKEN"),
        endpoint=os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com"),
    )

    deployment = dr.Deployment.get(deployment_id)

    # SDK v3.10.0 does not expose Deployment.predict(); use predict_batch with a 1-row DataFrame.
    df = pd.DataFrame([data])
    predictions_df = deployment.predict_batch(df)

    return {
        "deployment_id": deployment_id,
        "predictions": predictions_df.to_dict(orient="records"),
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python make_prediction.py <deployment_id> <data_json>",
            file=sys.stderr,
        )
        print(
            'Example: python make_prediction.py abc123 \'{"feature1": 10, "feature2": 20}\'',
            file=sys.stderr,
        )
        sys.exit(1)

    deployment_id = sys.argv[1]
    data_json = sys.argv[2]

    try:
        data = json.loads(data_json)
        result = make_prediction(deployment_id, data)
        print(json.dumps(result, indent=2))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
