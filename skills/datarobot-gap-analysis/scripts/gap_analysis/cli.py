# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Command-line entrypoint: clone -> analyze -> report -> (optionally) fix."""

from __future__ import annotations

import argparse
import json
import atexit
import os
import signal
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import analyze, fix
from .ingest import clone_repo
from .opencode import OpenCodeServer, OpenCodeWorkerClient, dr_available
from .models import AnalysisResult
from .policy import load_policy
from .report import render_report, usage_summary
from .settings import Settings
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


def _make_llm_client(settings: Settings) -> OpenCodeWorkerClient | None:
    """Return the LLM client for this run, or None to let the engine auto-detect.

    A private `dr opencode` server is started on a free port and every check
    attaches to it as a worker subprocess, authenticated through the CLI's own
    login. Without `dr` there is no LLM client: Layers 2 and 4 are skipped and
    the report says so. The server is stopped at process exit, covering every
    CLI return path.
    """
    if not dr_available():
        _status(
            "→ dr CLI not found; Layers 2 and 4 (LLM) will be skipped. Install it "
            "with the datarobot-setup skill."
        )
        return None
    server = OpenCodeServer(models=[settings.model], reasoning=settings.effort)
    try:
        url = server.start()
    except Exception as e:  # noqa: BLE001
        _status(
            f"→ dr opencode server failed to start ({e}); Layers 2 and 4 (LLM) "
            "will be skipped."
        )
        return None
    atexit.register(server.stop)
    # A SIGTERM (timeout, orchestrator kill) must still run atexit hooks, or the
    # private server outlives the run.
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda signum, _frame: sys.exit(128 + signum))
    effort = server.efforts.get(settings.model)
    client = OpenCodeWorkerClient(
        url,
        model=settings.model,
        cwd=server.workdir,
        reasoning_effort=effort,
        timeout=settings.worker_timeout,
    )
    effort_note = (
        f"reasoning effort {effort}"
        if effort
        else (
            "reasoning effort off"
            if settings.effort.lower() == "off"
            else "no reasoning mode for this model"
        )
    )
    _status(f"→ LLM checks run through dr opencode ({client.model}, {effort_note}).")
    return client


def settings_from_args(args: argparse.Namespace) -> Settings:
    """Every run option in one object: flags win, GAP_* variables are the defaults."""
    base = Settings.from_env()
    return base.with_(
        use_llm=base.use_llm and not args.no_llm,
        model=args.model or base.model,
        effort=args.effort or base.effort,
        verify=base.verify and not args.no_verify,
        workers=args.workers if args.workers is not None else base.workers,
        worker_timeout=args.llm_timeout
        if args.llm_timeout is not None
        else base.worker_timeout,
        offline=base.offline or args.offline,
    )


def out_path_for(args: argparse.Namespace) -> Path | None:
    """Where the Markdown report goes, or None for stdout."""
    if not args.out:
        return None
    out_path = Path(args.out)
    if out_path.is_dir() or args.out.endswith(("/", os.sep)):
        out_path = out_path / "gap-report.md"
    return out_path


def _html_path(args: argparse.Namespace, out_path: Path | None) -> str:
    if args.html:
        return str(args.html)
    return str(out_path.with_suffix(".html")) if out_path else "gap-report.html"


def _findings_path(args: argparse.Namespace, out_path: Path | None) -> Path:
    """The saved findings sit next to the HTML report, named by absolute path so
    the report's fix commands work from any shell directory."""
    return Path(_html_path(args, out_path)).resolve().with_name("gap-findings.json")


def _run_fix(
    args: argparse.Namespace,
    workspace: str | Path,
    result: AnalysisResult,
    policy: dict[str, Any],
    ts: str,
    llm_client: Any = None,
    html_path: str | None = None,
) -> dict[str, Any]:
    """Apply deterministic codemods, print the summary, optionally re-verify.

    Returns {"final_findings": [...]} so the caller can compute the exit code.
    """

    def progress(msg: str) -> None:
        _status(f"  … {msg}")

    html_path = html_path or "gap-report.html"
    final_findings = result.findings
    selected = set(s.strip() for s in args.select.split(",")) if args.select else None
    _status(
        f"→ Applying fixes ({'selected: ' + ','.join(sorted(selected)) if selected else 'all auto-fixable'}) "
        "on a gap-fixes/* branch …"
    )
    summary = fix(workspace, result, policy, ts, selected_ids=selected)
    # A fix that landed no longer counts against the exit code; without
    # --verify this is the only way the run can reflect what it just did.
    applied = {
        (r["condition_id"], r.get("file"))
        for r in summary["results"]
        if r["status"] == "applied"
    }
    final_findings = [
        f for f in result.findings if (f.condition_id, f.file) not in applied
    ]
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
            "\nHeld back (business-logic fixes; re-run with --select naming these "
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
        "\nNote: --fix patches the repo IN PLACE; it does not adopt the af-component "
        "stack. Re-platforming onto af-components is the migration path (RE-PLATFORM)."
    )
    if summary.get("unverified"):
        _status(
            "\nNot applied (LLM findings that did not pass the verification pass; "
            "re-run the analysis with verification on, or fix by hand): "
            + ", ".join(
                f"{u['condition_id']} ({u['file']})" for u in summary["unverified"]
            )
        )
    if summary.get("unfixable_selected"):
        print(
            "Selected but advisory-only (no automated fix exists; follow the report's "
            "guidance): " + ", ".join(summary["unfixable_selected"])
        )
    print("Review the branch and, if good, push / open a PR (not done automatically).")

    if getattr(args, "verify", False):
        _status("→ Re-analyzing the fixed branch to score deploy-readiness …")
        after, _ = analyze(
            workspace,
            args.policy,
            llm_client=llm_client,
            progress=progress,
            settings=settings_from_args(args),
        )
        before_keys = {(f.condition_id, f.file, f.line) for f in result.findings}
        after_keys = {(f.condition_id, f.file, f.line) for f in after.findings}
        final_findings = after.findings
        fail_on_list = policy.get("report", {}).get("fail_on", ["critical", "high"])
        remaining = sum(1 for f in after.findings if f.severity.value in fail_on_list)
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
            render_html(after, repo=args.repo, policy=policy, verification=verification)
        )
        print(f"✓ Post-fix report: {after_out.as_uri()}")
        if args.open:
            webbrowser.open(after_out.as_uri())
        verdict = (
            "READY to deploy"
            if ready
            else f"NOT READY: {remaining} {'/'.join(fail_on_list)} gap(s) remain"
        )
        _status(
            f"→ Deploy-readiness: {verdict}. {len(before_keys - after_keys)} gaps closed "
            f"({len(result.findings)} → {len(after.findings)})."
        )

    # Exit non-zero if any fail_on-severity gaps exist (CI-friendly).
    return {"final_findings": final_findings}


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
        help="load DataRobot credentials (DATAROBOT_ENDPOINT, DATAROBOT_API_TOKEN) "
        "from a dotenv file before running (default: .env); run options are flags",
    )
    ap.add_argument(
        "--no-llm",
        action="store_true",
        help="skip LLM checks: Layer 2 code reasoning entirely, and Layer 4's "
        "per-mitigation evidence assessment (required mitigations are still "
        "fetched from DataRobot risk-management and reported as not assessed). "
        "Layers 1 and 3 always run.",
    )
    llm = ap.add_argument_group(
        "LLM options",
        "Each flag defaults to the matching GAP_* environment variable when set.",
    )
    llm.add_argument(
        "--workers",
        type=int,
        default=None,
        help="parallel workers for Layer 2/4 LLM checks (default 4; GAP_WORKERS)",
    )
    llm.add_argument(
        "--model",
        default=None,
        help="model id for the LLM checks, provider/model (GAP_LLM_MODEL)",
    )
    llm.add_argument(
        "--effort",
        default=None,
        help="reasoning effort: max (the highest the provider accepts, default), off, "
        "or a literal value such as low or high (GAP_LLM_EFFORT)",
    )
    llm.add_argument(
        "--llm-timeout",
        type=int,
        default=None,
        help="seconds per LLM call before it is abandoned (default 120; GAP_OPENCODE_TIMEOUT)",
    )
    llm.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the second verification call per Layer 2 finding; faster, less "
        "trustworthy, and nothing is marked verified (GAP_VERIFY=off)",
    )
    ap.add_argument(
        "--offline",
        action="store_true",
        help="fetch no live catalogs (LLM Gateway models, docs index, agent template "
        "flavors); use the shipped snapshots (GAP_OFFLINE=on)",
    )
    ap.add_argument(
        "--fix",
        action="store_true",
        help="apply the deterministic fixes (dependency pins, secrets to env vars, "
        "scaffolds) on a gap-fixes/* branch",
    )
    ap.add_argument(
        "--from",
        dest="from_json",
        metavar="PATH",
        help="reuse the findings of a previous run (gap-findings.json written next to "
        "the report) instead of analyzing again; pairs with --fix",
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

    if Path(args.repo).expanduser().is_dir():
        _status(f"→ Using the local checkout at {args.repo} …")
    else:
        _status(f"→ Cloning {args.repo} …")
    try:
        workspace = clone_repo(args.repo, args.ref)
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.from_json:
        # Fixing from a saved run: no model, no re-analysis, straight to codemods.
        try:
            result = AnalysisResult.from_dict(
                json.loads(Path(args.from_json).read_text())
            )
        except (OSError, ValueError, KeyError) as e:
            print(
                f"error: cannot load findings from {args.from_json}: {e}",
                file=sys.stderr,
            )
            return 2
        policy = load_policy(args.policy)
        _status(f"→ Loaded {len(result.findings)} finding(s) from {args.from_json}.")
        if not args.fix:
            print(
                "nothing to do: --from is only useful together with --fix",
                file=sys.stderr,
            )
            return 2
        try:
            final = _run_fix(args, workspace, result, policy, ts)["final_findings"]
        except RuntimeError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        fail_on = set(policy.get("report", {}).get("fail_on", []))
        return 1 if any(f.severity.value in fail_on for f in final) else 0

    settings = settings_from_args(args)
    llm_client = _make_llm_client(settings) if settings.use_llm else None

    _status(
        "→ Analyzing (Layer 2/4 LLM checks run in parallel; use --no-llm to skip) …"
    )
    result, policy = analyze(
        workspace,
        args.policy,
        llm_client=llm_client,
        progress=progress,
        settings=settings,
    )
    _status(
        f"→ Analysis complete — {len(result.findings)} gaps "
        f"({result.posture.get('recommendation', '')})."
    )
    if usage_summary(result.usage):
        _status(f"→ LLM Gateway usage: {usage_summary(result.usage)}.")
    findings_path = _findings_path(args, out_path_for(args))
    report = render_report(
        result, repo=args.repo, policy=policy, findings_path=str(findings_path)
    )

    out_path = out_path_for(args)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"✓ Markdown report: {out_path.resolve()}")
    elif not args.html:
        print(report)

    html_path = _html_path(args, out_path)
    final_findings = result.findings
    out = Path(html_path).resolve()
    out.write_text(
        render_html(
            result, repo=args.repo, policy=policy, findings_path=str(findings_path)
        )
    )
    print(f"✓ HTML report: {out.as_uri()}")
    findings_path.write_text(json.dumps(result.to_dict(), indent=1, default=str))
    print(f"✓ Findings: {findings_path} (reuse with --fix --from)")
    if args.open:
        webbrowser.open(out.as_uri())

    if args.fix:
        try:
            final_findings = _run_fix(
                args, workspace, result, policy, ts, llm_client, html_path
            )["final_findings"]
        except RuntimeError as e:
            # The report/findings above are already written; only --fix failed.
            print(f"error: {e}", file=sys.stderr)
            return 2

    fail_on = set(policy.get("report", {}).get("fail_on", []))
    if any(f.severity.value in fail_on for f in final_findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
