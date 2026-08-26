#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Upload a dataset file to DataRobot.

Usage:
    python upload_dataset.py <file_path> <dataset_name> [use_case_id]

Supports CSV, Parquet, and other formats. Optionally links the dataset to
an existing Use Case so it isn't orphaned in the DataRobot UI.
"""

import json
import os
import sys

import datarobot as dr


def upload_dataset(
    file_path: str, dataset_name: str, use_case_id: str | None = None
) -> dict:
    """
    Upload a dataset file to DataRobot.

    Args:
        file_path: Path to the dataset file (CSV, Parquet, etc.)
        dataset_name: Name for the dataset
        use_case_id: Optional existing Use Case ID to link the dataset to

    Returns:
        Dataset information including dataset_id
    """
    # Initialize client
    dr.Client()

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    use_cases = [dr.UseCase.get(use_case_id)] if use_case_id else None

    # Upload dataset
    dataset = dr.Dataset.create_from_file(
        file_path=file_path, name=dataset_name, use_cases=use_cases
    )

    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "file_path": file_path,
        "use_case_id": use_case_id,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python upload_dataset.py <file_path> <dataset_name> [use_case_id]",
            file=sys.stderr,
        )
        sys.exit(1)

    file_path = sys.argv[1]
    dataset_name = sys.argv[2]
    use_case_id = sys.argv[3] if len(sys.argv) > 3 else None

    result = upload_dataset(file_path, dataset_name, use_case_id)
    print(json.dumps(result, indent=2))
