# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Poll a workload's active artifact replacement until it completes or fails.

GET /workloads/{id}/replacement/ returns 404 when there is no active
replacement.  This script treats 404 mid-poll as "completed and cleared" (the
platform removes the record after settling) and returns the last-seen status
to the caller.  If 404 is the very first response (no replacement was ever
started), the script exits with a clear "no active replacement" message.

Reads DATAROBOT_ENDPOINT (must include /api/v2) and DATAROBOT_API_TOKEN from
the environment.  Exits 0 on completed, 2 on failed, 3 on timeout, 4 if no
replacement was active at start.

Usage:
    python wait_for_replacement.py <workload_id> [--timeout SECONDS] [--interval SECONDS]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, cast

import httpx

Headers = dict[str, str]
Json = dict[str, Any]


def wait_for_replacement(
    base: str,
    headers: Headers,
    wid: str,
    timeout: int,
    interval: int,
) -> tuple[str, Json | None]:
    """Returns (outcome, last_seen_record).  outcome ∈ {completed, failed, gone, timeout}."""
    deadline = time.time() + timeout
    last: Json | None = None
    while time.time() < deadline:
        r = httpx.get(
            f"{base}/workloads/{wid}/replacement/", headers=headers, timeout=30
        )
        if r.status_code == 404:
            return ("gone" if last is None else "completed"), last
        r.raise_for_status()
        last = cast(Json, r.json())
        status = last.get("status")
        print(
            f"[{int(time.time() - (deadline - timeout)):>4}s] replacement status: {status}",
            flush=True,
        )
        if status == "completed":
            return "completed", last
        if status == "failed":
            return "failed", last
        time.sleep(interval)
    return "timeout", last


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("workload_id")
    p.add_argument(
        "--timeout",
        type=int,
        default=1200,
        help="Total poll budget in seconds (default: 1200)",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=20,
        help="Poll interval in seconds (default: 20)",
    )
    args = p.parse_args()

    base = os.environ.get("DATAROBOT_ENDPOINT", "").rstrip("/")
    token = os.environ.get("DATAROBOT_API_TOKEN", "")
    if not base or not token:
        print(
            "DATAROBOT_ENDPOINT and DATAROBOT_API_TOKEN must be set.", file=sys.stderr
        )
        return 1
    headers = {"Authorization": f"Bearer {token}"}

    outcome, last = wait_for_replacement(
        base, headers, args.workload_id, args.timeout, args.interval
    )

    if outcome == "gone":
        print(
            f"No active replacement on workload {args.workload_id} (404 at start). "
            f"Did you intend to POST /workloads/{args.workload_id}/replacement/ first?"
        )
        return 4
    if outcome == "completed":
        print("Replacement completed.")
        if last:
            print(json.dumps(last, indent=2, default=str)[:600])
        return 0
    if outcome == "failed":
        print(
            f"Replacement FAILED — workload reverted to the old artifact. "
            f"Diagnose with: python {Path(__file__).parent / 'diagnose_workload.py'} {args.workload_id}",
            file=sys.stderr,
        )
        if last:
            print(json.dumps(last, indent=2, default=str)[:600], file=sys.stderr)
        return 2
    # timeout
    print(
        f"TIMEOUT — replacement on {args.workload_id} did not settle within {args.timeout}s.",
        file=sys.stderr,
    )
    if last:
        print(f"Last seen: {json.dumps(last, default=str)[:300]}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(main())
