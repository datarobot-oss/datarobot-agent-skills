# `dr workload config` + `dr workload up` — the declarative CLI path

Confirmed against `dr` v0.12's `--help`; re-verify flags on a materially
different CLI version. **Prefer this path when the user works from a
project directory** (an existing app, or source to build server-side). It
replaces the create → sync → build → wait → deploy choreography in
`code-to-workload.md` with two commands and a committed file, and it covers
bring-your-own-image too.

## `up` or the granular commands: the agent's call

`up` is a convenience over the same endpoints the granular verbs call, and
it decides a lot on its own: whether to sync code, whether a build is
needed, whether to roll or resize in place, whether to wait, what counts as
drift. That is the point when the goal is "make what is running match this
file". It is the wrong tool when the agent needs to control or observe each
step, and it will never expose the full range of what the API and the
granular commands do (replacement timing, several candidate artifacts,
multi-container groups, mid-build inspection, settings bodies beyond
sizing). Reach for `dr artifact create`/`code sync`/`build create`,
`dr workload create`/`settings`/`promote` and `dr artifact lock`, or raw
REST, whenever:

- the user asks for one specific step, not a reconciled end state;
- an intermediate result matters (the artifact id before a build, the
  build log while it runs, a candidate artifact that must not go live yet);
- the manifest's managed-fields rule or its drift reverts would surprise
  the pipeline;
- the spec needs something `config` has no question for and `up` has no
  plan line for.

`cli-command-map.md` lists every verb and its route; `code-to-workload.md`
and `lifecycle-flows.md` walk the manual flows. The two styles mix: a
project deployed by `up` can be inspected, scaled, promoted or rolled with
the granular verbs, and `up` picks up where they left off on its next run.

## What it is

- `dr workload config` — one-time setup. Asks a handful of questions, or
  takes them from flags with `--yes`, and writes `.datarobot.yaml` at the
  project root. With a manifest present it prints the path and exits: edit
  the YAML, do not re-answer. Delete the file to start over.
- `dr workload up` — reads `.datarobot.yaml`, compares it and the working
  tree against what is running, prints a plan, applies the difference. No
  manifest and a terminal: runs the same setup, writes the file, deploys.
  No manifest and no terminal: refused, never deploys by guessing.
- `dr workload promote` — locks the version a workload is running in place
  and gives it a version number. `up --promote` does the same as part of a
  deploy.

Both take `--dir <path>`; `up` searches upward from it for the manifest, so
it works from any subdirectory of the project.

## The manifest, `.datarobot.yaml`

The file is the platform's **workload-create spec, verbatim** (the document
`dr workload create --spec-file` takes; fields in `schema-reference.md`) plus
two conveniences the CLI manages:

- `workloadId` — written by the first `up`, read by every later one to find
  the workload, stripped before anything is sent. **Commit it**: a checkout
  without it creates a second workload.
- `dr-credential:<credential-id>/<key>` as an env var value — shorthand for
  the credential-backed object form (`source: dr-credential`,
  `drCredentialId`, `key`). Either form is accepted.

What `config` writes for a project with a Dockerfile:

```yaml
workloadId: 68b0c1d2e3f4a5b6c7d8e9f0 # managed by the CLI
name: my-app
importance: low # low | moderate | high | critical

artifact:
  name: my-app-artifact
  type: service
  spec:
    containerGroups:
      - name: default
        containers:
          - name: primary
            primary: true
            port: 8080 # must be 1024 or above
            imageBuildConfig:
              dockerfile:
                source: provided
            environmentVars:
              - name: LOG_LEVEL
                value: info
              - name: OPENAI_API_KEY
                value: dr-credential:PLACEHOLDER/apiToken

runtime:
  containerGroups:
    - replicaCount: 1
      containers:
        - name: primary
          resourceAllocation: {cpu: 0.5, memory: 512MB}
```

Generating the file by hand is fine: write this shape, omit `workloadId`,
run `dr workload up`. Three image sources, one per container, never
`imageUri` and `imageBuildConfig` together:

| Image source | In the file | `config` flags |
| --- | --- | --- |
| Your Dockerfile | `imageBuildConfig.dockerfile.source: provided` | none when `./Dockerfile` exists |
| DataRobot base image + your code | `imageBuildConfig.dockerfile.source: generated` with `executionEnvironmentId`, `executionEnvironmentVersionId`, `entrypoint` | `--build-mode generated --execution-environment <name-or-id> --entrypoint "..."` |
| Image already published | `imageUri` | `--build-mode image --image <uri>` |

The first two make `up` push the working tree and wait for a platform build
on the first deploy and whenever the code changes. The third deploys in one
call and never syncs code. The runtime group needs no `name` (the platform
assigns `default`); a runtime with several groups has to name them. No
readiness probe is written unless `--health <path>` is given: a guessed path
kills a healthy deploy. Everything else in the spec vocabulary (GPU bundles,
autoscaling, secrets, sidecars, probes, `agent` type) is written and deployed
as it stands.

**Managed-fields rule.** Whatever the file says, `up` makes true; whatever it
leaves out, `up` leaves alone; deleting a line stops managing that field
rather than reverting it. A value changed in the UI that the file names is
reported as drift and put back on the next `up`. Surface this before running
`up` on a manifest someone may have hand-edited around.

Machine state lives beside the code in `.datarobot/workload/` (artifact and
catalog binding, sync index, history, rollback copies), never in the
manifest. Add it to `.gitignore`.

## What `up` does on each run

The plan is printed, then carried out; `--dry-run` prints it and stops, which
is the answer to "what would this deploy" in CI. Nothing to do is
`Already up to date`, exit 0.

| Change | Detected by | What `up` does |
| --- | --- | --- |
| Code (only when the file builds the image) | working tree vs what was last pushed to the artifact | pushes the diff, builds, mints a new artifact version, rolls the workload onto it |
| Artifact spec (env vars, port, probes, image) | file's `artifact` block vs the artifact the workload runs | new version and roll; a change the image can take (env var, port, probe, route) keeps the running image, so seconds rather than minutes. On a draft it is written in place and the workload rolled again, no new version |
| Runtime (replicas, cpu, memory) | file's `runtime` block vs live runtime | settings update in place, no version; rides along when a roll happens anyway |

- A workload that does not exist is created from the file in one call. A
  stopped one is started and reconciled in the same run. One still starting,
  stopping or mid-rollout is waited out and re-read first. An errored one is
  rolled when the file has something new to roll; with nothing new the run is
  refused and names the platform's reason (`--force-build` rebuilds a
  platform-built image, the fix when the registry lost it).
- Rolling never changes the endpoint; the serving generation keeps serving
  until the new one is ready.
- A build that would reproduce the image already on the artifact is skipped;
  `--force-build` overrides.
- Locking is one-way: the next version of a locked artifact is a new
  artifact, locked to match, so a locked workload keeps deploying without
  `--promote` again. Interactive runs ask for the workload name before
  rolling a locked version; `--yes` or no terminal rolls without asking.
- `--detach` returns once the deploy is requested. `--poll-timeout` (default
  30m) bounds each wait, including the build; giving up ends the wait, not
  the deploy.
- `--output-format json` prints one document with the plan and result and
  skips the setup wizard; stderr carries everything else.

## Promote: `dr workload promote [<workload-id>]`

`POST /workloads/{id}/promote/` through the CLI: the draft artifact the
workload serves is locked in place and versioned, nothing rebuilt or rolled.
The id is optional in a project directory (read from the manifest, confirmed
unless `--yes`). Refused with the platform's reason when the version is
already locked, nothing is running, or a rollout is in flight; only the
artifact's owner can promote. Share the locked version with other workloads
by naming its `artifactId` in their spec. `dr workload up --promote` promotes
whatever ends up live, even when the deploy minted no new version.

## Environment variables and secrets

By default `config` carries the project's `.env` into the manifest: ordinary
values as literals, secret-looking ones as `dr-credential:PLACEHOLDER/<key>`
references to complete later. `--skip-env` omits it.

`--sync-env` (on `config` or `up`) brings the manifest into line with `.env`
in one act: adds names the file lacks, rewrites a literal whose value moved,
re-sends the credential behind a secret, removes a name `.env` dropped. It
prints a table of what it would do and asks before writing or sending
anything, because `.env` winning on everything means a stale copy can delete
something a running workload needs. Secrets are re-sent without comparison:
the platform never returns a stored value. On `up`, a re-sent secret reaches
the containers that deploy replaces; a deploy with nothing else to do
replaces none and says how to restart.

## Starting from a prepared spec: `--spec-file`

`config --spec-file <path>` and `up --spec-file <path>` take the answers from
an existing artifact spec or workload spec (JSON or YAML, what `dr artifact
create` and `dr workload create` take) and ask only what it leaves open: a
name when it has none, the `.env` import, the sizing when there is no
`runtime` block. The spec file is left alone; `.datarobot.yaml` is written
beside the code. Refused once a manifest exists; not combinable with the
build-source flags, `--type`, `--a2a-enabled`, `--sync-env` or
`--workload-id`. An artifact spec names no workload, so headless use needs
`config --spec-file ... --name ... --yes` before `up`.

## Binding an existing workload: `--workload-id`

`config --workload-id <id>` downloads the live spec into the manifest instead
of naming a new workload (exclusive with `--name`), so a first `up` from it
cannot quietly downgrade something running. The bound workload's probe and
importance are kept.

## Tear-down: `dr workload delete --purge`

A plain `delete` removes the workload and clears the manifest's `workloadId`.
`--purge` also removes what the deploy created: the credentials this project
minted, the draft artifact it ran when nothing else references it, and
`.datarobot/workload/`, so the next `up` starts from scratch. A locked
artifact and a credential the project did not mint are kept and named, and a
reference to a removed credential is reset to the placeholder the next
`--sync-env` fills.

## CI recipe

```bash
export DATAROBOT_CLI_NON_INTERACTIVE=1          # or pass --yes
dr workload up --dry-run --output-format json   # review the plan
dr workload up --yes                            # apply; exit != 0 on refusal or failed rollout
dr workload status                              # id read from the manifest
```

`DATAROBOT_CLI_NON_INTERACTIVE=1` answers every `up` prompt. `delete` and
`promote` of a workload named only by the manifest still need `--yes`: that
variable is set once per pipeline, not as consent to lock or delete something
nobody named.

## Cases `up` does not cover

- Explicit `warmupDurationMinutes`/`keepOldVersionMinutes` on a replacement:
  `up` does not expose `ReplacementConfig`; use
  `POST /workloads/{id}/replacement/` (`lifecycle-flows.md`).
- Inspecting intermediate artifact or build state (build logs mid-build,
  several candidate artifacts): `dr artifact build logs`, `dr artifact code
  versions`, or REST.
- A pipeline that must not inherit the managed-fields rule: granular CLI
  calls or REST give one-shot, explicit control.
- Keeping the remote code catalog from touching a git working copy during a
  manual loop: `dr artifact code sync --push-only` uploads local changes and
  leaves every remote change alone, refusing conflicts.

The full verb-to-route map, including `diagnose`, `events`, `settings` and
the `logs` filters, is in `cli-command-map.md`.
