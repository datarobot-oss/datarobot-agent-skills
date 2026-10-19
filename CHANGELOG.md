# Changelog

All notable changes to DataRobot agent skills are tracked here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
version numbers track the shared plugin version maintained across `package.json`,
`.claude-plugin/`, `.cursor-plugin/plugin.json`, `.codex-plugin/plugin.json`, and `gemini-extension.json`.

Each entry should be prefixed with the affected skill folder name (for example,
`` `datarobot-predictions`: ... ``) so it's easy to scan what changed per skill.

Version bumps, `[Unreleased]` renames, and releases are automated&mdash;see
[`CONTRIBUTING.md`](CONTRIBUTING.md#plugin-version-management).

## [Unreleased]

### Changed

- `repo`: Pinned the tools and actions the CI workflows use (yamlfmt, license-eye, the claude, gemini and codex CLIs, and every GitHub Action by commit SHA), locked the `uv` install with `--locked`, set the Python version in `.python-version`, and limited the lint and e2e workflows to read-only permissions. Added zizmor to `task lint` to audit the workflows. Ruff and mypy updates now come from Dependabot in their own PR, and Dependabot waits 7 days after a release.
- `repo`: Configured pytest (`testpaths`, strict markers and config) so a bare `pytest` runs the integration tests, and made the pre-commit hook run ruff on staged Python files before the skill e2e step.

## [1.27.0] - 2026-10-19

- `datarobot-agent-assist`: Added NO_COLOR=True to for shell commands to prevent ANSI color escape codes
- `datarobot-agent-assist`: Revert application template version to 11.12.2.

## [1.26.0] - 2026-10-19

- `datarobot-agent-assist`: Bumped application template version to 11.12.7.

## [1.25.0] - 2026-10-16

### Added

- `datarobot-agent-assist-deploy-workload`: New sub-skill that deploys a single-container agent with the Workload API (`dr workload up`) instead of Pulumi. It applies to projects without an `infra/Pulumi.yaml`. Agent assist still uses Pulumi for the agent template, for agents that need a GPU, a standalone MCP server, guard models or many tools, and when the Workload API is off for the account.

## [1.24.0] - 2026-10-16

### Changed

- `repo`: Pinned the ruff rule set to the pre-0.16 defaults plus import order, bugbear and security rules, and excluded Markdown from `ruff format`, so upgrading ruff to 0.16 or later no longer adds rules or reformats skill docs.
- `repo`: Raised `requires-python` to 3.12, adopted ruff's expanded default rules and fixed what they found in the skill scripts and tests: `datetime.UTC`, an explicit `check=` on `subprocess.run`, `zip(strict=True)`, executable bits on scripts with a shebang, and parenthesized implicit string concatenations. `zip` in the `list_llm_models.py` table renderer now raises on mismatched lengths instead of truncating.

## [1.23.0] - 2026-10-16

### Fixed

- `datarobot-connectivity-jdbc-sql`: Fixed `tables` and `columns` building SQL that a name with a backslash could break out of on Snowflake, Redshift and other dialects that read `\'` as an escaped quote. Backslashes are now doubled in every catalog value, and BigQuery, Databricks and Spark reject a backslash in a catalog or schema name. Documented each remaining string-built query with an inline `noqa` and its reason.

## [1.22.0] - 2026-10-15

### Fixed

- `datarobot-agent-assist-simulate`: Fixed `tool_executor.py` re-executing forever when the `.venv` interpreter reports a different `sys.prefix`, for example a `.venv` without `pyvenv.cfg`. It now re-execs at most once.

## [1.21.0] - 2026-10-15

### Fixed

- `datarobot-agent-assist-simulate`: `tool_executor.py` now re-execs into the nearest `.venv` beside the tools file before importing it, so `selective_e2e` correctly resolves the agent's dependencies rather than the swarm's interpreter. Also handles async tool functions (via `asyncio.run`) and Pydantic return values (via `model_dump`) that previously caused serialization errors.

## [1.20.0] - 2026-10-15

### Added

- `datarobot-connectivity-jdbc-sql`: New skill for running SQL through DataRobot against a database reached with a caller-supplied JDBC URL and driver properties, without registering a data connection. It tests connectivity, lists tables and columns with dialect-aware catalog SQL, runs read queries via `/jdbcDataPreview/`, and runs DML/DDL via `/jdbcExecution/` only after a dry-run plan and an explicit `--confirm`. Secrets come from environment variables or `.env` and are masked in all output. Ships the standard-library `scripts/jdbc_sql.py` and references for the API contract, driver URL templates and dialect limits, and app integration, including a migration checklist for Talk to My Data.
- `repo`: Added offline preflight tests that run before the paid LLM judge. They check the agentskills.io frontmatter limits, that linked files and script paths exist, that Python and shell samples parse, that scripts start with `--help`, and that no skill file holds an internal host, employee email, private IP address or credential. The e2e CI job also prints skip reasons now.
- `repo`: Added ruff import-order, bugbear and security rules, a repo-wide shellcheck glob, actionlint for workflows, `claude plugin validate skills`, and Dependabot for GitHub Actions, uv and npm. CI now fails on Trivy secret findings and when the e2e job skips skills because the LLM gateway call failed.

### Changed

- `datarobot-agent-assist`: `setup_template.py` runs its Pulumi, `dr` and `task` commands without a shell. A missing tool now fails with an error message instead of a shell exit code.

### Fixed

- `repo`: Fixed the preflight `--help` check failing on modules inside a Python package. They use relative imports and cannot run as scripts, so the check now skips them.
- `repo`: Fixed false INCOMPLETE verdicts in the e2e skill gate. A judge report with `## Overall Verdict` was read as INCOMPLETE because the report text mentioned "incomplete". The gate now reads the verdict line at any heading level.

## [1.19.0] - 2026-10-15

### Added

- `repo`: Added `tests/integration/test_sdk_conformance.py`, which resolves every DataRobot SDK call in `SKILL.md` python fences and skill `scripts/*.py` against the installed `datarobot` package and checks its signature. Methods that do not exist and calls with wrong arguments now fail `task lint`. It needs no DataRobot account.

### Fixed

- `datarobot-predictions`: Replaced the single-argument `dr.Model.get`, the nonexistent `Model.get_features()` and `Project.get_time_series_info()` with `deployment.get_features()` and `dr.DatetimePartitioning.get` in the samples and scripts. Batch scoring uses `BatchPredictionJob.score(deployment=...)`.
- `datarobot-model-training`: Fixed the time series pattern to use `dr.DatetimePartitioningSpecification`, removed the `Dataset.create_from_file(name=...)` argument (upload, then `dataset.modify(name=...)`), and replaced the nonexistent `wait_for_completion()` with `wait_for_autopilot()`.
- `datarobot-data-preparation`: Corrected the `Dataset.create_from_file` signature in the guide and in `scripts/upload_dataset.py`.
- `datarobot-feature-engineering`: Fixed the two-argument `dr.Model.get` calls and the undefined helpers in the Quick Start.
- `datarobot-workload-api`: Tagged the credential injection payload as JSON so it parses.

## [1.18.0] - 2026-10-13

### Added

- `datarobot-connectivity-datastore-sql`: New skill for running SQL through DataRobot data connections (datastores) with their stored credentials. It lists connections and credentials, browses schemas, tables and columns, previews tables, and runs read queries via `/previewQuery/`, falling back to `/verifySQL/` where the newer routes are not available. DML/DDL runs via `/executeUpdate/` only after a dry-run plan and an explicit `--confirm`. Ships the standard-library `scripts/datastore_sql.py` and references for the API contract, per-connector capabilities and dialects, and troubleshooting.

## [1.17.0] - 2026-10-08

### Changed

- `datarobot-workload-api`: Made `dr workload config`/`up` the default deploy path from a project directory: documented the `.datarobot.yaml` manifest shape and managed-fields rule, `promote`, `--sync-env`, `--spec-file`, `delete --purge`, and added `references/cli-command-map.md` covering `diagnose`, `events`, `settings`, the `logs` filters and `code sync --push-only`.

## [1.16.0] - 2026-10-07

- `repo`: Fixed OpenAI plugin listing: category set to Developer Tools (Coding is not a valid marketplace category).
- `datarobot-app-framework-cicd`: Replaced the `curl | sh` Pulumi install in the state-management guide with Homebrew and a link to the official install docs.

## [1.15.0] - 2026-10-06

- `repo`: Fixed OpenAI plugin listing: brand color now meets 2:1 contrast on white (Indigo `#5C41FF`), category set to Coding, and listing text no longer references other AI agents.
- `datarobot-setup`: Required user confirmation before running the Linux/WSL installer scripts, and replaced the go-task `curl | sh` install with `uv tool install go-task-bin`.

## [1.14.0] - 2026-10-02

- `repo`: Added automated public Codex plugin packaging, release attachment, and manifest synchronization.
- `datarobot-agent-assist`: Expanded integration test coverage for how LLM choices flow from catalog listings into `agent_spec.md` and `.env` (gateway vs. deployed routing, `setup_and_run` failure paths, spec completeness), and added an on-prem / deployed-LLM example to `agent-spec-examples.md`.

## [1.13.0] - 2026-09-30

### Added

- `datarobot-external-agent-monitoring`: Recommend intelligent trace analysis via Tensile (`tensile>=0.12.0`). Each framework reference file gains an **Intelligent Trace Analysis via Tensile** section showing where `tensile.otel.install(tracer=False)` goes for that framework.

## [1.12.0] - 2026-09-29

- `datarobot-agent-assist`: Clarified that the "After Coding" next-steps menu must be reproduced verbatim (same wording, order, and numbers) rather than paraphrased or renumbered, after an observed case where the assistant referenced "option 3" for a menu item that was actually numbered differently.

## [1.11.0] - 2026-09-24

- `repo`: Added Codex plugin metadata and included the Codex manifest in the shared version bump workflow.
- `datarobot-workload-api`: Never gate CLI commands on a pinned `dr` version — always run `dr self update --force` first, matching `datarobot-agent-assist`'s handling. Added `references/declarative-cli-deploy.md` documenting `dr workload config`/`dr workload up`, the CLI-native one-command create/build/deploy/resize path that replaces most manual REST choreography for project-directory deploys — noting `up`/`config` can return `unknown command` even on an otherwise-current CLI, independent of `dr self update`, with the manual flows as the fallback. Fixed the Code-to-Workload state directory (`.datarobot/workload/`, not `.wapi/`), `codeRef` field placement (`imageBuildConfig.codeRef`, not directly on the container — PATCH silently drops a misplaced value), `dr workload logs --level` semantics (minimum threshold, not exact match), and `dr artifact code sync`/`build create`/`build logs` behavior against the live v0.9.0 CLI (three-way diff with remote-wins auto-resolve, `--wait`, `CANCELLED` terminal status, structured JSON build logs). Documented the edge's forwarded identity headers and spoof-test results, sharing-role casing (`OWNER`/`USER`/`CONSUMER`, uppercase), the rolling-roll proton-watch trap, and that some instances omit Workload API paths from the public OpenAPI spec. Sharpened the web-UI auth-disable guardrail to require surfacing the tradeoff to the user, not disabling unilaterally.
- `datarobot-workload-api`: Rewrote SKILL.md and all `references/*.md` for token economy — terser phrasing, fewer filler words, tighter headings — with no change in technical content. SKILL.md dropped from 6647 to 6262 tokens (still under the 6700 hard cap); reference files dropped ~12% in word count combined.

## [1.10.0] - 2026-09-22

- `datarobot-agent-assist`: Unified and increased timeouts for git commands and long running task commands in helper scripts.

## [1.9.0] - 2026-09-21

- `datarobot-agent-assist`: Increased timeouts to prevent failing some of the long running scripts/tools.

## [1.8.0] - 2026-09-02

### Added

- `datarobot-agent-assist`: Dress rehearsal exports a shareable Markdown report to `<target_dir>/rehearsal_report/rehearsal_report.md` (archived under `.datarobot/rehearsal/<session_id>/`). `DONE` always runs `--report` before any summary or menu; post-design next steps add **Review rehearsal report**. `NOTE:` observations persist via `rehearsal.py --note`. Session state lives under `.datarobot/rehearsal/` instead of the system temp dir.

### Changed

- `datarobot-agent-assist`: Bumped application template version to 11.11.6.
- `datarobot-agent-assist`: Deduplicated `SKILL.md` by pointing dress rehearsal, clone discipline, and spec validation at the reference files instead of restating them.
- `datarobot-agent-assist`: Welcome menu infers a clear free-text category (and asks when ambiguous). `frontend.type` may be held from the Clarification Phase before the first spec draft exists.
- `datarobot-agent-assist`: Tool/service secrets stay in `.env` only — coding appends `VAR_NAME=` and asks the user to paste values in their editor, never in chat, `agent_spec.md`, or source.
- `datarobot-agent-assist`: Spec-only / messy-cwd classification treats dress-rehearsal artifacts (`.datarobot/rehearsal/`, `rehearsal_report/`) as design-phase files so they do not force a subdirectory clone.

### Fixed

- `datarobot-agent-assist`: Rehearsal reports pair parallel tool returns with the matching call (previously every return was labeled with the last tool). `model_substituted` / `simulation_substituted` now compare against the originally requested model so a runtime fallback does not leave a stale flag.

## [1.7.0] - 2026-09-02

### Added

- `datarobot-agent-assist`: Support an OpenAI-completions-compatible external LLM (`AGENT_ASSIST_LLM_MODEL_NAME`, `AGENT_ASSIST_LLM_API_KEY`, `AGENT_ASSIST_LLM_BASE_URL`) as a model source alongside the LLM Gateway and deployed models, so `list_llm_models.py` and `setup_template.py --llm-base-url` can wire up a template without a DataRobot endpoint or token. Also lets `clone_template.py` override the template repo via `AGENT_ASSIST_TEMPLATE_REPO_URL`/`_BRANCH`/`_TAG`, with branch now taking priority over tag when both are set.

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
