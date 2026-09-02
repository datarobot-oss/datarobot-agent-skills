#!/usr/bin/env python3
# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check risk_management_mitigations.yaml for drift against the live DataRobot
risk-management mitigation-method catalog.

Run this periodically, not on every gap-analysis invocation, since it needs
DATAROBOT_API_TOKEN/DATAROBOT_ENDPOINT and a DataRobot org with the (not yet
GA) risk-management feature enabled:

  uv run scripts/validate_risk_management_mapping.py

Exits 0 with no drift, 1 with drift found, 2 on a setup/connectivity problem.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from gap_analysis import risk_management as rm  # noqa: E402  (path setup above)


def main() -> int:
    client = rm.get_client()
    if client is None:
        print(
            "error: DATAROBOT_API_TOKEN/DATAROBOT_ENDPOINT not set.",
            file=sys.stderr,
        )
        return 2

    catalog = rm.fetch_mitigation_catalog(client)
    if catalog is None:
        print(
            "error: could not fetch the mitigation-method catalog "
            "(the feature may not be enabled for this org, or the API has moved).",
            file=sys.stderr,
        )
        return 2

    metadata = rm.load_mitigation_metadata()
    drift = rm.validate_metadata_against_catalog(metadata, catalog)

    if not drift["new_in_catalog"] and not drift["removed_from_catalog"]:
        print("risk_management_mitigations.yaml matches the live catalog. No drift.")
        return 0

    if drift["new_in_catalog"]:
        print("New mitigation types in the catalog, not yet in the metadata file:")
        for t in drift["new_in_catalog"]:
            print(f"  - {t}")
    if drift["removed_from_catalog"]:
        print("Metadata file references types no longer in the catalog:")
        for t in drift["removed_from_catalog"]:
            print(f"  - {t}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
