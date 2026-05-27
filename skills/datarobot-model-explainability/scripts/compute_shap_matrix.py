#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Compute a ShapMatrix for a DataRobot model and export to CSV or DataFrame.

Usage:
    python compute_shap_matrix.py --model-id <model_id> [--source validation] [--output out.csv]
    python compute_shap_matrix.py --model-id <model_id> --data-slice-id <slice_id>
    python compute_shap_matrix.py --model-id <model_id> --source externalTestSet \
        --dataset-path ./data/scoring.csv --output out.csv
    python compute_shap_matrix.py --model-id <model_id> --list-existing
"""

import argparse
import os
from typing import Any

import pandas as pd
import datarobot as dr
from datarobot.insights import ShapMatrix


def compute_shap_matrix(
    model_id: str,
    source: str = "validation",
    dataset_path: str | None = None,
    output_path: str | None = None,
    data_slice_id: str | None = None,
    quick_compute: bool | None = None,
) -> Any:
    external_dataset_id: str | None = None
    if source == "externalTestSet":
        if not dataset_path:
            raise ValueError("--dataset-path required when source=externalTestSet")
        print(f"Uploading dataset: {dataset_path}")
        dataset = dr.Dataset.upload(dataset_path)
        external_dataset_id = dataset.id
        print(f"  Dataset ID: {external_dataset_id}")

    print(f"Computing ShapMatrix: model={model_id!r} source={source!r} ...")
    result = ShapMatrix.create(
        entity_id=model_id,
        source=source,
        data_slice_id=data_slice_id,
        external_dataset_id=external_dataset_id,
        quick_compute=quick_compute,
    )

    print(f"  Features:   {len(result.columns)}")
    print(f"  Rows:       {len(result.matrix)}")
    print(f"  Base value: {result.base_value:.6f}")
    print(f"  Link:       {result.link_function}")

    if output_path:
        df = pd.DataFrame(result.matrix, columns=result.columns)
        df.to_csv(output_path, index=False)
        print(f"  Exported to: {output_path}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute DataRobot ShapMatrix")
    parser.add_argument("--model-id", required=True)
    parser.add_argument(
        "--source",
        default="validation",
        choices=["validation", "crossValidation", "holdout", "externalTestSet"],
    )
    parser.add_argument("--data-slice-id", default=None)
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--full-compute", action="store_true")
    parser.add_argument("--list-existing", action="store_true")
    args = parser.parse_args()

    dr.Client(
        token=os.environ["DATAROBOT_API_TOKEN"],
        endpoint=os.environ.get(
            "DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2"
        ),
    )

    if args.list_existing:
        matrices = ShapMatrix.list(entity_id=args.model_id)
        print(f"Found {len(matrices)} existing ShapMatrix computation(s):")
        for m in matrices:
            print(
                f"  source={m.source}  features={len(m.columns)}  rows={len(m.matrix)}"
            )
        return

    compute_shap_matrix(
        model_id=args.model_id,
        source=args.source,
        dataset_path=args.dataset_path,
        output_path=args.output,
        data_slice_id=args.data_slice_id,
        quick_compute=False if args.full_compute else None,
    )


if __name__ == "__main__":
    main()
