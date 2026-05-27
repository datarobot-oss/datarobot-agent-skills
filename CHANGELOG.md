# Changelog

All notable changes to DataRobot agent skills are tracked here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
version numbers track the shared plugin version maintained across
`.claude-plugin/`, `.cursor-plugin/plugin.json`, and `gemini-extension.json`.

Each entry should be prefixed with the affected skill folder name (for example,
`` `datarobot-predictions`: ... ``) so it's easy to scan what changed per skill.

## [Unreleased]

- `datarobot-model-explainability`: migrate SHAP explanations and model diagnostics
  (ROC curve, confusion matrix, lift chart) from the legacy per-resource APIs to the
  unified `datarobot.insights` API.

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
