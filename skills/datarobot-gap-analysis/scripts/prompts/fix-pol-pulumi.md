# Fix: enable a DataRobot risk-management mitigation via pulumi-datarobot

You are given a Pulumi program file that already uses the `pulumi-datarobot`
provider, and ONE unsatisfied risk-management mitigation (the finding's
condition id tells you which). Your job is to add the missing configuration to
the EXISTING resources in this file, the way DataRobot expects the mitigation
to be enabled.

What each condition needs (pulumi-datarobot provider, Python SDK naming;
mirror the file's own language/SDK if it uses TypeScript/Go):

- **POL-DR-DRIFT-TRACKING** — on the `datarobot.Deployment` resource, add
  `drift_tracking_settings=datarobot.DeploymentDriftTrackingSettingsArgs(
  target_drift_enabled=True, feature_drift_enabled=True)`.
- **POL-DR-ACCURACY-TRACKING** — on the `datarobot.Deployment` resource, add
  `association_id_settings=datarobot.DeploymentAssociationIdSettingsArgs(
  column_names=[...], required_in_prediction_requests=True)`. Use a plausible
  id column from context; note in `manual_followup` that the org must confirm
  the column and wire an actuals feed.
- **POL-DR-BIAS-AND-FAIRNESS-TRACKING** — on the `datarobot.Deployment`
  resource, add `bias_and_fairness_settings=
  datarobot.DeploymentBiasAndFairnessSettingsArgs(protected_features=[...],
  preferable_target_value=..., fairness_metric_set=..., fairness_threshold=...)`.
  Protected features are org-specific: pick placeholders from context and flag
  them in `manual_followup`.
- **POL-DR-DEPLOYMENT-NOTIFICATION** — add a `datarobot.NotificationChannel`
  and a `datarobot.NotificationPolicy` whose related entity is the existing
  deployment (at least one active policy).
- **POL-DR-PROMPT-INJECTION-GUARD / POL-DR-PII-DETECTION-GUARD /
  POL-DR-TASK-ADHERENCE-GUARD / POL-DR-AGENT-GOAL-ACCURACY-GUARD /
  POL-DR-ROUGE-1-GUARD / POL-DR-FAITHFULNESS-GUARD** — on the
  `datarobot.CustomModel` resource, append an entry to `guard_configurations`
  using the STANDARD template for that guard type (the platform recognizes the
  standard templates, not lookalikes), with `stages` (prompt and/or response as
  appropriate) and an `intervention` block. Note in `manual_followup` that the
  intervention action (report vs block) is a product decision.

The deployment may be created through the `datarobot-pulumi-utils` wrapper
`CustomModelDeployment(...)` instead of a bare `datarobot.Deployment`; it
creates a Deployment under the hood, so add the deployment settings through
the wrapper's deployment arguments (keeping its calling convention) rather
than introducing a duplicate Deployment resource.

Rules:
- Edit only what the mitigation needs; never restructure unrelated resources.
- If the file has no `datarobot.Deployment` / `CustomModelDeployment` (for
  deployment settings) or no `datarobot.CustomModel` (for guards), return
  `can_fix: false` and explain what is missing.
- Keep the file's existing style (SDK language, args-object vs dict literals,
  naming).
- Anything org-specific (protected features, association id column, guard
  intervention action, notification channel target) gets a sensible placeholder
  AND a `manual_followup` entry naming the decision the org must make.
