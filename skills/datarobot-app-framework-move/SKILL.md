---
name: datarobot-app-framework-move
description: Use when the user wants to move or redeploy a DataRobot Custom Application to another DataRobot install, let several engineers deploy one app to one install, keep Pulumi state durable between machines or Codespaces, or deploy to an install with no internet access. Covers `dr-sync run` with Pulumi, laptop and Codespace runners, offline delivery of tools and Python packages, and recovery after a failed or interrupted deploy.
---

# Move a Custom Application between installs

A move is a redeploy. Deploy the same repository to the target install with that install's settings. Never copy running objects, state or a stack from one install to another, because IDs, credentials and environments differ per install. Look up what the app depends on by name on the target.

Pulumi keeps its local `file://` backend. `dr-sync run` keeps that directory durable in a Files container on the install: it takes a lease, pulls the state, runs the command, pushes the state back and releases the lease. The full steps are in the [move guide](https://github.com/datarobot-labs/datarobot-sync/blob/main/docs/content/docs/move-an-app.md). Follow the guide for commands. This skill covers the decisions.

## Before you start

Ask the user for:

- The target install's API endpoint and an API key. Never print the key or write it to a file.
- The stack passphrase. Never commit it.
- Whether the user's laptop reaches the target API, and whether the install reaches the internet.

The plugin is `dr-sync` (the `dr` plugin `sync`) v0.3.1 or later. Earlier versions lose the push when `dr` cancels a run on Ctrl-C.

## Decide where to run

| The laptop reaches the target API | Run from |
| --- | --- |
| Yes, for example over VPN | The laptop, with `datarobot sync` or `dr-sync` |
| No, only a browser does | A Codespace in the target install, with the standalone `dr-sync` and `DR_SYNC_NO_PRESIGN=1` |

Prefer the standalone `dr-sync` for deploys. Through `dr`, a plugin is killed 5 seconds after Ctrl-C, so a push can be cut short.

## Deploy

1. Create the state container once per install with `dr-sync init --name "<app>-state"`. Save the container ID in `installs/<install>.env` in the repository and commit it. Share the Files item with each teammate as an Editor.
2. Use one stack per install, named after the install. Keep its settings in `Pulumi.<install>.yaml` and commit the file, again after the first deploy, because Pulumi adds the `encryptionsalt` line then.
3. Keep `stack init` for the first deploy and `stack select` for every later one, as two separate commands. Do not use `select --create`: with a wrong container ID it deploys a duplicate app instead of failing.
4. Run every deploy through `dr-sync run "$STATE_DIR" --exclude-from pulumi.drsyncignore -- sh -c '... && exec pulumi up --yes'`. Keep `exec`, so SIGTERM reaches Pulumi.

If `stack select` reports `no stack named`, stop. The container ID is wrong or new, and a deploy now starts from empty state and creates a duplicate app.

## After a failure

Read the exit code and the last message before you rerun anything.

| Result | Meaning | Do |
| --- | --- | --- |
| Exit 4, `holds this container` | Another run, or a killed one, holds the lease. Nothing ran | Wait for the lease to expire (30 minutes at most). Use `--force` only after you confirm nobody else is deploying |
| Exit 4, `container advanced` or `another writer claimed` | Pulumi ran, and a teammate pushed first. The result is only on this machine | Do not rerun. Keep `.dr-sync-backup/` and ask for help |
| Exit 7 | Pulumi failed. The state is pushed | Fix the error and run again |
| Exit 6 | The pull did not finish. Nothing ran | Run again |
| Exit 130 or 255 | Interrupted | Rerun only after the output says `the tree was pushed as it stood`. Otherwise keep `.dr-sync-backup/` and ask for help |

A warning that names `.dr-sync-backup/` means local state differed from the head. If the last run on this machine did not push, that folder can hold the only record of resources Pulumi created. Keep it, and do not deploy again until someone merges it back.

An `Application name must be unique` error after a killed deploy means the app exists but the state does not know it. `pulumi refresh` does not find it. Do not retry, because each retry leaves one more app. Delete the clashing apps, then deploy.

## Install with no internet

A Codespace there reaches only the install's own API. Deliver three files through one Files item: the `dr-sync` Linux archive, the Pulumi provider tarball (its version must match `pip show pulumi-datarobot`) and a `git bundle` of the repository. The app build runs `pip install` and fails without a package index. Vendor the wheels into the app source with `pip install --target` and put them on `PYTHONPATH` in `start-app.sh`. Delete `requirements.txt`, because it wins over everything else. The guide has the exact commands.

## Limits

- Workloads: deploy with `dr workload up` from a laptop that reaches the install. From a Codespace, `/api/v2/workloads` often fails. Use one checkout per install, because `up` writes the `workloadId` into `.datarobot.yaml`.
- `dr-sync` is a field tool, not a state service. When the install reaches an S3 or Azure Blob bucket, use Pulumi's own backend instead.
- Not tested: an install behind an HTTP proxy, a Files upload through the UI, Windows with Pulumi, and a Workload endpoint override.

## Related skills

- `datarobot-app-framework-cicd` for unattended pipelines.
- `datarobot-workload-api` for the Workload lifecycle and diagnosis.
