# Changelog

All notable changes to DataRobot agent skills are tracked here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
version numbers track the shared plugin version maintained across
`.claude-plugin/`, `.cursor-plugin/plugin.json`, and `gemini-extension.json`.

Each entry should be prefixed with the affected skill folder name (for example,
`` `datarobot-predictions`: ... ``) so it's easy to scan what changed per skill.

## [Unreleased]

## [1.4.0] - 2026-07-20

- `datarobot-gap-analysis`: New skill. Scores any agent repository (DataRobot-built or not) against a 40-factor enterprise-readiness framework across seven risk pillars (Security, Identity, AI Governance, Reliability, Ops, IT Conformance, Regulatory & Policy) and four evaluation layers (deterministic scanning, dependency/supply-chain analysis, LLM-based code reasoning, configuration conformance), recommends a Patch/Hybrid/Re-platform remediation path, and can apply safe fixes on a dedicated branch. Vendors the `gap-analysis` engine prototype; hands off structural re-platform cases to `datarobot-agent-assist`.
- `datarobot-agent-assist`: Mention `datarobot-gap-analysis` as a follow-up step after a successful deploy.

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
