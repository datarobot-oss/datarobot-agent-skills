---
name: datarobot-app-framework-cicd
description: Guidance for setting up CI/CD pipelines for DataRobot application templates using GitLab, GitHub Actions, and Pulumi for infrastructure as code.
---

# DataRobot Application Templates CI/CD Skill

This skill provides comprehensive guidance for setting up production-grade CI/CD pipelines for DataRobot application templates, including automated testing, review deployments, and continuous delivery.

## Quick Start

**Most common use case**: Set up CI/CD for an application template

1. **Choose platform**: GitLab CI/CD or GitHub Actions
2. **Configure secrets**: Set up DataRobot API tokens, LLM keys, and Pulumi credentials
3. **Add pipeline config**: Create `.gitlab-ci.yml` or `.github/workflows/*.yml`
4. **Set up Pulumi**: Configure state backend for infrastructure tracking
5. **Enable review apps**: Add manual deployment jobs for PR/MR validation

**Example**: "Set up GitHub Actions CI/CD for my Talk to My Data Agent application template with review deployments and continuous delivery"

## When to use this skill

Use this skill when you need to:
- Set up automated testing and linting for DataRobot application templates
- Configure CI/CD pipelines for GitLab or GitHub
- Implement review app deployments for pull/merge requests
- Set up continuous delivery to automatically deploy merged changes
- Manage Pulumi state across environments
- Securely handle secrets and credentials in CI/CD
- Automate infrastructure provisioning with Pulumi
- Create DevOps workflows for AI applications

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
│       ├── secrets.sh
│       ├── setup-github-cicd.sh
│       ├── setup-gitlab-variables.sh
│       ├── pulumi-setup.sh
│       ├── github-actions/         # composite action — copy to .github/actions/
│       │   └── decrypt-secrets/
│       │       └── action.yml
│       ├── gitlab-ci.yml           # ⚠️ TEMPORARY — delete after copying to .gitlab-ci.yml
│       ├── github-deploy.yml       # ⚠️ TEMPORARY — delete after copying to .github/workflows/deploy.yml
│       ├── github-cd.yml           # ⚠️ TEMPORARY — delete after copying to .github/workflows/cd.yml
│       ├── github-destroy.yml      # ⚠️ TEMPORARY — delete after copying to .github/workflows/destroy.yml
│       └── taskfile-snippets.yaml  # ⚠️ TEMPORARY — delete after copying to infra/Taskfile.yaml
├── .env                            # User's secrets (never commit!)
├── .env.gpg                        # Encrypted secrets (commit for GitHub)
├── .gitlab-ci.yml                  # Copy from infra/scripts/gitlab-ci.yml
├── .github/
│   ├── actions/
│   │   └── decrypt-secrets/        # Copy from infra/scripts/github-actions/decrypt-secrets/
│   │       └── action.yml
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

**Example outline** (tailor section titles and commands to the actual platform):

```markdown
# Infrastructure & CI/CD

## Architecture
This project uses **GitHub Actions** for CI/CD and **Azure Blob Storage** as the Pulumi state backend.

| Component | Technology |
|-----------|------------|
| CI/CD platform | GitHub Actions |
| Infrastructure as code | Pulumi (Python) |
| State backend | Azure Blob — `azblob://dr-ai-apps-pulumi` |
| Secrets | GPG-encrypted `.env.gpg` + GitHub Secrets |

## First-time setup
```bash
# 1. Encrypt your .env for CI
task infra:encrypt-secrets

# 2. Push GitHub secrets
task infra:setup-github-secrets

# 3. Initialise Pulumi (sets backend + creates dev stack)
task infra:pulumi-login-azure
```

## Available tasks
| Task | Description |
|------|-------------|
| `task infra:encrypt-secrets` | GPG-encrypt `.env` → `.env.gpg` |
| `task infra:decrypt-secrets` | Decrypt `.env.gpg` → `.env` locally |
| `task infra:setup-github-secrets` | Push secrets to GitHub via `gh` CLI |
| `task infra:pulumi-login-azure` | Log Pulumi in to the Azure backend |
| `task infra:pulumi-deploy` | Deploy the current stack |
| `task infra:pulumi-destroy` | Destroy the current stack |

## How CI/CD deployments work
- **Pull requests** — `deploy.yml` runs tests, then deploys a review stack named `github-pr-<repo>-<number>`
- **Merge to main** — same workflow re-runs and updates the `ci` stack
- **Cleanup** — `destroy.yml` (manual trigger) tears down a named stack

## Required secrets
| Secret | Description |
|--------|-------------|
| `CICD_SECRET_PASSPHRASE` | GPG passphrase for `.env.gpg` |
| `PULUMI_ACCESS_TOKEN` | *(omit if using DIY backend)* |
| `AZURE_STORAGE_ACCOUNT` | Azure storage account for Pulumi state |
| `AZURE_STORAGE_KEY` | Azure storage key for Pulumi state |
| `DATAROBOT_API_TOKEN` | DataRobot API token |
```

Adjust the table rows, task names, and stack-naming strategy to match what was actually configured. The README should be accurate enough that a new contributor can set up CI/CD without referring to any other document.

## Workflow examples

### Example 1: Set up GitLab CI/CD with review apps

**User request**: "Set up GitLab CI/CD for my application template with automated testing and manual review deployments"

**Agent workflow**:
1. Create `infra/scripts/` directory in project root: `mkdir -p infra`
2. Copy entire scripts directory: `cp -R <skill-path>/scripts infra/scripts`
3. Make scripts executable: `chmod +x infra/scripts/*.sh`
4. Copy CI/CD configs to standard locations:
   - GitLab: `cp infra/scripts/gitlab-ci.yml .gitlab-ci.yml`
   - GitHub workflows: `cp infra/scripts/github-*.yml .github/workflows/`
   - GitHub composite action: `mkdir -p .github/actions/decrypt-secrets && cp infra/scripts/github-actions/decrypt-secrets/action.yml .github/actions/decrypt-secrets/`
5. Copy tasks from `infra/scripts/taskfile-snippets.yaml` to `infra/Taskfile.yaml`
   Then add an `includes` entry to the root `Taskfile.yml` pointing to `./infra/Taskfile.yaml` — **do NOT paste tasks directly into root Taskfile.yml**
6. **⚠️ CLEAN UP snippet files** — remove the originals now that they've been copied to their final destinations:
   ```bash
   rm infra/scripts/gitlab-ci.yml
   rm infra/scripts/github-cd.yml infra/scripts/github-deploy.yml infra/scripts/github-destroy.yml
   rm infra/scripts/taskfile-snippets.yaml
   ```
7. Guide user to run `task infra:setup-github-cicd` or `task infra:setup-gitlab-vars`
8. If GitHub, guide user to run `task encrypt-secrets` to encrypt `.env` file
9. **Generate `infra/README.md`** tailored to GitLab + chosen Pulumi backend (see "Generating infra/README.md" above)
10. Test pipeline with a sample PR/MR

### Example 2: Set up GitHub Actions with encrypted secrets

**User request**: "Configure GitHub Actions CI/CD with GPG-encrypted secrets and review deployments"

**Agent workflow**:
1. Create `infra/scripts/` directory: `mkdir -p infra && cp -R <skill-path>/scripts infra/scripts`
2. Make scripts executable: `chmod +x infra/scripts/*.sh`
3. Copy GitHub workflows: `cp infra/scripts/github-*.yml .github/workflows/`
4. Copy composite action: `mkdir -p .github/actions/decrypt-secrets && cp infra/scripts/github-actions/decrypt-secrets/action.yml .github/actions/decrypt-secrets/`
5. Copy `infra/scripts/taskfile-snippets.yaml` to `infra/Taskfile.yaml`: `cp infra/scripts/taskfile-snippets.yaml infra/Taskfile.yaml`
   Add an `includes` entry for `./infra/Taskfile.yaml` to the root `Taskfile.yml` — **do NOT paste tasks directly into root Taskfile.yml**
5. **⚠️ CLEAN UP snippet files** — remove the originals now that they've been copied to their final destinations:
   ```bash
   rm infra/scripts/github-cd.yml infra/scripts/github-deploy.yml infra/scripts/github-destroy.yml
   rm infra/scripts/gitlab-ci.yml
   rm infra/scripts/taskfile-snippets.yaml
   ```
6. Guide user to encrypt `.env` with `task infra:encrypt-secrets`
7. Guide user to set up GitHub secrets with `task infra:setup-github-cicd`
8. Add encrypted `.env.gpg` to repository
9. **Generate `infra/README.md`** tailored to GitHub Actions + chosen Pulumi backend (see "Generating infra/README.md" above)
10. Test workflow with a sample pull request

### Example 3: Configure continuous delivery

**User request**: "Set up automatic deployment when changes are merged to main branch"

**Agent workflow**:
1. Add deployment job triggered on push to main branch
2. Configure Pulumi to use persistent stack name (e.g., "ci" or "prod")
3. Set up automatic stack selection and update
4. Configure deployment to run only on successful tests
5. Add deployment status notifications
6. Document the CD process for the team

## Using Task for workflow management

Application templates use [Task](https://taskfile.dev) to simplify local development and CI/CD workflows. Task provides a unified interface for Python and TypeScript/React components.

### Example Taskfile.yaml

```yaml
version: '3'
dotenv:
  - .env
includes:
  react:
    taskfile: ./frontend_react/react_src/Taskfile.yaml
    dir: ./frontend_react/react_src/
tasks:
  install:
    desc: 📦 Install all dependencies
    cmds:
      - uv venv .venv
      - source .venv/bin/activate && uv pip install -r requirements.txt
      - task: react:install

  python-lint:
    desc: 🧹 Lint Python code
    cmds:
      - ruff format .
      - ruff check . --fix
      - mypy --pretty .

  python-lint-check:
    desc: 🧹 Check Python linting without fixes
    cmds:
      - ruff format --check .
      - ruff check .
      - mypy --pretty .

  lint:
    deps:
      - react:lint
      - python-lint
    desc: 🧹 Lint all code

  lint-check:
    deps:
      - react:lint-check
      - python-lint-check
    desc: 🧹 Check linting for all code

  test:
    deps:
      - react:test
    desc: 🧪 Run all tests
```

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

## Helper Scripts and Configuration

When implementing CI/CD for an application template, create an `infra/` directory in the project root to house all CI/CD and infrastructure-related files:

**Directory Structure:**
```
project-root/
├── infra/
│   ├── Taskfile.yaml       # ⚠️ CI/CD tasks go HERE — copy from infra/scripts/taskfile-snippets.yaml
│   └── scripts/
│       ├── setup-github-secrets.sh
│       ├── setup-gitlab-variables.sh
│       ├── encrypt-secrets.sh
│       ├── decrypt-secrets.sh
│       ├── pulumi-setup.sh
│       ├── gitlab-ci.yml
│       ├── github-deploy.yml
│       ├── github-destroy.yml
│       ├── taskfile-snippets.yaml
│       └── README.md
├── .gitlab-ci.yml          # Copied from infra/scripts/
├── .github/
│   └── workflows/
│       ├── deploy.yml       # Copied from infra/scripts/
│       └── destroy.yml      # Copied from infra/scripts/
└── Taskfile.yml            # Root Taskfile — ADD ONLY an includes entry for infra/Taskfile.yaml. DO NOT add tasks here.
```

**Script reference:**

| Script | Purpose |
|--------|--------|
| `gitlab-ci.yml` | Complete GitLab CI/CD pipeline — copy to `.gitlab-ci.yml` |
| `github-cd.yml` | GitHub Actions CD workflow — copy to `.github/workflows/cd.yml` |
| `github-deploy.yml` | GitHub Actions deploy workflow — copy to `.github/workflows/deploy.yml` |
| `github-destroy.yml` | GitHub Actions destroy workflow — copy to `.github/workflows/destroy.yml` |
| `github-actions/decrypt-secrets/action.yml` | Composite action — copy to `.github/actions/decrypt-secrets/action.yml` |
| `pulumi-setup.sh` | Interactive Pulumi backend setup + CI/CD variable configuration |
| `setup-github-cicd.sh` | Interactive GitHub secrets, variables, and labels setup via `gh` CLI |
| `setup-gitlab-variables.sh` | Interactive GitLab CI/CD variables setup via `glab` CLI |
| `secrets.sh encrypt` | GPG-encrypt `.env` → `.env.gpg` for committing |
| `secrets.sh decrypt` | Decrypt `.env.gpg` → `.env` for local development |
| `taskfile-snippets.yaml` | Task definitions — copy to `infra/Taskfile.yaml` |

The typical first-time setup sequence:

```bash
# 1. Copy scripts and CI config
mkdir -p infra
cp -R <skill-path>/scripts infra/scripts
chmod +x infra/scripts/*.sh
cp infra/scripts/taskfile-snippets.yaml infra/Taskfile.yaml
# Add includes entry to root Taskfile.yml — see Implementation Pattern above

# 2. Copy composite action to its final destination
mkdir -p .github/actions/decrypt-secrets
cp infra/scripts/github-actions/decrypt-secrets/action.yml .github/actions/decrypt-secrets/

# 3. Configure Pulumi backend and CI/CD variables (interactive)
./infra/scripts/pulumi-setup.sh

# 4. Encrypt credentials and push
task infra:encrypt-secrets
git add .env.gpg infra/ .github/ && git commit -m "Add CI/CD infrastructure"
```

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
- [DataRobot Application Templates](https://docs.datarobot.com/en/docs/workbench/wb-apps/app-templates/)
- [DataRobot Codespaces](https://docs.datarobot.com/en/docs/workbench/wb-apps/codespaces/)
