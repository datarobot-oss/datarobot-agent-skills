---
name: datarobot-app-framework-cicd
description: Guidance for setting up CI/CD pipelines for DataRobot application templates using GitLab, GitHub Actions, and Pulumi for infrastructure as code. Use when setting up CI/CD pipelines, configuring deployments, or managing infrastructure for DataRobot application templates.
context-tokens: "~6 000 (SKILL.md) + ~2 000 (scripts/*) + ~400 per examples/* file"
---

# DataRobot Application Templates CI/CD Skill

This skill provides comprehensive guidance for setting up production-grade CI/CD pipelines for DataRobot application templates, including automated testing, review deployments, and continuous delivery.

## Quick Start

**Default behavior:** When a user asks to "set up CI/CD" without specifying a platform or backend, always use the [Simple Path](#simple-path-pulumi-cloud--github-secrets) below — three workflow files, two GitHub Secrets, done. Do not create `infra/scripts/`, do not add CI/CD tasks to `infra/Taskfile.yaml`, do not involve GPG encryption unless the user explicitly asks for it.

Only deviate from the simple path when the user specifies:
- A specific Pulumi state backend (Azure Blob, S3, GCS) → use `scripts/` and see [Implementation Pattern](#implementation-pattern)
- GitLab CI/CD → see [GitLab CI/CD Configuration](#gitlab-cicd-configuration)
- Many secrets to manage → consider GPG approach in `scripts/`

## Simple Path: Pulumi Cloud + GitHub Secrets

For most data scientists and AI engineers, this is all you need. No GPG encryption, no cloud storage account, no extra scripts.

**What to create in the user's repository:**

1. Copy the three workflow files to `.github/workflows/`:

   | Source | Destination | Trigger |
   |--------|-------------|---------|
   | `examples/github-cd-pulumi-cloud.yml` | `.github/workflows/cd.yml` | Automatic — every merge to `main` |
   | `examples/github-deploy-pulumi-cloud.yml` | `.github/workflows/deploy-pr.yml` | Manual — user picks PR branch + enters stack name (e.g. `pr-42`) |
   | `examples/github-destroy-pulumi-cloud.yml` | `.github/workflows/destroy.yml` | Manual — user enters stack name to tear down |

2. Create `.github/workflows/README.md` from `examples/workflows-README.md`. This is the setup guide that tells the user exactly what secrets and variables to add and how.

3. Tell the user to follow the setup guide in `.github/workflows/README.md`.

That's it. Do **not** add anything to `infra/Taskfile.yaml` or create `infra/scripts/` for this path.

**Required GitHub Secrets** (both required — no defaults):

| Name | Kind |
|------|------|
| `DATAROBOT_API_TOKEN` | Secret |
| `PULUMI_ACCESS_TOKEN` | Secret |

**Optional GitHub Variables** (defaults apply if not set):

| Name | Kind | Default |
|------|------|---------|
| `PULUMI_STACK_CI_NAME` | Variable | `ci` |
| `DATAROBOT_ENDPOINT` | Variable | `https://app.datarobot.com/api/v2` |

Set `DATAROBOT_ENDPOINT` only for EU (e.g. `https://app.eu.datarobot.com/api/v2`) or on-prem/self-managed DataRobot installs.

**When to use the advanced approach (GPG + DIY backends) instead:**
- You have many secrets (GPG encrypts all of `.env` behind a single passphrase — only one GitHub Secret needed)
- Your organization prohibits Pulumi Cloud and requires a self-managed backend (Azure Blob / S3 / GCS)
- You need GitLab CI/CD

The templates and scripts for all of these are in `scripts/` in this skill directory. If the skill has already been propagated to the project's `infra/` directory (common in downstream templates), look in `infra/scripts/` instead. See the [Implementation Pattern](#implementation-pattern) section below for full setup guidance.

| Scenario | Key files in `scripts/` |
|----------|------------------------|
| Azure Blob / S3 / GCS Pulumi backend | `pulumi-setup.sh`, `taskfile-snippets.yaml` |
| GitHub Actions + GPG secrets | `github-deploy.yml`, `github-cd.yml`, `encrypt-secrets.sh`, `setup-github-secrets.sh` |
| GitLab CI/CD | `gitlab-ci.yml`, `setup-gitlab-variables.sh` |

### Adapting the deploy command

The example workflows use `uv run pulumi up --yes` directly. Before copying them, check `infra/Taskfile.yaml` — the project may already wrap the deploy command in a task:

```bash
cat infra/Taskfile.yaml   # look for 'up-yes', 'deploy', or similar tasks
```

| What you find | What to use in CI |
|---------------|-------------------|
| `up-yes` task | `task up-yes` — non-interactive, purpose-built for CI; prefer this over raw Pulumi |
| `deploy` task (alias for `up`) | Avoid — typically runs `pulumi up` interactively; only safe in CI if you confirm it passes `-y` internally |
| No Taskfile or no relevant task | Keep `uv run pulumi up --yes` as-is |

To use `task` in a workflow, add an install step and swap the run command:

```yaml
- name: Install Task
  run: pip install go-task-bin

- name: Deploy
  working-directory: infra
  env:
    DATAROBOT_API_TOKEN: ${{ secrets.DATAROBOT_API_TOKEN }}
    PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
  run: |
    uv sync --all-extras
    task up-yes
```

### DataRobot API token (service account)

`DATAROBOT_API_TOKEN` should come from a **DataRobot service account** — a DataRobot user created for automation, not tied to anyone's personal login. This prevents CI/CD from breaking when the engineer who originally set it up leaves the team.

To set one up: ask your DataRobot admin to create a dedicated user (e.g. `ci-bot@your-org.com`). Under that account, go to **Developer Tools → API Key** and generate a token. Store it as the `DATAROBOT_API_TOKEN` secret in GitHub.

> **Note:** This is purely a DataRobot concept — it has no relation to Pulumi state management or backend configuration. "Service account" here just means a non-personal DataRobot user.

## Implementation Pattern

When implementing CI/CD for an application template, follow this structure:

**Project Structure:**
```
application-template-root/
├── infra/
│   ├── README.md                   # ⚠️ GENERATE THIS — tailored to the chosen CI/CD platform and Pulumi backend
│   ├── Taskfile.yaml               # ⚠️ CI/CD tasks go HERE — copy from infra/scripts/taskfile-snippets.yaml
│   └── scripts/                    # Copy entire scripts/ directory here
│       ├── README.md               # Copy from scripts/infra-README.md
│       ├── setup-github-secrets.sh
│       ├── setup-gitlab-variables.sh
│       ├── encrypt-secrets.sh
│       ├── decrypt-secrets.sh
│       ├── pulumi-setup.sh
│       ├── gitlab-ci.yml
│       ├── github-deploy.yml
│       ├── github-cd.yml
│       ├── github-destroy.yml
│       └── taskfile-snippets.yaml
├── .env                            # User's secrets (never commit!)
├── .env.gpg                        # Encrypted secrets (commit for GitHub)
├── .gitlab-ci.yml                  # Copy from infra/scripts/gitlab-ci.yml
├── .github/
│   └── workflows/
│       ├── deploy.yml              # Copy from infra/scripts/github-deploy.yml (PR review deploys)
│       ├── cd.yml                  # Copy from infra/scripts/github-cd.yml (push-to-main CD)
│       └── destroy.yml             # Copy from infra/scripts/github-destroy.yml
└── Taskfile.yml                    # Root Taskfile — ADD ONLY one `includes` entry (see below). DO NOT add tasks here.
```

**Key Points:**
- **⚠️ ALWAYS generate `infra/README.md`** tailored to the chosen platform and backend — see "Generating infra/README.md" below
- All CI/CD scripts go in `infra/scripts/` directory
- **⚠️ CRITICAL: All CI/CD tasks go in `infra/Taskfile.yaml` — NEVER add CI/CD tasks directly to the root `Taskfile.yml`**
- `.env` and `.env.gpg` stay in project root
- Scripts in `infra/scripts/` reference `../../.env` (two levels up)
- Root `Taskfile.yml` gets exactly ONE addition: an `includes` entry pointing to `./infra/Taskfile.yaml`
- CI/CD configs (`.gitlab-ci.yml`, `.github/workflows/`) are copied to standard locations

**Root Taskfile.yml — the only change needed:**
```yaml
# Add this includes block to the existing root Taskfile.yml:
includes:
  infra:
    taskfile: ./infra/Taskfile.yaml
    dir: infra
# Tasks are then run as: task infra:encrypt-secrets, task infra:setup-github-secrets, etc.
```

### Generating infra/README.md

After determining the user's CI/CD platform (GitHub/GitLab) and Pulumi backend, **always create `infra/README.md`** with content tailored to their choices. It should cover:

1. **Architecture overview** — which platform was chosen and why, and which Pulumi backend
2. **First-time setup** — the exact sequence of `task infra:*` commands needed to bootstrap
3. **Day-to-day tasks** — a table or list of the `task infra:*` commands relevant to their platform
4. **How deployments work** — short description of each trigger:
   - GitHub: `deploy.yml` fires on PR open/sync (review stack), `cd.yml` fires on push to main (CI stack), `destroy.yml` is manual
   - GitLab: `review_app` is manual on MR, `deploy_ci` fires on push to default branch, `destroy_review_app` is manual
5. **Secrets / credentials** — what variables/secrets are needed and where they live (GitHub Secrets, GitLab CI/CD variables, `.env.gpg`)
6. **Stack migration note** — if backend was migrated from a local stack, document what was done so future contributors understand the history

Adjust section titles, task names, and stack-naming strategy to match what was actually configured. The README should be accurate enough that a new contributor can set up CI/CD without referring to any other document.

## Workflow examples

See [`references/workflow-examples.md`](references/workflow-examples.md) for step-by-step examples covering GitLab CI/CD, GitHub Actions with GPG secrets, and continuous delivery setup.

## Using Task for workflow management

Application templates use [Task](https://taskfile.dev) to simplify local development and CI/CD workflows. Task provides a unified interface for Python and TypeScript/React components.

### Example Taskfile.yaml

See [`references/example-taskfile.yaml`](references/example-taskfile.yaml) for a complete example.

### Using Task in CI/CD

```bash
# Install Task
pip install go-task-bin

# Install dependencies
task install

# Run linters (with fixes)
task lint

# Run linters (check only)
task lint-check

# Run tests
task test
```

## GitLab CI/CD Configuration

The complete pipeline configuration lives in `scripts/gitlab-ci.yml`. Copy it to your repository root:

```bash
cp infra/scripts/gitlab-ci.yml .gitlab-ci.yml
```

Key pipeline jobs:
- `lint` / `test` — run on every same-project MR
- `review_app` — manual deploy per MR; stack name driven by the `PULUMI_STACK_REVIEW_NAME` CI/CD variable
- `deploy_ci` — automatic deploy on merge to default branch; stack name driven by `PULUMI_STACK_CI_NAME`
- `destroy_review_app` — manual cleanup of review stacks

`PULUMI_STACK_REVIEW_NAME` and `PULUMI_STACK_CI_NAME` must be set as plain CI/CD variables in GitLab (Settings → CI/CD → Variables). The pipeline file includes sensible defaults that project-level variables override.

## GitHub Actions Configuration

The complete workflow files live in `scripts/`:

- `scripts/github-deploy.yml` → copy to `.github/workflows/deploy.yml`
- `scripts/github-destroy.yml` → copy to `.github/workflows/destroy.yml`

```bash
mkdir -p .github/workflows
cp infra/scripts/github-deploy.yml .github/workflows/deploy.yml
cp infra/scripts/github-destroy.yml .github/workflows/destroy.yml
```

The deploy workflow triggers on pull requests and derives `PULUMI_STACK_NAME` from the `PULUMI_STACK_REVIEW_NAME` Actions variable and the PR number. Set `PULUMI_STACK_REVIEW_NAME` and `PULUMI_STACK_CI_NAME` as repository **variables** (Settings → Secrets and variables → Actions → **Variables** tab), not secrets.

## Pulumi State Management

### Pulumi Cloud Backend (Recommended)

The simplest approach for managing Pulumi state:

```bash
# Install Pulumi
curl -fsSL https://get.pulumi.com | sh

# Login to Pulumi Cloud
pulumi login

# Create/select stack
pulumi stack select --create dev

# Deploy
pulumi up
```

**CI/CD Setup**: Add `PULUMI_ACCESS_TOKEN` to your CI/CD secrets. Get token from [Pulumi Console](https://app.pulumi.com/account/tokens).

### DIY Backend Options

For organizations that cannot use Pulumi Cloud:

#### Azure Blob Storage

```bash
# Login to Azure backend
pulumi login azblob://container-name

# Set Azure credentials
export AZURE_STORAGE_ACCOUNT=myaccount
export AZURE_STORAGE_KEY=mykey
```

#### AWS S3

```bash
# Login to S3 backend
pulumi login s3://bucket-name

# AWS credentials from environment
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
```

#### Google Cloud Storage

```bash
# Login to GCS backend
pulumi login gs://bucket-name

# GCP credentials from environment
export GOOGLE_CREDENTIALS=...
```

### Migrating Stacks to a Different Backend

When a developer has an existing local stack (a `Pulumi.<stackname>.yaml` file) that was
created against a different backend than the CI/CD destination, the stack state must be
exported and re-imported before switching.

`pulumi-setup.sh` handles this automatically: it checks `pulumi whoami --verbose` for the
**Backend URL** and compares it with the target URL. If they differ and local stack files
exist, it offers to migrate them.

**Manual migration steps** (if not using the script):

```bash
# 1. Confirm current backend and stacks
pulumi whoami --verbose        # note "Backend URL:"
pulumi stack ls -a             # list stacks on current backend

# 2. Export each stack that exists locally (Pulumi.<name>.yaml)
pulumi stack export --stack <stackname> --file <stackname>-backup.json

# 3. Login to the new backend (set any required credentials first)
#    Examples:
pulumi login                           # Pulumi Cloud
pulumi login azblob://my-container     # Azure Blob
pulumi login s3://my-bucket            # AWS S3

# 4. Create the stack in the new backend and import state
pulumi stack select --create <stackname>
pulumi stack import --file <stackname>-backup.json

# 5. Clean up the backup
rm <stackname>-backup.json
```

**Key signals that migration is needed:**
- `pulumi whoami --verbose` shows `Backend URL: file://` (local) but CI/CD uses cloud storage
- Backend URL domain/scheme differs between developer machine and CI target

### Managing Stacks Across Environments

```bash
# List all stacks
pulumi stack ls -a

# Output:
# NAME                                 LAST UPDATE   RESOURCE COUNT
# organization/project/prod            1 day ago     15
# organization/project/staging         2 days ago    12
# organization/project/dev             1 hour ago    10
# github-pr-repo-42                    3 hours ago   13

# Select and update a stack
pulumi stack select dev
pulumi up

# View stack outputs
pulumi stack output --json

# Delete a stack
pulumi stack rm review-app-123 --yes
```

## Secrets Management

All credentials (DataRobot API token, Pulumi access token, LLM keys, cloud storage keys) are stored in `.env` and committed to the repository encrypted as `.env.gpg`. The only secret that needs to be configured in the CI/CD system directly is `CICD_SECRET_PASSPHRASE` (the GPG passphrase). Non-sensitive stack name variables (`PULUMI_STACK_CI_NAME`, `PULUMI_STACK_REVIEW_NAME`) are set as plain variables, not secrets.

### DataRobot API token (service account)

`DATAROBOT_API_TOKEN` should come from a **DataRobot service account** — a DataRobot user created for automation, not tied to anyone's personal login. This prevents CI/CD from breaking when the engineer who originally set it up leaves the team.

To set one up: ask your DataRobot admin to create a dedicated user (e.g. `ci-bot@your-org.com`). Under that account, go to **Developer Tools → API Key** and generate a token. Store it as the `DATAROBOT_API_TOKEN` secret in your CI/CD system.

> **Note:** This is purely a DataRobot concept — it has no relation to Pulumi state management or backend configuration. "Service account" here just means a non-personal DataRobot user.

### GitHub

Run `scripts/setup-github-secrets.sh` for interactive setup — it sets `CICD_SECRET_PASSPHRASE` as a repository secret and `PULUMI_STACK_CI_NAME` / `PULUMI_STACK_REVIEW_NAME` as repository variables.

To encrypt `.env` for CI:

```bash
task infra:encrypt-secrets
# or: ./infra/scripts/encrypt-secrets.sh
```

Add the resulting `.env.gpg` to git. For local decryption:

```bash
task infra:decrypt-secrets
# or: ./infra/scripts/decrypt-secrets.sh
```

### GitLab

Run `scripts/setup-gitlab-variables.sh` for interactive setup — it sets:
- `CICD_SECRET_PASSPHRASE` — masked, for decrypting `.env.gpg`
- `GITLAB_API_TOKEN` — masked, for posting MR comments
- `PULUMI_STACK_CI_NAME` / `PULUMI_STACK_REVIEW_NAME` — plain variables

Alternatively configure in the UI: Project Settings → CI/CD → Variables. Mark `CICD_SECRET_PASSPHRASE` and `GITLAB_API_TOKEN` as **Masked** and **Protected**.

## Best practices

### CI/CD Pipeline Design

1. **Fast feedback**: Run linting and testing in parallel
2. **Manual gates**: Make review apps manual to save resources
3. **Automatic cleanup**: Provide easy ways to destroy test environments
4. **Stack isolation**: Use unique stack names per PR/MR
5. **Idempotent operations**: Design deployments to be safely re-runnable

### Pulumi State

1. **Use centralized backends**: Enable collaboration and CI/CD
2. **Stack naming conventions**: Use consistent patterns (e.g., `github-pr-{repo}-{number}`)
3. **Clean up stacks**: Remove unused stacks to reduce clutter
4. **State locking**: Backends handle this automatically
5. **Backup state**: Cloud backends provide automatic backups

### Security

1. **Never commit secrets**: Use .gitignore for .env files
2. **Encrypt sensitive data**: Use GPG for GitHub, CI/CD variables for GitLab
3. **Rotate credentials**: Regularly update API tokens and keys
4. **Scope permissions**: Use least-privilege access for service accounts
5. **Audit access**: Monitor who has access to secrets

### Resource Management

1. **Tag resources**: Use consistent tagging for tracking
2. **Set TTLs**: Consider time-to-live for review environments
3. **Monitor costs**: Track resource usage per environment
4. **Auto-cleanup**: Implement automatic deletion of old review apps
5. **Resource limits**: Set quotas to prevent runaway costs

## Troubleshooting

### Common Issues

**Pulumi state conflicts:**
- Ensure only one deployment runs at a time per stack
- Use unique stack names for concurrent deployments
- Check backend connection and credentials

**Secret decryption failures:**
- Verify GPG passphrase is correct
- Check .env.gpg file is in repository
- Ensure GPG is installed in CI environment

**Deployment timeouts:**
- Increase timeout values in workflow
- Check DataRobot API connectivity
- Verify resource provisioning isn't blocked

**Stack not found:**
- List stacks: `pulumi stack ls -a`
- Verify backend connection
- Check stack name matches pattern

**Resource conflicts:**
- Use unique names per stack
- Check for orphaned resources
- Review Pulumi state for inconsistencies

## Example Repositories

Reference implementations:

- **GitLab**: [demo-data-agent](https://gitlab.com/datarobot-oss/demo-data-agent) - Complete GitLab CI/CD setup
- **GitHub**: [demo-talk-to-my-data-agent](https://github.com/datarobot-forks/demo-talk-to-my-data-agent) - Complete GitHub Actions setup

## Resources

- [Task Documentation](https://taskfile.dev)
- [Pulumi Documentation](https://www.pulumi.com/docs/)
- [Pulumi State and Backends](https://www.pulumi.com/docs/iac/concepts/state-and-backends/)
- [GitLab CI/CD](https://docs.gitlab.com/ci/)
- [GitHub Actions](https://docs.github.com/actions)
- [DataRobot Application Templates](https://docs.datarobot.com/en/docs/wb-apps/app-templates/index.html)
- [DataRobot Codespaces](https://docs.datarobot.com/en/docs/workbench/wb-notebook/codespaces/index.html)
