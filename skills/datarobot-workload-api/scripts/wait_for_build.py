# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Poll a server-side artifact image build until the image is deployable.

IMPORTANT: only COMPLETED means the image is pushed to the registry and
deployable. BUILT is an intermediate state — the image has been built
locally but NOT yet pushed.  Scheduling a workload on a BUILT artifact
returns `422 runtime_image_uri ... None` because the registry can't
resolve the imageUri yet.  This script waits for COMPLETED specifically;
BUILT keeps polling.

Build progression: pending → in-progress → BUILT (built, not yet pushed)
→ COMPLETED (pushed, deployable). Lowercase variants (`completed`,
`failed`) from the C2W flow are normalized to uppercase before
comparison.

Reads DATAROBOT_ENDPOINT (must include /api/v2) and DATAROBOT_API_TOKEN
from the environment.  Exits 0 on COMPLETED, 2 on FAILED or CANCELLED
(prints last 2KB of build logs to stderr), 3 on timeout.

Usage:
    python wait_for_build.py <artifact_id> <build_id> [--timeout SECONDS] [--interval SECONDS]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, cast

import httpx

# Only COMPLETED means the image is pushed to the registry and deployable.
# BUILT is intermediate (built locally, not yet pushed) — keep polling.
SUCCESS = {"COMPLETED"}
FAILURE = {"FAILED", "CANCELLED"}

Headers = dict[str, str]
Json = dict[str, Any]


def wait_for_build(
    base: str,
    headers: Headers,
    artifact_id: str,
    build_id: str,
    timeout: int,
    interval: int,
) -> Json:
    deadline = time.time() + timeout
    last_status: str | None = None
    while time.time() < deadline:
        r = httpx.get(
            f"{base}/artifacts/{artifact_id}/builds/{build_id}/",
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        b = cast(Json, r.json())
        status = (b.get("status") or "").upper()
        if status != last_status:
            print(
                f"[{int(time.time() - (deadline - timeout)):>4}s] build status: {status}",
                flush=True,
            )
            last_status = status
        if status in SUCCESS:
            return b
        if status in FAILURE:
            logs = httpx.get(
                f"{base}/artifacts/{artifact_id}/builds/{build_id}/logs/",
                headers=headers,
                timeout=30,
            ).text
            print(f"--- last 2KB of build logs ---\n{logs[-2000:]}", file=sys.stderr)
            raise RuntimeError(f"Build {build_id} {status}")
        time.sleep(interval)
    raise TimeoutError(
        f"Build {build_id} did not finish within {timeout}s (last status: {last_status})"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("artifact_id")
    p.add_argument("build_id")
    p.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Total poll budget in seconds (default: 1800)",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Poll interval in seconds (default: 15)",
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
        b = wait_for_build(
            base, headers, args.artifact_id, args.build_id, args.timeout, args.interval
        )
    except RuntimeError as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 2
    except TimeoutError as e:
        print(f"TIMEOUT: {e}", file=sys.stderr)
        return 3

    print(
        f"\nBUILD COMPLETED — image pushed to the registry. "
        f"Artifact's imageUri is now populated; GET /artifacts/{args.artifact_id}/ to confirm "
        f"before scheduling a workload."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
