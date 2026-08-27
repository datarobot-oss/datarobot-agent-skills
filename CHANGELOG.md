# Changelog

All notable changes to DataRobot agent skills are tracked here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
version numbers track the shared plugin version maintained across
`.claude-plugin/`, `.cursor-plugin/plugin.json`, and `gemini-extension.json`.

Each entry should be prefixed with the affected skill folder name (for example,
`` `datarobot-predictions`: ... ``) so it's easy to scan what changed per skill.

## [Unreleased]

## [1.6.0] - 2026-08-26

### Added

- `datarobot-llm-gateway`:  Added a new skill which helps setting up llm gateway, it lists available llm models directly from `SKILL.md`. The CLI handles auth via its own credential store, and syncs env variables.

## [1.5.5] - 2026-08-26

### Fixed
- `datarobot-model-monitoring`: The Pattern 1 health-check example read `stats.prediction_count` and `stats.mean_response_time`, which do not exist on the SDK 3.x `ServiceStats` object (`AttributeError`). Read them from the `.metrics` dict instead (`stats.metrics["totalPredictions"]`, `stats.metrics["responseTime"]`). Also corrected the SDK reference list: `model.get_metrics()` → `model.metrics` (a dict of `{metric: {partition: score}}`); `get_metrics()` does not exist.

## [1.5.4] - 2026-08-25

### Fixed

- All skills: helper scripts and examples now call plain `dr.Client()` instead of re-reading `DATAROBOT_API_TOKEN` and `DATAROBOT_ENDPOINT` and passing them back in. The SDK reads those variables itself and then falls back to `~/.config/datarobot/drconfig.yaml`, so this fixes setups where only `drconfig.yaml` is configured — what `dr auth login` (per `datarobot-setup`) writes. Previously most sites hardcoded a `"https://app.datarobot.com"` endpoint default, which supplied an endpoint with no matching token and failed with `ValueError: Token must be specified if endpoint is specified` (and was missing the `/api/v2` suffix); `datarobot-model-explainability` used `os.environ["DATAROBOT_API_TOKEN"]` and failed the same setup with `KeyError`.

## [1.5.3] - 2026-08-25

### Fixed
- `datarobot-model-training`: Update the sample code and helper scripts for the current `datarobot` SDK (3.x). `set_target()` → `analyze_and_model()` (sets the target and starts AutoPilot), the removed `Project.start(autopilot_on=, max_wait=)` → `wait_for_autopilot()`, `project.status` → `project.stage`, `model.get_metrics()` → `model.metrics`, and select the recommended model via `ModelRecommendation.get(project.id).get_model()` instead of a broken `max(models, key=lambda m: m.metrics.get("AUC", 0))` that treats a per-partition dict as a scalar. `list_models.py` now sorts on the validation partition score (null-safe).

## [1.5.1] - 2026-08-13

### Fixed
- `datarobot-agent-assist`: `LLM_DEFAULT_MODEL` now gets the `datarobot/`-prefixed `llm_default_model` value, not the catalog `llmId` the gateway 404s on. `setup_template.py` refuses an `llmId`; `api_model` stays unprefixed for the on-the-wire rehearsal.
- `datarobot-agent-assist`: The model table leads with `LLM_DEFAULT_MODEL` (not the unusable `llmId`) and gives the deployment id its own column, shown only when a deployed entry is present.
- `datarobot-agent-assist`: The dress rehearsal strips the `datarobot/` prefix before reading a provider, so a prefixed spec keeps its cross-provider guard instead of matching nothing and rehearsing against an arbitrary catalog pick.
- `datarobot-agent-assist`: `setup_template.py` verifies the model with a direct catalog API call (not `dr llm-gateway list`, which can fall back to a stored profile and answer about a different instance), rejects characters that would break the `.env` line, and treats a disabled gateway as a cue to pick a deployed LLM.

## [1.5.0] - 2026-08-10

### Added
- `datarobot-agent-assist`: Make a DataRobot-deployed LLM selectable end to end. `agent_spec.md` gains an optional `llm_deployment_id`, and `setup_template.py` gains `--llm-deployment-id`, writing `LLM_DEPLOYMENT_ID`, `INFRA_ENABLE_LLM=deployed_llm.py`, and `USE_DATAROBOT_LLM_GATEWAY=0` so the template routes to the deployment instead of the LLM Gateway. Model selection recommends a deployed LLM when the gateway is empty or disabled, which is the normal shape of an on-prem install.

### Fixed
- `datarobot-agent-assist`: DataRobot-deployed LLMs are listed on every `dr` version the agent template accepts. `dr llm-gateway list` only reports them from v0.2.79 while the template's minimum is 0.2.77, and a non-empty gateway was enough to skip the direct-API fallback, so the deployed source silently did not exist on an older CLI.
- `datarobot-agent-assist`: `setup_template.py` refuses the shared `datarobot-deployed-llm` placeholder without a deployment id, instead of leaving the template on its gateway configuration to fail later at `pulumi up` with `Model 'datarobot-deployed-llm' not found in catalog`. The placeholder is matched case-insensitively, since the value comes from LLM-authored spec text.
- `datarobot-agent-assist`: The dress rehearsal resolves a deployed LLM through the spec's `llm_deployment_id`. Resolving on `model` alone matched whichever deployment the catalog indexed last and reported it as an exact match, so a spec could silently rehearse against a different deployment than the one selected.
- `datarobot-agent-assist`: `list_llm_models.py` closes stdin on the `dr` subprocess, so a credential prompt fails immediately rather than waiting out the timeout, and it names the requested instance alongside the CLI's log lines, making visible the case where the CLI ignored the passed credentials and listed a different instance.
- `datarobot-agent-assist`: Deployment labels are collapsed to one pipe-free line when rendering the model table; an embedded newline in user-authored label text split a row apart.
- `datarobot-agent-assist`: `SKILL.md` documented `list_llm_models.py` without its required `--target-dir`, and its Helper Scripts section referenced an undefined `<scripts_dir>` placeholder instead of the `<skill_scripts_dir>` the skill resolves. Both made the documented invocations dead instructions.
- `datarobot-agent-assist`: `ensure_env_file` printed its progress line and the `dr dotenv setup` output to stdout, so `list_llm_models.py --json` produced unparseable output on a target directory with no `.env`. Both now go to stderr.

## [1.4.3] - 2026-08-05

### Changed
- `datarobot-agent-assist-simulate`: Refine UX for swarm simulation.

## [1.4.2] - 2026-08-04

- `datarobot-model-training`: Create/associate a `dr.UseCase` when creating datasets and projects, so projects aren't orphaned in the DataRobot UI.

## [1.4.1] - 2026-08-03

### Changed
- `datarobot-agent-assist-simulate`: UX improvements — domain-aware Q2, grouped scenario list, `dr dotenv update` in auth setup, live progress narration during swarm run.

## [1.4.0] - 2026-07-28

### Added
- `datarobot-agent-assist`: New `agent-assist-simulate` swarm skill — adversarial scenario generation, multi-turn simulation, convergence loop, and evaluation reporting.

### Changed
- `datarobot-agent-assist`: Move `check_codespace.py` into `agent-assist-build/scripts/` alongside `env_utils.py`.
- `datarobot-agent-assist`: Pin `ruff==0.15.22` in dev dependencies to prevent silent version drift.

## [1.3.10] - 2026-07-28

- `datarobot-agent-assist`: Merge pre-coding spec gate into `pre-coding-checklist.md` Bootstrap step 2 (removes duplicate "Before Coding Begins" section). Add missing-spec recovery, path validation, session flags, workspace ask-don't-guess for Code, and journey deduplication. Trim `SKILL.md`: move CLI setup, helper scripts, plugin tool mapping, dress rehearsal prompt, path resolution, and agent_spec schema into references. Flow polish: Code-no-spec merges with Path resolution step 1, schema read hook in Spec Display, `design_to_code` guard and Windows stop in pre-coding, welcome menu resets `design_messy_cwd`.

## [1.3.9] - 2026-07-22

- `datarobot-workload-api`: Add `references/web-uis-behind-the-edge.md` for serving a browser-facing web app (UI + backend) through the workload endpoint — the edge gateway strips the path prefix (inbound shim + base-path derived from the injected `WORKLOAD_ID`; proton-id path needs an explicit override), is itself the auth gate and hijacks the `Authorization` header (so disable the app's own auth and trust the edge), shared-origin `_xsrf`/CSRF collisions, and WebSocket pass-through. Correct artifact-replacement guidance: same-artifact replacement is allowed for drafts, `PATCH /settings/` rolling-redeploys onto a rebuilt image, and `imageUri` is build-managed (never hand-PATCH it or PATCH the spec mid-build). Trim `SKILL.md` ~18% to stay within the context-window budget.

## [1.3.8] - 2026-07-17

- `datarobot-agent-assist`: Warn when the ports needed for local agent testing (5173, 8080, 8842) are not exposed inside a DataRobot Codespace, and stop with guidance when Agent Assist runs from an unsupported working directory. New `check_codespace.py` helper wired into the Pre-requisite Check; no-op outside a Codespace.

## [1.3.7] - 2026-07-14

- `datarobot-external-agent-monitoring`: Fix PydanticAI instrumentation — modern PydanticAI makes OpenTelemetry instrumentation opt-in, so configuring a provider alone emitted no spans; document the required `Agent.instrument_all()` call.

## [1.3.6] - 2028-07-14

- `datarobot-agent-assist`: Implement pre-coding-checklist, pre-deployment-checklist & workspace-resolution flows.

## [1.3.5] - 2028-07-08

- `datarobot-agent-assist`: Bumped application template version to 11.10.7.

## [1.3.4] - 2028-07-01

- `datarobot-agent-assist`: Improved rehearsal flow to properly handle missing LLM model cases and improved user-facing messaging; refactored Dress Rehearsal instructions into separate `references/dress-rehearsal.md` file to reduce SKILL.md token count while preserving all behavior and control-flow reliability.
- `datarobot-discover`: New skill for discovering DataRobot resources — fetches the live catalog from `datarobot.com` and, if set, from `$DATAROBOT_ENDPOINT` to surface skills, MCP servers, agents, and platform resources without search index dependency.

## [1.3.3] - 2026-06-25

- `datarobot-external-agent-monitoring`: Support instrumenting existing (brownfield) agents — built on DataRobot or elsewhere — via the "Add tracing to my agent" trigger; resolve agentless invocations to the current IDE workspace; make a DataRobot Use Case the primary telemetry target (validate an existing Use Case ID, or create a net new one via the new `create_use_case.py` helper) with the shell deployment now optional; extract the OTel config template into `reference/dr_otel_config.md`; make `verify_otel_connection.py` accept the `experiment_container-` (Use Case) entity prefix in addition to `deployment-`; defer Use Case creation/validation to the post-approval execute step (prerequisites only collect the choice) to avoid premature or duplicate creation; collect the API token via the project `.env` file rather than chat (never asked for or echoed in the transcript).
- `datarobot-setup`: Broaden trigger to cover credential failures; add env var and auth validity checks to pre-flight.
- `datarobot-workload-api`: New skill for the DataRobot Workload API — create/configure, diagnose (`CrashLoopBackOff` / `ImagePullBackOff` / `OOMKilled` / `exec format error`), observe (logs/traces/metrics/stats), and artifact lifecycle (draft→lock→production, rolling replacement, `promote`, Code-to-Workload via `dr workload code sync` when no accessible registry). Modal `SKILL.md` + bundled `scripts/` + deep `references/`.
- `datarobot-setup`: Broaden trigger to cover credential failures; add env var and auth validity checks to pre-flight.
- `datarobot-model-explainability`: Correct SHAP export guidance for `datarobot.insights.ShapMatrix` (in-memory `matrix`/`columns` or classmethod `get_as_dataframe`/`get_as_csv`); fix `compute_shap_matrix.py` `--output` export; fix anomaly assessment date-range example to use `get_explanations()` instead of `get_latest_explanations()`; fix Model diagnostics examples (`get_confusion_chart`, `get_feature_effect`); document insights diagnostics (`RocCurve`, `LiftChart`, `ConfusionMatrix`); correct documented SHAP caveats for blenders, the >1000-feature limit, `ShapImpact` source support, logit-link probability conversion, XEMP contribution wording, XEMP routing guidance, and XEMP `max_explanations` limit; raise the documented minimum SDK version to `datarobot>=3.6.0` when referencing `ShapDistributions`.

## [1.3.1] - 2026-06-02

- `datarobot-setup`: Corrected issues with setup commands.

## [1.3.0] - 2026-05-27

- `datarobot-model-explainability`: Updated SHAP guidance to use the current `datarobot.insights` APIs, added data slice and anomaly assessment coverage, added SHAP and XEMP reference docs, and added a `compute_shap_matrix.py` helper script.

## [1.2.0] - 2026-05-20

First tracked release. Skills included:

- `datarobot-agent-assist`
- `datarobot-app-framework-cicd`
- `datarobot-data-preparation`
- `datarobot-external-agent-monitoring`
- `datarobot-feature-engineering`
- `datarobot-model-deployment`
- `datarobot-model-explainability`
- `datarobot-model-monitoring`
- `datarobot-model-training`
- `datarobot-predictions`
- `datarobot-setup`
