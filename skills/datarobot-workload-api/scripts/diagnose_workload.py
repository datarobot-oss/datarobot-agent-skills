# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Run the full 5-step debug flow against a DataRobot workload and print a
structured diagnosis: status, lifecycle-event highlights, proton K8s detail,
and a recommended next step.

Reads DATAROBOT_ENDPOINT (must include /api/v2) and DATAROBOT_API_TOKEN from
the environment.

Usage:
    python diagnose_workload.py <workload_id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, cast

import httpx

CONSOLE_URL = "https://app.datarobot.com/console-nextgen/workloads/{wid}/overview"
FLAG_EVENT_TYPE_KEYWORDS = ("failed", "error", "kill", "oom", "backoff", "evict")

Headers = dict[str, str]
Json = dict[str, Any]


def get_workload(base: str, headers: Headers, wid: str) -> Json:
    r = httpx.get(f"{base}/workloads/{wid}/", headers=headers, timeout=30)
    r.raise_for_status()
    return cast(Json, r.json())


def get_error_logs(
    base: str, headers: Headers, wid: str, limit: int = 30
) -> list[Json]:
    r = httpx.get(
        f"{base}/otel/workload/{wid}/logs/",
        headers=headers,
        params={"level": "error", "limit": limit},
        timeout=30,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return cast(list[Json], r.json().get("data", []))


def get_events(base: str, headers: Headers, wid: str, limit: int = 20) -> list[Json]:
    r = httpx.get(
        f"{base}/workloads/{wid}/events/",
        headers=headers,
        params={"limit": limit},
        timeout=30,
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return cast(list[Json], r.json().get("data", []))


def list_protons(base: str, headers: Headers, wid: str) -> list[Json]:
    r = httpx.get(f"{base}/workloads/{wid}/protons/", headers=headers, timeout=30)
    r.raise_for_status()
    return cast(list[Json], r.json().get("data", []))


def get_proton_status_details(
    base: str, headers: Headers, wid: str, pid: str
) -> Json | None:
    r = httpx.get(
        f"{base}/workloads/{wid}/protons/{pid}/statusDetails/",
        headers=headers,
        timeout=30,
    )
    if r.status_code == 204 or not r.text:
        return None
    r.raise_for_status()
    return cast(Json, r.json())


def diagnose(base: str, headers: Headers, wid: str) -> Json:
    """Returns a dict with: status, summary, evidence, recommended_next_step."""
    w = get_workload(base, headers, wid)
    status = w.get("status", "unknown")

    findings: list[str] = []
    evidence: str | None = None

    # Step 1 — scan recent error-level application logs for obvious signals
    keywords = (
        "error",
        "exception",
        "traceback",
        "killed",
        "permission denied",
        "connection refused",
        "exec format error",
    )
    for record in get_error_logs(base, headers, wid, limit=30):
        message = (record.get("message") or "").strip()
        lower = message.lower()
        for kw in keywords:
            if kw in lower:
                evidence = message
                findings.append(f"error log matched keyword {kw!r}: {evidence[:200]}")
                break
        if evidence:
            break

    # Step 2 — flag noteworthy lifecycle events
    flagged_events: list[str] = []
    for ev in get_events(base, headers, wid, limit=30):
        ev_type = (ev.get("eventType") or "").lower()
        if any(k in ev_type for k in FLAG_EVENT_TYPE_KEYWORDS):
            details = json.dumps(ev.get("details") or {}, default=str)
            flagged_events.append(
                f"  [{(ev.get('timestamp') or '')[:19]}] "
                f"{ev.get('eventType', '?')}: {details[:200]}"
            )
            if not evidence:
                evidence = f"{ev.get('eventType')}: {details[:200]}"

    # Step 3/4 — drill into the active (or most recent) proton
    proton_summary: str | None = None
    proton_detail_summary: str | None = None
    protons = list_protons(base, headers, wid)
    if protons:
        target = next(
            (p for p in protons if p.get("role") == "active"),
            max(protons, key=lambda p: cast(str, p.get("createdAt", ""))),
        )
        proton_summary = (
            f"{len(protons)} proton(s); using {target.get('role', '?')} {target['id']}"
        )
        detail = get_proton_status_details(base, headers, wid, target["id"])
        if detail is None:
            proton_detail_summary = (
                "statusDetails returned 204 — proton still initializing"
            )
        else:
            overall = detail.get("overallStatus", {}) or {}
            replicas = detail.get("replicas", []) or []
            lines = [
                f"overallStatus.state = {overall.get('state', '?')}",
                f"overallStatus.summary = {(overall.get('summary') or '')[:200]}",
                f"replicas: {len(replicas)}",
            ]
            for rep in replicas[:3]:
                for c in rep.get("containers", []) or []:
                    lines.append(
                        f"  container {c.get('name', '?')}: status={c.get('status')} "
                        f"ready={c.get('ready')} restarts={c.get('restartCount')} "
                        f"image={(c.get('image') or '')[:80]}"
                    )
                for cond in rep.get("conditions", []) or []:
                    met = cond.get("value", cond.get("met"))
                    mark = "OK" if met else "--"
                    lines.append(f"  [{mark}] {cond.get('type', '?')}")
            proton_detail_summary = "\n".join(lines)
            if not evidence and overall.get("summary"):
                evidence = overall["summary"]

    # Recommendation
    if status == "running":
        recommendation = "Workload is running — nothing to debug here; pull telemetry if you need to look at request behavior."
    elif status in ("submitted", "provisioning", "launching"):
        recommendation = (
            "Workload is still coming up. Wait 30–60 seconds and re-run. "
            "If stuck > 5 min, check events + proton statusDetails (above)."
        )
    elif status == "errored":
        if not evidence:
            recommendation = (
                "errored with no specific signal in logs/events. Pull application logs "
                "(SKILL.md section 3: GET /otel/workload/<id>/logs/) for the underlying cause."
            )
        else:
            recommendation = (
                "errored. Fix the root cause flagged above. For image/spec/env-var changes use "
                "SKILL.md section 4 (artifact lifecycle); for replicas/memory/bundle changes use "
                "SKILL.md section 1 (PATCH /workloads/{id}/settings/)."
            )
    elif status in ("stopping", "stopped"):
        recommendation = "Workload is shutting down or stopped. Start it via POST /workloads/<id>/start/ if unintended."
    else:
        recommendation = f"Unhandled status {status!r}; check events above and the console URL below."

    return {
        "workload_id": wid,
        "status": status,
        "log_findings": findings,
        "events_flagged": flagged_events,
        "proton_summary": proton_summary,
        "proton_detail": proton_detail_summary,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def print_report(d: Json) -> None:
    print(f"Workload {d['workload_id']} — Diagnosis")
    print(f"  Status:           {d['status']}")
    if d["log_findings"]:
        print("  Error-log signals:")
        for line in d["log_findings"]:
            print(f"    - {line}")
    if d["events_flagged"]:
        print(f"  Flagged events ({len(d['events_flagged'])}):")
        for line in d["events_flagged"][:5]:
            print(line)
    if d["proton_summary"]:
        print(f"  Proton:           {d['proton_summary']}")
    if d["proton_detail"]:
        print("  Proton detail:")
        for line in d["proton_detail"].split("\n"):
            print(f"    {line}")
    if d["evidence"]:
        print(f"  Evidence:         {d['evidence'][:300]}")
    print(f"  Recommendation:   {d['recommendation']}")
    print(f"  Console:          {CONSOLE_URL.format(wid=d['workload_id'])}")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("workload_id")
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of human-readable text",
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

    diag = diagnose(base, headers, args.workload_id)
    if args.json:
        print(json.dumps(diag, indent=2, default=str))
    else:
        print_report(diag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
