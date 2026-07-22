# NIM + GPU REST Contract (source-grounded)

Grounded in the `datarobot/DataRobot` monorepo (`master`): Flask route registrations,
request-validator classes, and controller handlers. **Verdict: the entire NIM+GPU
create→deploy flow IS REST-scriptable.** The "UI-only" claim in earlier docs prose is
wrong. None of these are in the public Python SDK (verified against `datarobot==3.16.0`),
so the skill hits them via the `dr.Client().get/post(...)` REST escape hatch.

## Prerequisites (server-enforced)
- Feature flag **`NIM_MODELS`** — required for the NIM template create path.
- Feature flag **`MLOPS_RESOURCE_REQUEST_BUNDLES`** — required to set `resourceBundleId` on a plain version create. (`"User is not allowed to use resource bundles"` otherwise.)
- An **NGC API key stored as a secureConfig** (`/api/v2/secureConfigs/...`), referenced by `secretConfigId`.

## 1. Discover the NIM template + GPU bundle
- `GET /api/v2/customTemplates/?templateSubType=NIM_CONTAINERS` → list of NIM templates; take `templateId`.
- `GET /api/v2/mlops/compute/bundles/?useCases=customModel` → GPU resource bundles (SDK `ResourceBundle.list(use_cases=["customModel"])`). Bundle must have `customModel` in `use_cases`.
- (Optional) the UI's bundle recommendation: `getCustomTemplatesFilters({resourceBundleId, templateSubType})` maps a NIM's GPU requirement to a recommended bundle.

## 2. Create the NIM custom model + version (one call, recommended)
```
POST /api/v2/customModels/fromModelTemplate/     (Content-Type: application/json; flag NIM_MODELS)
{
  "templateId": "<NIM template id>",
  "resourceBundleId": "<gpu bundle id>",            # required
  "secretConfigId": "<secureConfig id w/ NGC key>", # optional but needed for gated NIMs
  "nimContainerTagOverride": "latest"               # optional
}
→ 201 { "customModelId": "...", "customModelVersionId": "..." }
```
Controller: `public_api/custom_model/custom_model_templates_controller.py:119`
(`CustomModelCreateFromTemplateController`, `requires_features=["NIM_MODELS"]`).
Validator (`:75`): `template_id` (required), `resource_bundle_id` (required),
`secret_config_id` (optional), `nim_container_tag_override` (optional).
Newer alt path the current UI uses: `POST /api/v2/customTemplates/{templateId}/artifacts/`
with `{secretConfigId, resourceBundleId, containerTagOverride, name}`.

## 3. (Alt) GPU bundle on a plain custom model version
```
POST /api/v2/customModels/{customModelId}/versions/   (multipart/form-data; flag MLOPS_RESOURCE_REQUEST_BUNDLES)
baseEnvironmentId = <gpu base environment id>     # at least one of baseEnvironmentId/baseEnvironmentVersionId required
isMajorUpdate     = true                          # defaults true, not required
resourceBundleId  = <gpu bundle id>               # camelCase on wire; mutually exclusive with maximumMemory/desiredMemory
file=@model.py / filePath=model.py                # as needed
→ 201 { "id": "<new version id>", "customModelId": "...", ... }
```
Field declared in `CustomModelVersionResourcesValidator` (`validators.py:1222`), create
validator `CustomModelVersionCreateValidator` (`:1492`), response `id` is the new version
id (`CustomModelVersionResponseValidator`, `:2394`). Multipart enforced via
`FormValidationMixin` (`controllers.py:3392`).

## 4. Register the version as a model package
```
POST /api/v2/modelPackages/fromCustomModelVersion/   { "customModelVersionId": "<id>", "name": "..." }
→ { "id": "<modelPackageId>" }
```
SDK equivalent: `RegisteredModelVersion.create_for_custom_model_version(custom_model_version_id, name=...)`.
(Field name `customModelVersionId` inferred from SDK behavior — confirm against the registry controller if it errors.)

## 5. Deploy to a serverless GPU prediction environment
```
GET  /api/v2/predictionEnvironments/                 # pick the serverless / DataRobot-platform PE
POST /api/v2/deployments/fromModelPackage/
{ "modelPackageId": "<id>", "label": "my-nim", "predictionEnvironmentId": "<serverless PE id>" }
→ 202 async; poll Location; final deployment has "id"
```
SDK equivalent: `Deployment.create_from_registered_model_version(model_package_id, label, prediction_environment_id=...)`.
Pass **either** `predictionEnvironmentId` **or** `defaultPredictionServerId`, never both.
GPU sizing rides on the version's `resourceBundleId`, not the PE.

## 6. Expose as MCP tool
Tag the deployment `tool=tool` → hand off to `datarobot-register-mcp-tool`. NIM auto-detects
as chat (`supports_chat_api`) → `/chat/completions`, no inputSchema authoring needed.

## Confidence & gaps
- Verified in server source: §1–§3 (routes, validators, flags, multipart, response id), NIM controller/validator/flag.
- Inferred (not line-verified this pass): §4 `modelPackages/fromCustomModelVersion/` body key, NGC secureConfig schema. Confirm `customModelVersionId` against `MLOps_Tests/.../test_create_from_custom_model_version.py` before relying on it.
