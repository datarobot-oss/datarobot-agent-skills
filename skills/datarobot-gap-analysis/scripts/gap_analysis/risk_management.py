# Copyright (c) 2026 DataRobot, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Layer 4 (regulatory): the org's live DataRobot risk-management policy
decides WHAT is required, and an LLM judges whether the repo satisfies it.

There is no gap-analysis-defined regulatory checklist. The policy named by
`regulatory.policy_name` is fetched from DataRobot risk-management, and every
mitigation it requires (union across its risk tiers, the strictest honest
reading for a repo that isn't deployed anywhere yet) is assessed against the
repo the same way Layer 2 assesses its conditions: the LLM reads the relevant
files (per-type `files_glob` in risk_management_mitigations.yaml) and judges
whether there is evidence the mitigation is implemented, or wired up to be
provided by DataRobot at deployment time. This is deliberately a
pre-deployment, "would this be compliant if we deployed it" check; it does not
inspect deployed entities.

Unsatisfied required mitigations become findings; required mitigations that
cannot be assessed (no LLM, or an organisational requirement with no code
evidence) are listed as "not assessed" in the coverage table and never count
as gaps, so a run without an LLM does not read as a failing repo. Satisfying
almost all of them means adopting the corresponding DataRobot platform feature
(deployment monitoring, GenAI Guards, RBAC, Model Registry documentation,
...), not patching code in place. Findings are therefore advisory and
structural by default; the exception is mitigations satisfiable through
pulumi-datarobot (deployment settings, guards) on a repo that already carries
a Pulumi program, which become assisted IaC fixes and stop counting as
structural (see _finding_for_mitigation).

Degradation, the same "skipped-with-reason, never guess" philosophy as every
other layer: if DataRobot risk-management isn't reachable (no credentials,
feature not enabled for the org, no matching policy), Layer 4 finds nothing
and says why; if no LLM client is configured (--no-llm, or no model creds),
required mitigations are still fetched and reported, but as "required, not
assessed" rather than confirmed gaps.

The risk-management API is not yet publicly released as of this writing
(feature-gated, and there is no client for it in the public `datarobot` SDK,
checked directly against datarobot==3.18.0). This module calls it over
plain HTTP with stdlib urllib, no new dependency, following the standard
DataRobot Public API v2 convention of mounting under whatever
DATAROBOT_ENDPOINT already points at. Confirm paths against the live OpenAPI
spec once the feature is GA; a not-yet-public API carries no compatibility
guarantee.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

from . import paths
from .docs import resolve_docs
from .inventory import evidence_files, files_matching
from .llm import LLMClient, brief_error, parse_json
from .models import Finding, Severity

EU_AI_ACT_POLICY_NAME = "EU AI Act"
_TIMEOUT_SECONDS = 30
_RETRY_DELAY_SECONDS = 2
_MAX_FILES = 12  # cap files fed per mitigation, mirrors Layer 2's cap
_PROMPT_FILE = "prompts/risk-management-mitigation.md"
_DEFAULT_MAX_WORKERS = 4
_SUBMIT_STAGGER_SECONDS = 0.25


class RiskManagementClient:
    """Minimal stdlib HTTP client for the DataRobot risk-management API."""

    def __init__(self, endpoint: str, token: str):
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.last_error: str | None = None

    def get(self, path: str) -> Any | None:
        """GET a relative path under the risk-management API.

        None on any failure, with the reason kept in `last_error`. Timeouts
        and 5xx responses are retried once; anything else is final.
        """
        url = f"{self.endpoint}/{path.lstrip('/')}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
        )
        self.last_error = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                self.last_error = f"HTTP {e.code} {e.reason} from {url}"
                if e.code < 500:
                    return None
            except (TimeoutError, socket.timeout):
                self.last_error = f"timed out after {_TIMEOUT_SECONDS}s: {url}"
            except urllib.error.URLError as e:
                self.last_error = f"{e.reason} ({url})"
                return None
            except (ValueError, OSError) as e:
                self.last_error = f"{brief_error(e)} ({url})"
                return None
            if attempt == 0:
                time.sleep(_RETRY_DELAY_SECONDS)
        return None


def _drconfig_credentials() -> tuple[str | None, str | None]:
    """(endpoint, token) from the dr CLI / SDK config file, or (None, None)."""
    cfg = Path.home() / ".config" / "datarobot" / "drconfig.yaml"
    try:
        data = yaml.safe_load(cfg.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return None, None
    return data.get("endpoint"), data.get("token")


def get_client() -> RiskManagementClient | None:
    """Return a client, or None if credentials aren't configured.

    Env vars win; otherwise fall back to the dr CLI's config file, so a
    `dr auth login`-ed machine needs no DATAROBOT_* exports for Layer 4.
    """
    endpoint = os.environ.get("DATAROBOT_ENDPOINT")
    token = os.environ.get("DATAROBOT_API_TOKEN")
    if not endpoint or not token:
        cfg_endpoint, cfg_token = _drconfig_credentials()
        endpoint = endpoint or cfg_endpoint
        token = token or cfg_token
    if not endpoint or not token:
        return None
    return RiskManagementClient(endpoint, token)


def _as_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("data", [])
    return []


def fetch_mitigation_catalog(
    client: RiskManagementClient,
) -> list[dict[str, Any]] | None:
    """GET the live catalog of mitigation method types. None on any failure."""
    data = client.get("mitigationMethods/")
    return None if data is None else _as_list(data)


def fetch_policy_by_name(
    client: RiskManagementClient, name: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Find a risk policy by name or id. Returns (policy, note).

    An exact id match wins outright (the unambiguous escape hatch for
    `regulatory.policy_name`). On a name collision, a tenant-owned policy is
    preferred over the built-in of the same name: the API prepends built-ins,
    so first-match would deterministically shadow an org's customized copy
    with the stock default. `note`, when set, explains the disambiguation for
    the report's Engine Notes, or, when no policy is returned, why: the
    request failed (reason from the client) or the name matched none of the
    policies the API listed.
    """
    data = client.get("riskPolicies/")
    if data is None:
        return None, f"request failed: {client.last_error or 'no response'}"
    policies = _as_list(data)

    for policy in policies:
        if str(policy.get("id")) == name:
            return policy, None

    matches = [p for p in policies if p.get("name") == name]
    if not matches:
        names = ", ".join(repr(p.get("name")) for p in policies) or "none"
        return None, (
            f"the API returned {len(policies)} policy(ies): {names}. Set "
            "regulatory.policy_name to one of them, or to a policy id."
        )
    tenant_owned = [p for p in matches if p.get("tenantId")]
    if not tenant_owned:
        return matches[0], None
    note = None
    if len(tenant_owned) > 1:
        note = (
            f"Layer 4: {len(tenant_owned)} tenant policies are named '{name}'; "
            f"using the first (id {tenant_owned[0].get('id')}). Set "
            "regulatory.policy_name to a policy id to disambiguate."
        )
    elif len(matches) > 1:
        note = (
            f"Layer 4: the org's own '{name}' policy "
            f"(id {tenant_owned[0].get('id')}) was preferred over the "
            "built-in policy of the same name."
        )
    return tenant_owned[0], note


def required_mitigation_types(policy: dict[str, Any]) -> set[str]:
    """Every mitigation method type the policy requires, union across all risk
    tiers. Nothing is deployed or assessed yet, so no tier can be assumed; the
    union is the strictest honest reading for a pre-deployment check."""
    types: set[str] = set()
    for section in policy.get("mitigations", []) or []:
        for method in section.get("methods", []) or []:
            method_type = method.get("type")
            if method_type:
                types.add(method_type)
    return types


def load_mitigation_metadata(
    path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load risk_management_mitigations.yaml, keyed by mitigation_type."""
    p = Path(path) if path else paths.risk_management_mitigations_file()
    data = yaml.safe_load(p.read_text()) or {}
    return {m["mitigation_type"]: m for m in data.get("mitigations", [])}


def validate_metadata_against_catalog(
    metadata: dict[str, dict[str, Any]], catalog: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """Compare the shipped metadata against a live catalog. Returns drift, never raises."""
    catalog_types = {c["type"] for c in catalog if "type" in c}
    known_types = set(metadata)
    return {
        "new_in_catalog": sorted(catalog_types - known_types),
        "removed_from_catalog": sorted(known_types - catalog_types),
    }


def _condition_id(mitigation_type: str) -> str:
    return "POL-DR-" + mitigation_type.upper().replace("_", "-")


_PULUMI_FIX_PROMPT = "prompts/fix-pol-pulumi.md"
_PULUMI_PROGRAM_GLOBS = ["**/__main__.py", "**/infra/**/*.py", "**/*.py"]
_PULUMI_MARKERS = (
    "pulumi_datarobot",
    "pulumi-datarobot",
    "datarobot_pulumi_utils",
    "import pulumi",
)
_MAX_PULUMI_FILES = 10


def _detect_iac(workspace: Path, inventory: dict[str, Any]) -> dict[str, Any] | None:
    """The repo's pulumi-datarobot footprint, or None.

    Returns {file, deployment, custom_model, application}: which resource
    shapes the IaC declares. Deployment-level mitigations (drift, accuracy,
    fairness, notifications) can only be enabled on a `datarobot.Deployment`
    and guards only on a `datarobot.CustomModel`; a repo that ships just a
    CustomApplication/ApplicationSource has nothing to attach them to, so the
    gap is architectural (add a Deployment for the model/LLM path) rather than
    a settings edit.
    """
    info: dict[str, Any] = {
        "file": None,
        "files": [],
        "variants": {},
        "deployment": False,
        "deployment_file": None,
        "custom_model": False,
        "custom_model_file": None,
        "application": False,
    }
    # \bDeployment( catches datarobot.Deployment; CustomModelDeployment( is the
    # datarobot-pulumi-utils wrapper, which creates a Deployment under the hood.
    deployment_re = re.compile(r"\bDeployment\(|CustomModelDeployment\(")
    custom_model_re = re.compile(r"\bCustomModel\(")
    # Program entry points and infra/ modules first, then everything else, so a
    # large application tree cannot push the Pulumi program past the cap.
    candidates = files_matching(inventory, _PULUMI_PROGRAM_GLOBS[:2])
    seen = set(candidates)
    candidates += [
        f for f in files_matching(inventory, _PULUMI_PROGRAM_GLOBS[2:]) if f not in seen
    ]
    for rel in candidates[:400]:
        try:
            text = (workspace / rel).read_text(errors="ignore")
        except OSError:
            continue
        if not any(marker in text for marker in _PULUMI_MARKERS):
            continue
        if info["file"] is None:
            info["file"] = rel
        if len(info["files"]) < _MAX_PULUMI_FILES:
            info["files"].append(rel)
        path = workspace / rel
        if path.is_symlink():
            try:
                target = path.resolve().relative_to(workspace.resolve()).as_posix()
            except ValueError:
                target = os.readlink(path)
            info["variants"][rel] = target
        if deployment_re.search(text):
            info["deployment"] = True
            info["deployment_file"] = info["deployment_file"] or rel
        if custom_model_re.search(text):
            info["custom_model"] = True
            info["custom_model_file"] = info["custom_model_file"] or rel
        if "CustomApplication" in text or "ApplicationSource" in text:
            info["application"] = True
    return info if info["file"] else None


def _gather_files(
    workspace: Path, inventory: dict[str, Any], globs: list[str], max_bytes: int
) -> list[tuple[str, str]]:
    rels = evidence_files(inventory, globs, _MAX_FILES)
    out = []
    for rel in rels:
        try:
            data = (workspace / rel).read_text(errors="ignore")
        except OSError:
            continue
        if len(data.encode("utf-8", "ignore")) > max_bytes:
            data = data[:max_bytes] + "\n…[truncated]…"
        out.append((rel, data.replace("\x00", "")))
    return out


def _finding_for_mitigation(
    mitigation_type: str,
    meta: dict[str, Any],
    item: dict[str, Any] | None,
    iac: dict[str, Any] | None = None,
) -> Finding:
    """Build a Layer-4 Finding for one required-but-unsatisfied mitigation.

    `item` is the LLM's finding payload when the gap was confirmed by evidence
    assessment; None when the requirement couldn't be assessed (no LLM, no
    matching files, organizational-only), in which case the finding is framed
    as "required by policy, not verified" rather than a confirmed gap.

    A mitigation becomes an assisted IaC fix (and stops counting as structural)
    only when the Pulumi program already declares the resource it attaches to:
    deployment settings need a datarobot.Deployment, guards a
    datarobot.CustomModel. An application-only Pulumi program (CustomApplication
    with no Deployment) keeps these advisory and reframes them: the gap is that
    the model/LLM path is not behind a Deployment at all.
    """
    assessed = item is not None
    item = item or {}
    explanation = item.get("explanation") or (
        "Required by the org's DataRobot risk-management policy; not assessed "
        "against this repo, so treat as unresolved rather than passed."
    )
    remediation = f"{meta['remediation']} ({meta['datarobot_feature']})"
    fix_meta = meta.get("fix") or {}
    steps = [_step_text(s) for s in (meta.get("steps") or [])]
    if not steps and fix_meta.get("hint"):
        steps = [fix_meta["hint"]]

    requires = fix_meta.get("requires")
    pulumi_file = (iac or {}).get("file")
    if requires == "deployment" and (iac or {}).get("deployment_file"):
        pulumi_file = iac["deployment_file"]
    elif requires == "custom_model" and (iac or {}).get("custom_model_file"):
        pulumi_file = iac["custom_model_file"]
    target_exists = bool(
        iac
        and (
            (requires == "deployment" and iac.get("deployment"))
            or (requires == "custom_model" and iac.get("custom_model"))
        )
    )
    pulumi_fixable = fix_meta.get("via") == "pulumi" and target_exists
    prerequisite = _prerequisite(requires, fix_meta.get("via"), iac)
    return Finding(
        condition_id=_condition_id(mitigation_type),
        pillar="POL",
        severity=Severity(meta["default_severity"]),
        title=f"DataRobot risk-management: {meta['title']} not satisfied",
        # The Pulumi program is where the missing settings block belongs, so it
        # is both the evidence anchor and the assisted-fix target.
        file=pulumi_file if pulumi_fixable else item.get("file"),
        line=None if pulumi_fixable else item.get("line"),
        evidence=str(item.get("evidence", "") or f"mitigation type: {mitigation_type}")[
            :500
        ],
        explanation=str(explanation),
        remediation=remediation,
        fix_type="assisted" if pulumi_fixable else "advisory",
        fix_strategy=_PULUMI_FIX_PROMPT if pulumi_fixable else None,
        fix_risk=fix_meta.get("fix_risk", "plumbing") if pulumi_fixable else "none",
        confidence=item.get("confidence", "high") if assessed else "medium",
        layer=4,
        detector=f"risk_management:{mitigation_type}",
        structural=False if pulumi_fixable else bool(meta["structural"]),
        steps=steps,
        docs_url=resolve_docs(str(meta.get("docs_topic") or ""))
        if meta.get("docs_topic")
        else "",
        docs_topic=str(meta.get("docs_topic") or ""),
        prerequisite=prerequisite,
        fix_via=str(fix_meta.get("via") or ""),
        fix_requires=str(requires or ""),
    )


def _step_text(step: Any) -> str:
    """A step authored as `Label: text` parses as a one-key mapping in YAML."""
    if isinstance(step, dict) and len(step) == 1:
        ((label, text),) = step.items()
        return f"{label}: {text}"
    return str(step)


_RESOURCE_NAMES = {
    "deployment": "datarobot.Deployment",
    "custom_model": "datarobot.CustomModel",
}


def _prerequisite(
    requires: str | None, via: str | None, iac: dict[str, Any] | None
) -> str:
    """What the fix attaches to, and whether this repo's Pulumi program has it."""
    needed = requires or ("deployment" if via == "automatic" else None)
    if not needed:
        return ""
    name = _RESOURCE_NAMES.get(needed, needed)
    if not iac:
        return f"Needs a {name} in a Pulumi program; this repo has no pulumi-datarobot program."
    if iac.get(needed):
        where = iac.get(f"{needed}_file") or iac.get("file")
        return f"Needs a {name}; present in {where}."
    shape = (
        "a CustomApplication only"
        if iac.get("application")
        else "no Deployment or CustomModel"
    )
    return (
        f"Needs a {name}; not present. This repo's Pulumi program deploys {shape}, "
        "so the model or LLM path must first be put behind a DataRobot deployment."
    )


def _assess_mitigation(
    llm: LLMClient,
    workspace: Path,
    inventory: dict[str, Any],
    mitigation_type: str,
    meta: dict[str, Any],
    prompt: str,
    contract: str,
    max_bytes: int,
    pulumi_files: list[str] | None = None,
    iac_note: str = "",
) -> tuple[str, dict[str, Any] | None, str | None]:
    """LLM-judge one mitigation against the repo.

    Returns (verdict, finding_item, skip_reason): verdict is "pass" | "gap" |
    "skipped"; finding_item is the LLM's finding payload when verdict is "gap".
    """
    files = _gather_files(workspace, inventory, meta.get("files_glob") or [], max_bytes)
    # The Pulumi program is where IaC evidence lives; the per-glob file cap can
    # crowd it out with task runners and yaml, so pin those files to the front.
    have = {rel for rel, _ in files}
    for rel in reversed(pulumi_files or []):
        if rel in have:
            continue
        try:
            data = (workspace / rel).read_text(errors="ignore")
            files.insert(0, (rel, data[:max_bytes].replace("\x00", "")))
        except OSError:
            pass
    if not files:
        return "skipped", None, "no files matched this mitigation's globs"
    iac_line = (
        f"- infrastructure-as-code evidence that satisfies this: {meta['iac_evidence']}\n"
        if meta.get("iac_evidence")
        else ""
    )
    system = (
        f"{prompt}\n\n---\n# Mitigation under assessment\n"
        f"- id: {_condition_id(mitigation_type)}\n"
        f"- requirement: {meta['title']}\n"
        f"- satisfied by (at deployment): {meta['datarobot_feature']}\n"
        f"- what counts as evidence: {meta['evidence']}\n"
        f"{iac_line}{iac_note}"
        f"\n---\n# Output contract\n{contract}\n\n"
        f"You are checking condition {_condition_id(mitigation_type)}. "
        "Return ONLY the JSON object."
    )
    user = "\n\n".join(f"=== FILE: {rel} ===\n{content}" for rel, content in files)
    try:
        result = parse_json(llm.complete(system, user))
    except Exception as e:  # noqa: BLE001
        return "skipped", None, f"LLM/parse error: {brief_error(e)}"
    status = result.get("status", "found")
    if status == "not_found":
        return "pass", None, None
    if status == "skipped":
        return "skipped", None, result.get("skip_reason", "model reported skipped")
    items = result.get("findings") or [{}]
    return "gap", items[0], None


def run_dynamic_layer4(
    llm_client: LLMClient | None,
    workspace: str | Path,
    inventory: dict[str, Any],
    policy_name: str = EU_AI_ACT_POLICY_NAME,
    max_bytes: int = 200_000,
    mitigation_metadata_path: str | Path | None = None,
    progress: Any = None,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> tuple[list[Finding], list[dict[str, str]], list[str], dict[str, Any]]:
    """Run Layer 4: fetch the org's policy, LLM-assess each required mitigation.

    Returns (findings, coverage, notes, iac). `coverage` lists every mitigation
    considered, not just the ones that became findings, {mitigation_type,
    title, status}, status one of "pass" | "gap" | "not_assessed" |
    "unknown_type" (a live mitigation type this skill's metadata doesn't
    recognize yet, see validate_risk_management_mapping.py). Never raises:
    any failure here just means an empty result with a reason in `notes`.
    """
    notes: list[str] = []

    def _tick(msg: str) -> None:
        if progress:
            progress(msg)

    client = get_client()
    if client is None:
        notes.append(
            "Layer 4 (DataRobot risk-management) skipped, no DataRobot "
            "credentials found (DATAROBOT_API_TOKEN/DATAROBOT_ENDPOINT env "
            "vars, or the dr CLI config written by `dr auth login`)."
        )
        return [], [], notes, {}

    policy, name_note = fetch_policy_by_name(client, policy_name)
    if policy is None:
        notes.append(
            f"Layer 4 (DataRobot risk-management) skipped, policy "
            f"'{policy_name}' could not be loaded from {client.endpoint}: "
            f"{name_note or 'unknown reason'}"
        )
        return [], [], notes, {}
    if name_note:
        notes.append(name_note)

    required = sorted(required_mitigation_types(policy))
    metadata = load_mitigation_metadata(mitigation_metadata_path)
    workspace = Path(workspace)
    iac = _detect_iac(workspace, inventory)
    iac_note = ""
    if iac:
        shapes = [k for k in ("deployment", "custom_model", "application") if iac[k]]
        variants = iac.get("variants") or {}
        variant_txt = (
            " Active configuration variant(s): "
            + "; ".join(f"{k} -> {v}" for k, v in sorted(variants.items()))
            + "."
            if variants
            else ""
        )
        notes.append(
            f"Layer 4: pulumi-datarobot program detected ({iac['file']}; "
            f"declares: {', '.join(shapes) or 'no recognized resources'}).{variant_txt} "
            "Mitigations whose target resource exists are offered as assisted fixes."
        )
        if variants:
            iac_note = (
                "- active IaC variant(s), selected by symlink: "
                + "; ".join(f"{k} -> {v}" for k, v in sorted(variants.items()))
                + ". Other files under a configurations/ directory are alternative "
                "variants that are not deployed unless selected; judge the active one "
                "and name the variant you assessed in the evidence.\n"
            )
    prompt = contract = None
    if llm_client is not None:
        prompt = paths.resolve(_PROMPT_FILE).read_text()
        contract = (paths.prompts_dir() / "_contract.md").read_text()
    else:
        notes.append(
            "Layer 4: no LLM client configured, required mitigations are "
            "reported as not assessed instead of judged against the repo."
        )

    # LLM-assess all judgeable mitigations in parallel; each assessment is an
    # independent (prompt, files) completion, so only the aggregation below
    # needs to stay in `required` order for deterministic output.
    assessable = [
        mt
        for mt in required
        if metadata.get(mt)
        and metadata[mt].get("files_glob")
        and llm_client is not None
    ]
    assessed: dict[str, tuple[str, dict[str, Any] | None, str | None]] = {}
    if assessable:
        done = 0
        _tick(
            f"▶ Layer 4 (risk-management): judging {len(assessable)} mitigations "
            f"({max(1, max_workers)} workers)…"
        )
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futures = {}
            for i, mt in enumerate(assessable):
                if i:
                    time.sleep(_SUBMIT_STAGGER_SECONDS)
                futures[
                    pool.submit(
                        _assess_mitigation,
                        llm_client,
                        workspace,
                        inventory,
                        mt,
                        metadata[mt],
                        prompt,
                        contract,
                        max_bytes,
                        iac["files"] if iac else None,
                        iac_note,
                    )
                ] = mt
            for future in as_completed(futures):
                mt = futures[future]
                done += 1
                assessed[mt] = future.result()
                _tick(
                    f"Layer 4 (risk-management): {mt} done [{done}/{len(assessable)}]"
                )

    findings: list[Finding] = []
    coverage: list[dict[str, str]] = []
    for mitigation_type in required:
        meta = metadata.get(mitigation_type)
        if meta is None:
            coverage.append(
                {
                    "mitigation_type": mitigation_type,
                    "title": mitigation_type,
                    "status": "unknown_type",
                }
            )
            notes.append(
                f"Layer 4: DataRobot risk-management requires mitigation type "
                f"'{mitigation_type}', which isn't in this skill's assessment "
                "metadata yet (run validate_risk_management_mapping.py to confirm)."
            )
            continue

        verdict, item, skip_reason = "skipped", None, None
        if not meta.get("files_glob"):
            skip_reason = "organizational requirement, not assessable from code"
        elif mitigation_type in assessed:
            verdict, item, skip_reason = assessed[mitigation_type]

        if verdict == "pass":
            coverage.append(
                {
                    "mitigation_type": mitigation_type,
                    "title": meta["title"],
                    "status": "pass",
                }
            )
            continue

        if verdict == "gap":
            findings.append(_finding_for_mitigation(mitigation_type, meta, item, iac))
            coverage.append(
                {
                    "mitigation_type": mitigation_type,
                    "title": meta["title"],
                    "status": "gap",
                }
            )
            continue

        if skip_reason:
            notes.append(f"Layer 4: {mitigation_type} not assessed, {skip_reason}.")
        coverage.append(
            {
                "mitigation_type": mitigation_type,
                "title": meta["title"],
                "status": "not_assessed",
            }
        )

    unassessed = sum(1 for row in coverage if row["status"] == "not_assessed")
    if findings or unassessed:
        _tick(
            f"{len(findings)} mitigation(s) required by '{policy_name}' are unsatisfied; "
            f"{unassessed} not assessed."
        )
    return findings, coverage, notes, iac or {}
