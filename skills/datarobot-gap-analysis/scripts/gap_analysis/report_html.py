# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render the analysis result as a self-contained, styled HTML page.

Same data as report.py (posture, findings, scorecards) — different presentation. One
file, inline CSS + JS, no external assets, no server. Open it in a browser or share it.
All repo-derived text is HTML-escaped (repo content is untrusted).
"""

from __future__ import annotations

import html
import shutil
import sys
from pathlib import Path
from typing import Any

from .models import AnalysisResult, Finding, PILLARS
from .report import CONFORMANCE_ROWS, EU_ROWS

_SEV_LABEL = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
_FIX_LABEL = {"auto": "auto-fix", "assisted": "assisted-fix", "advisory": "advisory"}
_RISK_LABEL = {"plumbing": "plumbing", "business_logic": "business-logic"}
_POSTURE = {  # recommendation -> (label, css class)
    "PATCH": ("PATCH", "patch"),
    "HYBRID": ("HYBRID", "hybrid"),
    "RE-PLATFORM": ("RE-PLATFORM", "replatform"),
}


def _esc(s: Any) -> str:
    return html.escape("" if s is None else str(s))


def _cli_prog() -> str:
    """How to invoke the CLI in the copied commands.

    Prefer the `gap-analysis` console script that sits next to the running
    interpreter (the venv case) so the command runs WITHOUT activating the venv.
    Fall back to a bare `gap-analysis` (works if it's already on PATH; the report's
    Prerequisites note covers the not-installed case).
    """
    sibling = Path(sys.executable).resolve().parent / "gap-analysis"
    if sibling.exists():
        return str(sibling)
    return shutil.which("gap-analysis") or "gap-analysis"


def _cmd_target(repo: str) -> str:
    """The repo/path argument for the gap-analysis command (quoted if it has spaces)."""
    target = repo or "<repo>"
    return f'"{target}"' if " " in target else target


def _fix_cmd(repo: str, finding: Finding) -> str:
    """The exact terminal command that remediates this single finding."""
    return f"{_cli_prog()} {_cmd_target(repo)} --fix --select {finding.condition_id}"


def _fix_all_cmd(repo: str) -> str:
    """Blanket fix — the engine applies only plumbing fixes without explicit ids."""
    return f"{_cli_prog()} {_cmd_target(repo)} --fix"


def _migrate_cmd(repo: str) -> str:
    """Migration runs in the agent (no CLI flag); this is the agent invocation."""
    target = repo or "<repo>"
    return (
        "cd agent_app/agent && task cli START_DEV=1 -- execute "
        f'--user_prompt "Migrate {target} onto af-components"'
    )


def _verification_banner(v: dict[str, Any]) -> str:
    """Post-fix 'is it ready to deploy?' banner: before->after score + verdict."""
    ready = bool(v.get("ready"))
    cls = "ready" if ready else "notready"
    verdict = "✅ Ready to deploy" if ready else "⛔ Not ready to deploy"
    b, a = v.get("before", {}), v.get("after", {})
    fail_on = ", ".join(v.get("fail_on", [])) or "critical/high"
    blocking = v.get("remaining_blocking", 0)
    sub = (
        f"No {fail_on} gaps remain on the fixed branch."
        if ready
        else f"{blocking} {fail_on} gap(s) still remain — not safe to ship yet."
    )
    out = [f'<section class="verify {cls}">']
    out.append(
        f'<div class="verify-top"><span class="badge">{verdict}</span>'
        f'<span class="verify-sub">{_esc(sub)}</span></div>'
    )
    # before -> after deltas
    rows = [
        f"<b>{v.get('closed', 0)}</b> gaps closed "
        f"({b.get('total', 0)} → {a.get('total', 0)} total)",
        f"posture {_esc(b.get('posture', '?'))} → {_esc(a.get('posture', '?'))}",
    ]
    deltas = []
    for sev in ("critical", "high", "medium", "low"):
        bc = (b.get("counts") or {}).get(sev, 0)
        ac = (a.get("counts") or {}).get(sev, 0)
        if bc or ac:
            arrow = "▼" if ac < bc else ("▲" if ac > bc else "=")
            deltas.append(f"{_SEV_LABEL[sev].title()} {bc}→{ac} {arrow}")
    out.append('<p class="verify-line">' + " &nbsp;·&nbsp; ".join(rows) + "</p>")
    out.append(
        '<p class="verify-line deltas">'
        + " &nbsp; ".join(_esc(d) for d in deltas)
        + "</p>"
    )
    if v.get("branch") or v.get("workspace"):
        out.append(
            '<p class="verify-loc">Fixed branch <code>'
            + _esc(v.get("branch", ""))
            + "</code> in <code>"
            + _esc(v.get("workspace", ""))
            + "</code></p>"
        )
    out.append(
        '<p class="verify-note">Note: <code>--fix</code> patches the existing repo in '
        "place; it does not adopt the af-component stack. Re-platforming onto "
        "af-components is the migration path (RE-PLATFORM posture).</p>"
    )
    out.append("</section>")
    return "\n".join(out)


def render_html(
    result: AnalysisResult,
    repo: str = "",
    policy: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
) -> str:
    counts = result.counts()
    total = len(result.findings)
    inv = result.inventory or {}

    body: list[str] = []

    # Header
    body.append('<header class="hdr">')
    body.append("<h1>Enterprise-Readiness Gap Report</h1>")
    meta = []
    if repo:
        meta.append(f"<b>Repository:</b> {_esc(repo)}")
    if inv:
        meta.append(f"<b>Files scanned:</b> {inv.get('file_count', 0)}")
        meta.append(f"<b>Python:</b> {_esc(inv.get('python_version') or 'n/a')}")
    if meta:
        body.append('<p class="meta">' + " &nbsp;|&nbsp; ".join(meta) + "</p>")
    body.append("</header>")

    # Post-fix verification banner (deploy-readiness), when this is an "after" report.
    if verification:
        body.append(_verification_banner(verification))

    # Prerequisites note — the fix buttons copy a terminal command; this explains
    # how to make the CLI available if `gap-analysis` is "command not found".
    if any(f.fix_type in ("auto", "assisted") for f in result.findings):
        body.append(
            '<p class="prereq">ℹ️ The fix buttons copy a terminal command for you to run. '
            "If you get <code>gap-analysis: command not found</code>, the CLI isn't on your "
            "PATH — activate its virtualenv (<code>source .venv/bin/activate</code>) or install "
            "it (<code>pipx install</code> / <code>pip install -e .</code>). Copied commands use "
            "the resolved CLI path when one is found.</p>"
        )

    # Posture banner
    if result.posture:
        body.append(_posture_banner(result.posture, repo))

    # Severity summary chips (clickable filters)
    body.append('<section class="summary">')
    body.append(f'<p class="total">{total} gaps</p>')
    body.append('<div class="chips">')
    body.append(
        '<button class="chip chip-all active" data-sev="all" '
        'onclick="filterSev(this)">All</button>'
    )
    for sev in ("critical", "high", "medium", "low"):
        body.append(
            f'<button class="chip chip-{sev}" data-sev="{sev}" onclick="filterSev(this)">'
            f'{_SEV_LABEL[sev]} <span class="n">{counts[sev]}</span></button>'
        )
    body.append("</div>")
    fixable = sum(1 for f in result.findings if f.fix_type in ("auto", "assisted"))
    auto = sum(1 for f in result.findings if f.fix_type == "auto")
    body.append(
        f'<p class="sub">{fixable} of {total} fixable ({auto} automatically). '
        "Plumbing fixes are safe to sweep; business-logic fixes are applied only when "
        "selected by id.</p>"
    )
    body.append("</section>")

    # Findings grouped by pillar
    body.append('<section class="findings">')
    has_auto = any(f.fix_type == "auto" for f in result.findings)
    fixall_btn = ""
    if has_auto:
        fixall_btn = (
            f'<button class="fixbtn fixall" data-cmd="{_esc(_fix_all_cmd(repo))}" '
            'onclick="copyCmd(this)" title="Copies a terminal command that applies '
            'all auto-fixable (plumbing) fixes on a gap-fixes/* branch">'
            "⧉ Fix all auto-fixable</button>"
        )
    body.append(
        '<div class="findings-head"><h2>Findings</h2><div class="head-actions">'
        + fixall_btn
        + '<button class="toggle-all" onclick="toggleAll()">Collapse all</button>'
        "</div></div>"
    )
    by_pillar: dict[str, list[Finding]] = {}
    for f in result.by_severity():
        by_pillar.setdefault(f.pillar, []).append(f)
    if not result.findings:
        body.append('<p class="empty">No gaps detected.</p>')
    for pillar in [p for p in PILLARS if p in by_pillar]:
        items = by_pillar[pillar]
        body.append('<details class="pillar" open>')
        body.append(
            f'<summary>{_esc(PILLARS[pillar])} <span class="pill-id">({pillar})</span>'
            f'<span class="count">{len(items)}</span></summary>'
        )
        for f in items:
            body.append(_finding_card(f, repo))
        body.append("</details>")
    body.append("</section>")

    # Scorecards
    found_ids = {f.condition_id for f in result.findings}
    skipped_ids = {s.condition_id for s in result.skipped}
    body.append(_conformance_section(found_ids))
    body.append(_eu_section(found_ids, skipped_ids))

    # Skips & notes
    if result.skipped:
        body.append('<section class="notes"><h2>Not Evaluated (skipped)</h2><ul>')
        for s in result.skipped:
            body.append(f"<li><b>{_esc(s.condition_id)}</b> — {_esc(s.reason)}</li>")
        body.append("</ul></section>")
    if result.notes:
        body.append('<section class="notes"><h2>Engine Notes</h2><ul>')
        for n in result.notes:
            body.append(f"<li>{_esc(n)}</li>")
        body.append("</ul></section>")

    body.append(
        "<footer>Secret values are never shown. EU AI Act findings are advisory and "
        "not legal advice.</footer>"
    )

    return _DOC.replace("{{BODY}}", "\n".join(body))


def _posture_banner(posture: dict[str, Any], repo: str = "") -> str:
    rec = posture.get("recommendation", "PATCH")
    label, cls = _POSTURE.get(rec, (rec, "patch"))
    pct = int(round(posture.get("score", 0.0) * 100))
    out = [f'<section class="posture {cls}">']
    out.append(
        f'<div class="posture-top"><span class="badge">{_esc(label)}</span>'
        f'<span class="posture-meta">structural risk {pct}% &middot; '
        f"{posture.get('structural_count', 0)} of {posture.get('total', 0)} gaps "
        f"structural</span></div>"
    )
    out.append(f'<p class="rationale">{_esc(posture.get("rationale", ""))}</p>')
    drivers = posture.get("drivers") or []
    if drivers:
        out.append(
            '<details class="drivers"><summary>Structural drivers '
            "(can't be surgically patched)</summary><ul>"
        )
        for d in drivers:
            sev = d.get("severity", "")
            out.append(
                f'<li><span class="dot dot-{_esc(sev)}"></span>'
                f"<b>{_esc(d.get('condition_id'))}</b> {_esc(_SEV_LABEL.get(sev, sev))} — "
                f"{_esc(d.get('title'))}</li>"
            )
        out.append("</ul>")
        if rec != "PATCH":
            out.append(
                '<p class="hint">For these, prefer re-platforming: extract '
                "the business logic into a fresh af-components base rather than "
                "restructuring in place.</p>"
            )
            out.append(
                f'<button class="fixbtn migrate" data-cmd="{_esc(_migrate_cmd(repo))}" '
                'onclick="copyCmd(this)" title="Copy the command to run the guided migration '
                'in the agent">⧉ Copy re-platform command</button>'
            )
        out.append("</details>")
    out.append("</section>")
    return "\n".join(out)


def _finding_card(f: Finding, repo: str = "") -> str:
    sev = f.severity.value
    loc = (
        "repo-wide" if not f.file else (_esc(f.file) + (f":{f.line}" if f.line else ""))
    )
    fix = _FIX_LABEL.get(f.fix_type, f.fix_type)
    risk = _RISK_LABEL.get(f.fix_risk)
    risk_html = (
        f'<span class="tag tag-{_esc(f.fix_risk)}">{_esc(risk)}</span>' if risk else ""
    )
    conf = (
        ""
        if f.confidence == "high"
        else f'<span class="conf">confidence: {_esc(f.confidence)}</span>'
    )
    return (
        f'<article class="card sev-{sev}" data-sev="{sev}">'
        f'<div class="card-head">'
        f'<span class="cid">{_esc(f.condition_id)}</span>'
        f'<span class="tag tag-sev tag-{sev}">{_SEV_LABEL[sev]}</span>'
        f'<span class="tag tag-fix">{_esc(fix)}</span>{risk_html}'
        f'<span class="title">{_esc(f.title)}</span>{conf}'
        f"</div>"
        f'<div class="kv"><span class="k">Where</span><span class="v"><code>{loc}</code></span></div>'
        f'<div class="kv"><span class="k">Evidence</span><span class="v">{_esc(f.evidence) or "—"}</span></div>'
        f'<div class="kv"><span class="k">Why it matters</span><span class="v">{_esc(f.explanation) or "—"}</span></div>'
        f'<div class="kv"><span class="k">Fix</span><span class="v">{_esc(f.remediation) or "—"}</span></div>'
        f"{_fix_action(f, repo)}"
        f"</article>"
    )


def _fix_action(f: Finding, repo: str) -> str:
    """The actionable footer of a card: a copy-the-command button (or manual note)."""
    if f.fix_type not in ("auto", "assisted"):
        return (
            '<div class="card-action"><span class="manual">📝 Manual remediation — '
            "advisory only; follow the guidance above.</span></div>"
        )
    cmd = _fix_cmd(repo, f)
    if f.fix_risk == "business_logic":
        warn = (
            '<span class="warn">⚠ touches business logic — review the diff on the '
            "branch before merging</span>"
        )
    else:
        warn = '<span class="ok">safe plumbing fix</span>'
    return (
        '<div class="card-action">'
        f'<button class="fixbtn" data-cmd="{_esc(cmd)}" onclick="copyCmd(this)" '
        'title="Copy the terminal command that applies this fix">⧉ Copy fix command</button>'
        f'<code class="cmd">{_esc(cmd)}</code>{warn}'
        "</div>"
    )


def _conformance_section(found_ids: set[str]) -> str:
    rows = []
    for cid, label in CONFORMANCE_ROWS:
        gap = cid in found_ids
        status = (
            '<span class="st gap">gap</span>'
            if gap
            else '<span class="st pass">pass</span>'
        )
        rows.append(f"<tr><td>{_esc(cid)} — {_esc(label)}</td><td>{status}</td></tr>")
    return (
        '<section class="scorecard"><h2>IT Conformance Scorecard</h2>'
        "<table><thead><tr><th>Control</th><th>Status</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></section>"
    )


def _eu_section(found_ids: set[str], skipped_ids: set[str]) -> str:
    rows = []
    for cid, label in EU_ROWS:
        if cid in found_ids:
            status = '<span class="st gap">gap</span>'
        elif cid in skipped_ids:
            status = '<span class="st skip">not evaluated</span>'
        else:
            status = '<span class="st pass">evidence found</span>'
        rows.append(f"<tr><td>{_esc(cid)} — {_esc(label)}</td><td>{status}</td></tr>")
    return (
        '<section class="scorecard"><h2>EU AI Act Coverage</h2>'
        "<table><thead><tr><th>Article area</th><th>Status</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></section>"
    )


_DOC = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gap Report</title>
<style>
:root{
  --crit:#d92d20; --high:#e8801a; --med:#caa800; --low:#667085;
  --bg:#f6f7f9; --card:#fff; --line:#e4e7ec; --ink:#1d2433; --muted:#667085;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 6px} h2{font-size:16px;margin:26px 0 12px}
.meta,.sub{color:var(--muted)} .meta{margin:4px 0 0}
.prereq{margin:14px 0 0;padding:9px 12px;background:#fff8e6;border:1px solid #f3e1b0;
  border-radius:8px;color:#6b5a16;font-size:13px}
.prereq code{background:#0d1117;color:#e6edf3;padding:1px 6px;border-radius:4px;font-size:12px}
/* post-fix verification */
.verify{margin:14px 0 0;border-radius:12px;padding:16px 18px;color:#fff}
.verify.ready{background:#0a7d3c} .verify.notready{background:#b42318}
.verify-top{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.verify .badge{background:rgba(255,255,255,.22);padding:4px 12px;border-radius:999px;
  font-weight:800;letter-spacing:.3px}
.verify-sub{opacity:.95} .verify-line{margin:8px 0 0} .verify-line.deltas{font-weight:600}
.verify-loc{margin:8px 0 0;opacity:.95} .verify-note{margin:8px 0 0;opacity:.85;font-size:12px}
.verify code{background:rgba(255,255,255,.22);padding:1px 6px;border-radius:4px}
section{margin-top:18px}
/* posture */
.posture{border-radius:12px;padding:16px 18px;border:1px solid var(--line);color:#fff}
.posture.patch{background:#0a7d3c} .posture.hybrid{background:#b97309}
.posture.replatform{background:#b42318}
.posture-top{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.posture .badge{background:rgba(255,255,255,.22);padding:4px 12px;border-radius:999px;
  font-weight:700;letter-spacing:.5px}
.posture-meta{opacity:.9} .rationale{margin:10px 0 0}
.posture details{margin-top:10px} .posture summary{cursor:pointer;opacity:.95;font-weight:600}
.posture .drivers ul{margin:8px 0 0;padding-left:4px;list-style:none}
.posture .drivers li{padding:3px 0} .posture .hint{opacity:.92;margin:8px 0 0}
.posture code{background:rgba(255,255,255,.22);padding:1px 5px;border-radius:4px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}
.dot-critical{background:#fff} .dot-high{background:#ffe0b3}
.dot-medium{background:#fff4bf} .dot-low{background:#d6dae0}
/* summary */
.total{font-size:18px;font-weight:700;margin:0}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.chip{cursor:pointer;border:1px solid var(--line);background:var(--card);border-radius:999px;
  padding:5px 12px;font-size:13px;font-weight:600;color:var(--ink)}
.chip .n{opacity:.6;margin-left:4px}
.chip.active{outline:2px solid #1570ef33}
.chip-critical{border-color:var(--crit);color:var(--crit)}
.chip-high{border-color:var(--high);color:var(--high)}
.chip-medium{border-color:var(--med);color:#8a7400}
.chip-low{border-color:var(--low);color:var(--low)}
/* findings */
.findings-head{display:flex;align-items:center;justify-content:space-between}
.toggle-all{cursor:pointer;background:none;border:1px solid var(--line);border-radius:6px;
  padding:4px 10px;color:var(--muted)}
details.pillar{background:var(--card);border:1px solid var(--line);border-radius:10px;
  margin:10px 0;padding:6px 14px}
details.pillar>summary{cursor:pointer;font-weight:700;padding:6px 0;list-style:none}
details.pillar>summary::-webkit-details-marker{display:none}
.pill-id{color:var(--muted);font-weight:500}
.count{float:right;background:var(--bg);border-radius:999px;padding:1px 9px;color:var(--muted)}
.card{border:1px solid var(--line);border-left:4px solid var(--low);border-radius:8px;
  padding:11px 13px;margin:9px 0;background:#fff}
.card.sev-critical{border-left-color:var(--crit)}
.card.sev-high{border-left-color:var(--high)}
.card.sev-medium{border-left-color:var(--med)}
.card.sev-low{border-left-color:var(--low)}
.card-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.cid{font-weight:700;font-family:ui-monospace,Menlo,monospace}
.title{font-weight:600} .conf{color:var(--muted);font-size:12px}
.tag{font-size:11px;font-weight:700;border-radius:5px;padding:2px 7px;text-transform:uppercase;
  letter-spacing:.3px}
.tag-sev{color:#fff}
.tag-critical{background:var(--crit)} .tag-high{background:var(--high)}
.tag-medium{background:var(--med)} .tag-low{background:var(--low)}
.tag-fix{background:#eef2ff;color:#3538cd}
.tag-plumbing{background:#e7f6ec;color:#0a7d3c}
.tag-business_logic{background:#fdecea;color:#b42318}
.kv{display:flex;gap:10px;padding:2px 0}
.kv .k{flex:0 0 116px;color:var(--muted);font-size:12px;text-transform:uppercase;
  letter-spacing:.3px;padding-top:1px}
.kv .v{flex:1} .kv code{background:var(--bg);padding:1px 5px;border-radius:4px}
.empty{color:var(--muted)}
/* scorecards */
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid var(--line);
  border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line)}
th{background:var(--bg);font-size:12px;text-transform:uppercase;color:var(--muted)}
tr:last-child td{border-bottom:none}
.st{font-weight:700} .st.gap{color:var(--crit)} .st.pass{color:#0a7d3c} .st.skip{color:var(--muted)}
.notes ul{margin:0;padding-left:18px}
footer{margin-top:30px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);
  padding-top:12px}
/* fix actions */
.head-actions{display:flex;gap:8px;align-items:center}
.fixbtn{cursor:pointer;border:1px solid #3538cd;background:#eef2ff;color:#3538cd;
  border-radius:6px;padding:4px 11px;font-size:12px;font-weight:700;white-space:nowrap}
.fixbtn:hover{background:#3538cd;color:#fff}
.fixbtn.fixall{border-color:#0a7d3c;background:#e7f6ec;color:#0a7d3c}
.fixbtn.fixall:hover{background:#0a7d3c;color:#fff}
.fixbtn.migrate{margin-top:10px;border-color:#fff;background:rgba(255,255,255,.18);color:#fff}
.fixbtn.migrate:hover{background:#fff;color:#b42318}
.card-action{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:9px;
  padding-top:9px;border-top:1px dashed var(--line)}
.card-action .cmd{font-family:ui-monospace,Menlo,monospace;font-size:12px;background:#0d1117;
  color:#e6edf3;padding:3px 8px;border-radius:5px;user-select:all}
.card-action .warn{font-size:12px;color:var(--crit);font-weight:600}
.card-action .ok{font-size:12px;color:#0a7d3c;font-weight:600}
.card-action .manual{font-size:12px;color:var(--muted)}
#toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(20px);
  background:#1d2433;color:#fff;padding:10px 16px;border-radius:8px;font-size:13px;
  box-shadow:0 6px 24px #0003;opacity:0;pointer-events:none;transition:.2s;max-width:80vw}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#toast code{background:rgba(255,255,255,.18);padding:1px 6px;border-radius:4px}
</style>
</head>
<body>
<div class="wrap">
{{BODY}}
</div>
<div id="toast"></div>
<script>
var _toastTimer;
function showToast(html){
  var t=document.getElementById('toast');
  t.innerHTML=html; t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(function(){t.classList.remove('show');},4200);
}
function copyCmd(btn){
  var cmd=btn.dataset.cmd;
  function done(){ showToast('Copied — paste in your terminal:<br><code>'+
    cmd.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</code>'); }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(cmd).then(done, function(){ fallback(cmd); done(); });
  } else { fallback(cmd); done(); }
}
function fallback(cmd){
  var ta=document.createElement('textarea'); ta.value=cmd;
  ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta);
  ta.select(); try{document.execCommand('copy');}catch(e){} document.body.removeChild(ta);
}
function filterSev(btn){
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
  btn.classList.add('active');
  var sev=btn.dataset.sev;
  document.querySelectorAll('.card').forEach(function(c){
    c.style.display=(sev==='all'||c.dataset.sev===sev)?'':'none';
  });
  // hide a pillar block whose cards are all filtered out
  document.querySelectorAll('details.pillar').forEach(function(p){
    var any=[].some.call(p.querySelectorAll('.card'),x=>x.style.display!=='none');
    p.style.display=any?'':'none';
  });
}
function toggleAll(){
  var ps=document.querySelectorAll('details.pillar');
  var anyOpen=[].some.call(ps,p=>p.open);
  ps.forEach(p=>p.open=!anyOpen);
  document.querySelector('.toggle-all').textContent=anyOpen?'Expand all':'Collapse all';
}
</script>
</body>
</html>
"""
