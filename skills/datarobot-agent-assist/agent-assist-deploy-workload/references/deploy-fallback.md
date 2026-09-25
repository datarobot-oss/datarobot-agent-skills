# Deploy without dr workload up

Use this only when `dr workload up` can't run: the CLI won't update, `up` is missing even with the flag set, or `up` fails in a way that isn't about the app. Tell the user you're switching and why.

Each step has the CLI command first and the REST call after it. `dr artifact` and the rest of `dr workload` are GA and need no flag. Use REST only if the CLI isn't usable at all.

For REST, get credentials into the shell without printing them: `eval "$(dr auth export)"`. Base URL is `$DATAROBOT_ENDPOINT` (ends in `/api/v2`), header `Authorization: Bearer $DATAROBOT_API_TOKEN`.

## First deploy

1. Find an execution environment. You need its id and its `latestSuccessfulVersion.id`, not `latestVersion`, which can point at a failed build.
   REST: `GET /executionEnvironments/?searchFor=Python&limit=10`. A 403 means the user lacks read permission on environments. Ask them for the two ids.

2. Write `artifact.yaml` and create the artifact.

   ```yaml
   name: <agent-name>
   type: agent
   spec:
     containerGroups:
       - name: default
         containers:
           - name: main
             primary: true
             imageUri: placeholder:latest
             port: 8080
             readinessProbe: {path: /healthz, port: 8080, initialDelaySeconds: 10}
             imageBuildConfig:
               dockerfile:
                 source: generated
                 executionEnvironmentId: <ee id>
                 executionEnvironmentVersionId: <ee version id>
                 entrypoint: ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
             environmentVars: <same block as SKILL.md section 3>
   ```

   `type` sits beside `spec`, never inside it. Inside, it's dropped without an error and the agent becomes a service.
   CLI: `dr artifact create --spec-file artifact.yaml --output-format json`.
   REST: `POST /artifacts/` with the same body as JSON. Keep the returned id.

3. Upload the code and point the artifact at it.
   CLI: `dr artifact code init <artifact_id> --yes`, then `dr artifact code sync --yes`. Sync zips the project, uploads it, re-locks a stale `uv.lock` and sets `codeRef` for you. `code init` keeps the artifact binding in `.datarobot/workload/`, so later commands can leave the artifact id out.
   If sync refuses because a file changed both locally and on the artifact, ask the user before rerunning with `--accept-remote`. Remote wins, and the local copies are saved as `<file>.LOCAL.<timestamp>`.
   REST:
   - Zip the project, leaving out what `.dockerignore` excludes, `.env`, and `.venv`.
   - `POST /files/fromFile/` as multipart. You get 202 with the catalog ids and a status URL.
   - Poll the status URL. A 303 means processing is done.
   - `GET /artifacts/<id>/`. Set `codeRef` at `containers[].imageBuildConfig.codeRef`, not at `containers[].codeRef`:
     `{"datarobot": {"catalogId": "<id>", "catalogVersionId": "<vid>"}}`
   - Remove the read-only fields the GET returns (`build`, `imageOutdated`, `routes`, `securityContext`) and PATCH the spec back.
   - GET again and confirm `codeRef` is there. A misplaced field is dropped silently and the PATCH still reports success.

4. Build.
   CLI: `dr artifact build create <artifact_id> --wait`. It waits until the new image is the one the artifact points at.
   REST: `POST /artifacts/<id>/builds` with body `{}`. Poll `GET /artifacts/<id>/builds/<build_id>`.
   - `BUILT` is not done. Wait for `COMPLETED`, and then for `imageApplied: true`. On a platform without that field, wait until the artifact's `imageUri` ends in `:<build_id>`.
   - On `FAILED` or `CANCELLED`, read `GET /artifacts/<id>/builds/<build_id>/logs`. It returns plain text.
   - Don't PATCH the artifact while a build is running. It clobbers the new image.

5. Create the workload. Write `workload.yaml`:

   ```yaml
   name: <agent-name>
   artifactId: <artifact_id>
   importance: low
   runtime:
     containerGroups:
       - name: default
         replicaCount: 1
         containers:
           - name: main
             resourceAllocation: {cpu: 0.5, memory: "512MB"}
   ```

   Group and container names must match the artifact.
   CLI: `dr workload create --spec-file workload.yaml --output-format json`, then poll `dr workload status <id>` until `running`.
   REST: `POST /workloads/`, then poll `GET /workloads/<id>/`. States are `submitted`, `provisioning`, `launching`, `running`. `statusDetails.logTail` shows the last container lines.
   If the create returns `422 runtime_image_uri ... None` right after a build, the registry hasn't caught up. Wait a few seconds and retry.

6. The endpoint is `<DATAROBOT_ENDPOINT>/endpoints/workloads/<workload_id>/`, which is also what `dr workload endpoint <id>` prints. Verify as in SKILL.md section 5.

Write the workload id into a small file in `<target_dir>` (for example `.workload-id`) so the next session can redeploy. The CLI already keeps the artifact binding in `.datarobot/workload/`. On raw REST, save the artifact id there too.

## Redeploy

There's no CLI command for the roll, so step 3 is REST either way.

1. Code or dependency change: sync and build again (first-deploy steps 3 and 4). Same artifact, new image.
2. Env var change only: GET the artifact, strip the read-only fields, change `environmentVars`, and PATCH it back. No build.
3. Roll the workload onto the new state: `GET /workloads/<id>/settings/`, then `PATCH /workloads/<id>/settings/` with the same `runtime` body. Sending it unchanged is fine. That's what triggers the roll.
4. Watch `GET /workloads/<id>/protons/` until the proton with `role: active` has a new id. The old one stays in the list as `stopped`, so don't wait for the list to shrink to one. The workload itself stays `running` throughout.

If you skip the roll, the workload keeps serving the old image. It doesn't pick up a rebuild on its own.

## Lock and clean up

- Lock (one way, ask first): `dr artifact lock <artifact_id>`, or REST `PATCH /artifacts/<id>/` with `{"status": "locked"}`. After that, changes need a new artifact and `POST /workloads/<id>/replacement/`. See the `datarobot-workload-api` skill, section 4.
- Tear down: `dr workload stop <id>`, `dr workload delete <id>`, `dr artifact delete <artifact_id>`, in that order. Only drafts can be deleted.
