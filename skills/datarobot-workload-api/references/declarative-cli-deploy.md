# `dr workload config` + `dr workload up` — the declarative CLI path

> **`up`/`config` are newer than the rest of `dr workload`/`dr artifact` and
> can be missing (`Error: unknown command`) even on an otherwise-current,
> GA CLI.** `dr self update --force` doesn't reliably fix this. If either is
> unavailable, use the manual REST/CLI-granular flows in `code-to-workload.md`
> and SKILL.md sections 1/4 instead — there is no raw-REST equivalent of
> `up`'s diff-and-apply behavior, since it's a client-side convenience over
> the same endpoints those flows already call directly.

Confirmed against `dr` v0.9.0's own `--help`; re-verify flags if you're on a
materially different CLI version. This pair is the CLI-native alternative to
the manual create → (build) → deploy/redeploy choreography documented
elsewhere in this skill and in `code-to-workload.md`. **Prefer it whenever the
user is working from a project directory** (an existing app, or C2W source)
**and both subcommands are available** — it's far less wonky than
hand-rolling `curl`/`httpx` for the same job, and it also covers the plain
bring-your-own-image case, not just C2W.

## What it is

- `dr workload config` — one-time setup wizard. Answers a handful of questions
  (or takes flags non-interactively) and writes a committed `.datarobot.yaml`
  manifest at the project root: the platform's own workload-create spec plus
  the `workloadId` binding the CLI manages. Re-running it with a manifest
  already present just prints its path and exits — edit the YAML directly
  instead of re-answering questions.
- `dr workload up` — reads `.datarobot.yaml`, diffs it (and the working tree)
  against what's actually running, and applies only the difference. No
  manifest + a terminal → runs `config` then deploys in one shot. No manifest
  + no terminal → hard error (never deploys by guessing).

## Key behaviors that replace manual REST choreography

- **A manifest naming a published image deploys in one call** — no manual
  artifact create + workload create dance.
- **A manifest that asks the platform to build** creates the artifact, pushes
  the working tree, and waits for the image before deploying — the CLI
  absorbs the whole `code sync` → `build create` → wait-for-`COMPLETED` →
  redeploy loop from `code-to-workload.md`'s "Iteration loop" section into one
  command. A build that would reproduce the image already on the artifact is
  skipped automatically; force it with `--force-build`.
- **Sizing-only changes (replica count, resource allocation) apply in place**
  — no build, no new artifact version — because what the workload runs hasn't
  changed. This is the CLI equivalent of `PATCH /workloads/{id}/settings/`
  (SKILL.md section 1) for anyone working from a manifest instead of raw JSON.
  A change that touches both sizing and image ships the sizing with the
  rollout.
- **Deploying onto an existing workload rolls it** — zero-downtime, same
  semantics as the manual `PATCH /settings/`/`POST /replacement/` paths in
  `lifecycle-flows.md`. Rolling a **locked** version prompts for the workload
  name to be typed back (interactive) or is refused without `--yes`.
- **Only fields the manifest names are managed.** A setting the file never
  mentions survives every deploy untouched; deleting a line from the manifest
  stops managing that field rather than reverting a live change. If the
  platform/UI changes a field the manifest *does* name, the next `up` reverts
  it and says so — surface this to the user before running `up` on a manifest
  someone else may have hand-edited outside it.
- `--dry-run` prints the plan (create/build/deploy/resize) without applying
  it — the answer to "what would this deploy do," including in CI.
- `--lock` locks whichever artifact ends up live (one-way) even on a deploy
  that minted no new version.
- `--detach` returns once the deploy is requested instead of waiting for it
  to serve.

## When to still use the manual/raw-REST flows instead

- **`up`/`config` return `unknown command`** — by far the most common reason;
  don't assume they're present just because the CLI is installed and current.
- You need explicit `warmupDurationMinutes`/`keepOldVersionMinutes` control on
  a replacement — `up` doesn't expose `ReplacementConfig`; use
  `POST /workloads/{id}/replacement/` directly (`lifecycle-flows.md`).
- You need to inspect or script against intermediate artifact/build state
  directly (build logs mid-build, multiple candidate artifacts, etc.) — use
  the granular `dr artifact`/`dr workload` subcommands or raw REST.
- CI/automation that shouldn't depend on a committed YAML file's drift
  semantics ("only fields the manifest names are managed" can surprise a
  fully-declarative pipeline) — raw REST or the granular CLI calls give
  explicit, one-shot control instead.
- The user is doing something `--build-mode`/`--type` doesn't model yet
  (e.g. multi-container groups) — fall back to a hand-written artifact spec.

## `dr workload config` flags worth knowing

`--build-mode {dockerfile|generated|image}` picks the image source
(`dockerfile` needs `./Dockerfile`; `generated` needs
`--execution-environment` + `--entrypoint`, same idea as C2W's
`imageBuildConfig.dockerfile` in `code-to-workload.md`; `image` needs
`--image`). `--type {service|agent}`; `--a2a-enabled` publishes an agent's A2A
card to the tenant-wide registry (agent type only). `--skip-env` omits the
project's `.env` from the manifest (by default its vars are written in —
plain values as literals, anything that looks like a secret as a credential
reference to complete later, mirroring SKILL.md's "Credential injection"
guidance). `--workload-id <id>` binds to and downloads the spec of an
*existing* workload instead of naming a new one (exclusive with `--name`) —
use this to start managing an already-running workload declaratively without
risking a silent downgrade of something live.
