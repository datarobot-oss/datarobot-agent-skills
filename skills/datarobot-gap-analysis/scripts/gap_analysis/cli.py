# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Command-line entrypoint: clone -> analyze -> report -> (optionally) fix."""

from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from .engine import analyze, fix
from .ingest import clone_repo
from .opencode import OpenCodeServer, OpenCodeWorkerClient, dr_available
from .report import render_report
from .report_html import render_html


_T0 = time.monotonic()


def _status(msg: str) -> None:
    """Timestamped status line on stderr: elapsed since process start."""
    m, s = divmod(int(time.monotonic() - _T0), 60)
    print(f"[{m:02d}:{s:02d}] {msg}", file=sys.stderr, flush=True)


def _after_path(html_path: str | None) -> str:
    """The filename for the post-fix report: '<name>-after<ext>' (default gap-report)."""
    p = Path(html_path or "gap-report.html")
    return str(p.with_name(p.stem + "-after" + (p.suffix or ".html")))


def _load_env_file(path: str) -> list[str]:
    """Load KEY=VALUE pairs from a dotenv file into os.environ. Returns the key names.

    Minimal, dependency-free: supports `export ` prefixes, # comments, blank lines,
    and surrounding quotes. Existing environment variables are NOT overridden, so an
    explicit `export` in the shell still wins.
    """
    loaded: list[str] = []
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"env file not found: {path}")
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not key:
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key not in os.environ:  # don't override an explicit shell export
            os.environ[key] = val
        loaded.append(key)
    return loaded


def _make_llm_client():
    """Return the LLM client for this run, or None to let the engine auto-detect.

    Preferred backend is `dr opencode`: a private server is started on a free
    port and every check attaches to it as a worker subprocess, authenticated
    through the CLI's own login. `GAP_LLM_BACKEND=litellm` (or a missing `dr`)
    falls back to direct gateway calls via litellm, which need
    DATAROBOT_API_TOKEN/DATAROBOT_ENDPOINT (or GAP_LLM_MODEL provider creds).
    The server is stopped at process exit, covering every CLI return path.
    """
    if os.environ.get("GAP_LLM_BACKEND", "opencode") != "opencode":
        return None
    if not dr_available():
        _status(
            "→ dr CLI not found; LLM checks fall back to direct API calls (litellm)."
        )
        return None
    server = OpenCodeServer()
    try:
        url = server.start()
    except Exception as e:  # noqa: BLE001
        _status(
            f"→ dr opencode server failed to start ({e}); "
            "falling back to direct API calls (litellm)."
        )
        return None
    atexit.register(server.stop)
    # A SIGTERM (timeout, orchestrator kill) must still run atexit hooks, or the
    # private server outlives the run.
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda signum, _frame: sys.exit(128 + signum))
    client = OpenCodeWorkerClient(url, cwd=server.workdir)
    _status(f"→ LLM checks run through dr opencode ({client.model}).")
    return client


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="gap-analysis",
        description="Find (and optionally fix) enterprise-readiness gaps in a repo.",
    )
    ap.add_argument("repo", help="GitHub URL or local path to a repository")
    ap.add_argument("--ref", help="branch/tag/commit to check out")
    ap.add_argument(
        "--policy", help="path to a policy YAML (deep-merged over defaults)"
    )
    ap.add_argument(
        "--out",
        help="write the Markdown report to this file, or into this directory as "
        "gap-report.md (default: stdout)",
    )
    ap.add_argument(
        "--html",
        metavar="PATH",
        help="path for the styled HTML report, which is always written "
        "(default: next to --out, else ./gap-report.html). A clickable file:// link is printed; "
        "the browser is only launched with --open",
    )
    ap.add_argument(
        "--open",
        action="store_true",
        help="open the HTML report(s) in the default browser after writing",
    )
    ap.add_argument(
        "--env-file",
        nargs="?",
        const=".env",
        metavar="PATH",
        help="load env vars (e.g. DATAROBOT_ENDPOINT/_API_TOKEN, GAP_LLM_MODEL) "
        "from a dotenv file before running (default: .env)",
    )
    ap.add_argument(
        "--no-llm",
        action="store_true",
        help="skip LLM checks: Layer 2 code reasoning entirely, and Layer 4's "
        "per-mitigation evidence assessment (required mitigations are still "
        "fetched from DataRobot risk-management and reported as not assessed). "
        "Layers 1 and 3 always run.",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=int(os.environ.get("GAP_WORKERS", "4")),
        help="parallel workers for Layer 2/4 LLM checks (default: 4, or $GAP_WORKERS)",
    )
    ap.add_argument(
        "--fix", action="store_true", help="apply fixes on a gap-fixes/* branch"
    )
    ap.add_argument(
        "--select", help="comma-separated condition ids to fix (default: all fixable)"
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="after --fix, re-analyze the fixed branch and write a post-fix HTML "
        "report with a before→after score and a deploy-readiness verdict",
    )
    args = ap.parse_args(argv)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    if args.env_file:
        try:
            keys = _load_env_file(args.env_file)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        _status(
            f"→ Loaded {len(keys)} var(s) from {args.env_file}: "
            f"{', '.join(sorted(keys)) or '(none)'}"
        )

    # Progress goes to stderr so stdout stays clean (report / piping unaffected).
    def progress(msg: str) -> None:
        _status(f"  … {msg}")

    _status(f"→ Cloning {args.repo} …")
    try:
        workspace = clone_repo(args.repo, args.ref)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 2

    llm_client = _make_llm_client() if not args.no_llm else None

    _status(
        "→ Analyzing (Layer 2/4 LLM checks run in parallel; use --no-llm to skip) …"
    )
    result, policy = analyze(
        workspace,
        args.policy,
        llm_client=llm_client,
        use_llm=not args.no_llm,
        progress=progress,
        max_workers=args.workers,
    )
    _status(
        f"→ Analysis complete — {len(result.findings)} gaps "
        f"({result.posture.get('recommendation', '')})."
    )
    report = render_report(result, repo=args.repo, policy=policy)

    out_path: Path | None = None
    if args.out:
        out_path = Path(args.out)
        if out_path.is_dir() or args.out.endswith(("/", os.sep)):
            out_path = out_path / "gap-report.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"✓ Markdown report: {out_path.resolve()}")
    elif not args.html:
        print(report)

    html_path = args.html or (
        str(out_path.with_suffix(".html")) if out_path else "gap-report.html"
    )
    final_findings = result.findings
    out = Path(html_path).resolve()
    out.write_text(render_html(result, repo=args.repo, policy=policy))
    print(f"✓ HTML report: {out.as_uri()}")
    if args.open:
        webbrowser.open(out.as_uri())

    if args.fix:
        selected = (
            set(s.strip() for s in args.select.split(",")) if args.select else None
        )
        _status(
            f"→ Applying fixes ({'selected: ' + ','.join(sorted(selected)) if selected else 'all auto-fixable'}) "
            "on a gap-fixes/* branch …"
        )
        summary = fix(
            workspace,
            result,
            policy,
            ts,
            llm_client=llm_client,
            selected_ids=selected,
            use_llm=not args.no_llm,
        )
        print("\n" + "=" * 60)
        print(
            f"Remediation: applied {summary['applied']}/{summary['attempted']} fixes "
            f"on branch {summary['branch']}"
        )
        for r in summary["results"]:
            mark = "✓" if r["status"] == "applied" else "•"
            risk = f" [{r['fix_risk']}]" if r.get("fix_risk") else ""
            print(f"  {mark} {r['condition_id']}{risk}: {r['message']}")
        if summary.get("held_back"):
            print(
                "\nHeld back (business-logic fixes — re-run with --select naming these "
                "ids to apply):"
            )
            for h in summary["held_back"]:
                print(f"  - {h['condition_id']} ({h.get('file') or 'repo-wide'})")
        if summary["followups"]:
            print("\nManual follow-ups:")
            for fu in summary["followups"]:
                print(f"  - {fu}")
        if summary["diff_stat"]:
            print("\n" + summary["diff_stat"])
        print(
            f"\nThe branch '{summary['branch']}' lives in the cloned workspace:\n  {workspace}"
        )
        print(f"  Inspect it with:  git -C {workspace} diff main")
        print(
            "\nNote: --fix patches the repo IN PLACE — it does not adopt the af-component "
            "stack. Re-platforming onto af-components is the migration path (RE-PLATFORM)."
        )
        if summary.get("unfixable_selected"):
            print(
                "Selected but advisory-only (no automated fix exists; follow the report's "
                "guidance): " + ", ".join(summary["unfixable_selected"])
            )
        print(
            "Review the branch and, if good, push / open a PR (not done automatically)."
        )

        if args.verify:
            _status("→ Re-analyzing the fixed branch to score deploy-readiness …")
            after, _ = analyze(
                workspace,
                args.policy,
                llm_client=llm_client,
                use_llm=not args.no_llm,
                progress=progress,
                max_workers=args.workers,
            )
            before_keys = {(f.condition_id, f.file, f.line) for f in result.findings}
            after_keys = {(f.condition_id, f.file, f.line) for f in after.findings}
            final_findings = after.findings
            fail_on_list = policy.get("report", {}).get("fail_on", ["critical", "high"])
            remaining = sum(
                1 for f in after.findings if f.severity.value in fail_on_list
            )
            ready = remaining == 0
            verification = {
                "ready": ready,
                "fail_on": fail_on_list,
                "remaining_blocking": remaining,
                "before": {
                    "total": len(result.findings),
                    "counts": result.counts(),
                    "posture": result.posture.get("recommendation", "?"),
                },
                "after": {
                    "total": len(after.findings),
                    "counts": after.counts(),
                    "posture": after.posture.get("recommendation", "?"),
                },
                "closed": len(before_keys - after_keys),
                "branch": summary["branch"],
                "workspace": str(workspace),
            }
            after_out = Path(_after_path(html_path)).resolve()
            after_out.write_text(
                render_html(
                    after, repo=args.repo, policy=policy, verification=verification
                )
            )
            print(f"✓ Post-fix report: {after_out.as_uri()}")
            if args.open:
                webbrowser.open(after_out.as_uri())
            verdict = (
                "READY to deploy"
                if ready
                else f"NOT READY — {remaining} {'/'.join(fail_on_list)} gap(s) remain"
            )
            _status(
                f"→ Deploy-readiness: {verdict}. {len(before_keys - after_keys)} gaps closed "
                f"({len(result.findings)} → {len(after.findings)})."
            )

    # Exit non-zero if any fail_on-severity gaps exist (CI-friendly).
    fail_on = set(policy.get("report", {}).get("fail_on", []))
    if any(f.severity.value in fail_on for f in final_findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
