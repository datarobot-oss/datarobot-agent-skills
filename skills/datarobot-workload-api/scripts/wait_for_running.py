# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Poll a DataRobot workload until it reaches the `running` status.

Reads DATAROBOT_ENDPOINT (must include /api/v2) and DATAROBOT_API_TOKEN from
the environment.  Returns exit 0 once the workload is running, exit 2 if it
enters a terminal failure state, exit 3 on timeout.

Usage:
    python wait_for_running.py <workload_id> [--timeout SECONDS] [--interval SECONDS]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, cast

import httpx

TERMINAL_FAILURES = ("errored", "terminated")


def wait_for_running(
    base: str,
    headers: dict[str, str],
    workload_id: str,
    timeout: int,
    interval: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_status: str | None = None
    while time.time() < deadline:
        r = httpx.get(f"{base}/workloads/{workload_id}/", headers=headers, timeout=30)
        r.raise_for_status()
        w = cast(dict[str, Any], r.json())
        status = w.get("status")
        if status != last_status:
            print(
                f"[{int(time.time() - (deadline - timeout)):>4}s] status: {status}",
                flush=True,
            )
            last_status = status
        if status == "running":
            return w
        if status in TERMINAL_FAILURES:
            raise RuntimeError(
                f"Workload {workload_id} entered terminal state {status!r}. "
                f"Run: python scripts/diagnose_workload.py {workload_id}"
            )
        time.sleep(interval)
    raise TimeoutError(
        f"Workload {workload_id} did not reach 'running' within {timeout}s "
        f"(last status: {last_status})"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("workload_id")
    p.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Total poll budget in seconds (default: 300)",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Poll interval in seconds (default: 10)",
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

    try:
        w = wait_for_running(
            base, headers, args.workload_id, args.timeout, args.interval
        )
    except RuntimeError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 2
    except TimeoutError as e:
        print(f"TIMEOUT: {e}", file=sys.stderr)
        return 3

    print(f"\nRUNNING. endpoint: {w.get('endpoint')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
