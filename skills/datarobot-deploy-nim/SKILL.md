---
name: datarobot-deploy-nim
description: Deploy an NVIDIA NIM on DataRobot with a GPU resource bundle and expose it as an MCP tool. Use when someone wants to stand up a NIM (e.g. a CoPilot model) and call it as a tool from an assistant, including choosing GPU resources.
---

# DataRobot Deploy NIM Skill

This skill walks you through the end-to-end process of deploying an NVIDIA NIM on DataRobot — from discovering the right template and GPU resource bundle, through creating and deploying the NIM, to exposing it as an MCP tool that Claude or any MCP client can call natively. Every step is fully REST-scriptable via the DataRobot Python SDK's `dr.Client()` escape hatch; nothing in this flow requires the DataRobot UI.

## Quick Start

These four commands take you from nothing to a callable NIM tool in Claude.

**Step 1 — Discover templates and GPU bundles.** List the available NIM templates and GPU resource bundles on your cluster:

```bash
python scripts/discover_nim_options.py
```

To filter by model name (e.g. a substring like "llama" or "mistral"):

```bash
python scripts/discover_nim_options.py --name llama
```

Note the `templateId` of the NIM you want and the `bundleId` of a GPU resource bundle whose `useCases` includes `customModel`.

**Step 2 — Create the NIM model.** Instantiate the NIM as a DataRobot custom model from the template:

```bash
python scripts/create_nim_from_template.py \
  --template-id <templateId> \
  --resource-bundle-id <bundleId> \
  --secret-config-id <secureConfigId>
```

The script prints `customModelId` and `customModelVersionId`. Keep the version ID — you need it in the next step.

**Step 3 — Deploy to a serverless GPU prediction environment.** Register the version as a model package and create a deployment:

```bash
python scripts/deploy_nim.py \
  --custom-model-version-id <customModelVersionId> \
  --label "my-nim-deployment"
```

Pass `--prediction-environment-id <id>` to target a specific serverless GPU prediction environment if your cluster has more than one. The script prints the deployment ID when the async job completes.

**Step 4 — Expose as a tool.** Invoke the `datarobot-register-mcp-tool` skill to tag the deployment `tool=tool` and surface it in your MCP client. Because NIM deployments auto-detect as chat models (`supports_chat_api = true`), no `inputSchema` authoring is needed — the MCP server generates the chat interface automatically.

## Prerequisites

**DataRobot access.** `DATAROBOT_ENDPOINT` (ending in `/api/v2`) and `DATAROBOT_API_TOKEN` must be set, and the `datarobot` Python SDK installed. Run the `datarobot-setup` skill first if not — it installs the SDK, configures credentials, and validates authentication.

Beyond access, three things must be in place before running any script. Two are cluster-level feature flags that a DataRobot operator must enable; the third is your NGC API key stored as a DataRobot secureConfig.

**Feature flag `NIM_MODELS`.** This flag gates the `POST /api/v2/customModels/fromModelTemplate/` route. Without it, the create-from-template call returns a 403 with the message "User is not allowed to create from template". Contact your DataRobot platform administrator or DataRobot support to enable this flag.

**Feature flag `MLOPS_RESOURCE_REQUEST_BUNDLES`.** This flag gates the ability to attach a `resourceBundleId` to a custom model version. Without it, any attempt to set a GPU bundle returns "User is not allowed to use resource bundles". On DataRobot Cloud, this flag is enabled by default for GPU-enabled organizations. On-premises operators enable it in the admin panel.

**NGC API key stored as a secureConfig.** NVIDIA gates most production NIM images behind an NGC API key. Store your key in DataRobot so the platform can authenticate to the NGC registry on your behalf. To create a secureConfig, POST to `/api/v2/secureConfigs/` with `{"name": "my-ngc-key", "apiToken": "<your-ngc-key>"}`. The returned `id` is your `secretConfigId`. Pass it to `create_nim_from_template.py` with `--secret-config-id`. If your organization has set up a shared secureConfig for NGC access, ask your DataRobot admin for its ID.

GPU capacity is an infrastructure concern, not a quota you can query via API. The GPU resource bundles visible in step 1 reflect what your cluster operator has defined. If no GPU bundle appears, your cluster has no GPU nodes provisioned — escalate to your infrastructure team.

## Step 1 — Discover the NIM Template and GPU Bundle

`scripts/discover_nim_options.py` makes two REST calls and prints the results side by side.

For NIM templates it calls `GET /api/v2/customTemplates/?templateSubType=NIM_CONTAINERS`. Each template represents one NVIDIA NIM container image (e.g. `meta/llama-3-8b-instruct`, `nvidia/mistral-7b-instruct`). The response includes the `templateId`, the container image name, a human-readable display name, and the minimum GPU memory the NIM requires. Pass `--name <substr>` to filter by display name substring.

For GPU resource bundles the script calls `ResourceBundle.list(use_cases=["customModel"])` (SDK equivalent of `GET /api/v2/mlops/compute/bundles/?useCases=customModel`). This returns only bundles whose `useCases` field includes `customModel` — these are the bundles you can attach to a custom model version. Each bundle is printed with its `id`, `gpu_count`, and `gpu_memory_bytes` (GPU memory in bytes). Match the NIM's minimum GPU memory requirement to a bundle with sufficient `gpu_memory_bytes`.

There is no platform API to check real-time GPU availability. If a deployment later fails with an insufficient-capacity error, work with your cluster operator to either scale GPU nodes or choose a smaller NIM.

## Step 2 — Create the NIM Model

`scripts/create_nim_from_template.py` issues a single REST call:

```
POST /api/v2/customModels/fromModelTemplate/
{
  "templateId": "<NIM template id>",
  "resourceBundleId": "<gpu bundle id>",
  "secretConfigId": "<secureConfig id>",
  "nimContainerTagOverride": "latest"  // optional — defaults to latest
}
```

This route is defined in `public_api/custom_model/custom_model_templates_controller.py` and requires the `NIM_MODELS` feature flag. On success it returns HTTP 201 with `{ "customModelId": "...", "customModelVersionId": "..." }`. Both IDs are printed and also written to stdout in `KEY=value` format for easy shell capture.

`secretConfigId` is optional in the API spec but required in practice for most gated NIM images. Omit it only for open-weight NIM images that do not require NGC authentication. `nimContainerTagOverride` defaults to `latest` if omitted; pin a specific tag (e.g. `"24.12"`) when you need a reproducible model version.

The `resourceBundleId` is passed at creation time and baked into the version. It determines which GPU type and size the deployment will request. Changing the bundle after creation requires creating a new version — there is no in-place update.

## Step 3 — Register and Deploy to a Serverless GPU Prediction Environment

`scripts/deploy_nim.py` executes a two-step REST flow: register the custom model version as a model package, then create a deployment from that package.

**Register the version.** The script calls:

```
POST /api/v2/modelPackages/fromCustomModelVersion/
{ "customModelVersionId": "<id>", "name": "<label>" }
```

This is equivalent to `dr.RegisteredModelVersion.create_for_custom_model_version(custom_model_version_id, name=label)` in the Python SDK. The response contains `{ "id": "<modelPackageId>" }`.

**Create the deployment.** The script then calls:

```
POST /api/v2/deployments/fromModelPackage/
{
  "modelPackageId": "<modelPackageId>",
  "label": "<label>",
  "predictionEnvironmentId": "<serverless PE id>"
}
```

This is equivalent to `dr.Deployment.create_from_registered_model_version(model_package_id, label, prediction_environment_id=pe_id)`. The API returns HTTP 202 with a `Location` header. The script polls the location URL until the deployment reaches a ready state, then prints the final `deploymentId`.

**Prediction environment selection.** If you pass `--prediction-environment-id`, the script uses it directly. Otherwise the script calls `GET /api/v2/predictionEnvironments/` and picks the first serverless (DataRobot-managed) environment. On most clusters there is exactly one; if there are multiple, specify the ID explicitly. GPU sizing is carried by the version's `resourceBundleId` — you do not configure GPU resources on the prediction environment itself.

Never pass both `predictionEnvironmentId` and `defaultPredictionServerId` in the same request; the API treats them as mutually exclusive.

## Step 4 — Expose as a Tool

Once the deployment is live, expose it to MCP clients by tagging it and registering it with the `datarobot-register-mcp-tool` skill.

NIM deployments automatically satisfy the chat detection check: `supports_chat_api` is set to `true` for NIM-backed deployments, so the MCP server routes calls through `/chat/completions` and generates a chat-style tool interface. You do not need to author an `inputSchema` or run the `datarobot-define-tool-schema` skill.

After the `datarobot-register-mcp-tool` skill completes, your NIM is callable by Claude and any other MCP client using the standard OpenAI chat interface — system prompt, user message, temperature, and all. The deployment label becomes the tool name that the LLM sees.

## Scripts

- `scripts/discover_nim_options.py [--name <substr>]` — lists NIM templates from `GET /api/v2/customTemplates/?templateSubType=NIM_CONTAINERS` and GPU resource bundles from `GET /api/v2/mlops/compute/bundles/?useCases=customModel`; filters templates by display name substring when `--name` is given.
- `scripts/create_nim_from_template.py --template-id <id> --resource-bundle-id <id> [--secret-config-id <id>] [--container-tag-override <tag>]` — calls `POST /api/v2/customModels/fromModelTemplate/` and prints `customModelId` and `customModelVersionId`.
- `scripts/deploy_nim.py --custom-model-version-id <id> --label <name> [--prediction-environment-id <id>]` — registers the version via `POST /api/v2/modelPackages/fromCustomModelVersion/`, creates the deployment via `POST /api/v2/deployments/fromModelPackage/`, polls until ready, and prints the deployment ID.

## Related skills

- `datarobot-setup` — install the SDK, configure authentication, set env vars (run first if credentials are missing)
- `datarobot-register-mcp-tool` — expose the deployed NIM as an MCP tool (this skill hands off to it in step 4)
