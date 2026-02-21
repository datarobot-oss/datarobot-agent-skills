---
name: datarobot-templates-cicd
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

## Key capabilities

### 1. Testing and Linting

- Automated Python linting with ruff and mypy
- TypeScript/React linting and testing
- Task-based workflow management
- Parallel test execution for faster feedback
- Per merge request validation

### 2. GitLab CI/CD

- Automated testing on merge requests
- Manual review app deployments
- Continuous delivery on merge to main
- Pulumi-based infrastructure management
- DIY backend support (Azure Blob, S3)

### 3. GitHub Actions

- Automated testing on pull requests
- Review deployments with PR comments
- Pulumi Cloud or DIY backend support
- GPG-encrypted secrets management
- Manual workflow triggers for resource cleanup

### 4. Pulumi State Management

- Centralized state backends (Pulumi Cloud, Azure, AWS, GCP)
- Stack isolation per environment/PR
- Idempotent infrastructure updates
- Cross-machine state synchronization
- Codespace-compatible workflows

### 5. Secrets Management

- GitHub Actions secrets
- GitLab CI/CD variables
- GPG-encrypted .env files
- Environment variable injection
- Secure credential handling

## Workflow examples

### Example 1: Set up GitLab CI/CD with review apps

**User request**: "Set up GitLab CI/CD for my application template with automated testing and manual review deployments"

**Agent workflow**:
1. Create `.gitlab-ci.yml` in repository root
2. Configure `before_script` to install Task and dependencies
3. Add `lint` and `test` stages that run on merge requests
4. Add manual `review_app` stage with Pulumi deployment
5. Configure environment variables in GitLab project settings
6. Set up Pulumi DIY backend (Azure Blob) for state management
7. Add cleanup job to destroy review stacks
8. Test pipeline with a sample merge request

### Example 2: Set up GitHub Actions with encrypted secrets

**User request**: "Configure GitHub Actions CI/CD with GPG-encrypted secrets and review deployments"

**Agent workflow**:
1. Create `.github/workflows/deploy.yml` workflow file
2. Encrypt `.env` file with GPG: `gpg --symmetric --cipher-algo AES256 .env`
3. Add encrypted `.env.gpg` to repository
4. Store GPG passphrase in GitHub repository secrets
5. Configure workflow to decrypt secrets at runtime
6. Add Pulumi deployment step that creates PR-specific stacks
7. Configure workflow to comment on PR with deployment URLs
8. Create destroy workflow for manual resource cleanup
9. Set up Pulumi Cloud backend with access token

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

### Complete .gitlab-ci.yml example

```yaml
image: cimg/python:3.11-node

variables:
  DATAROBOT_ENDPOINT: https://app.datarobot.com/api/v2
  FRONTEND_TYPE: react
  # Set these in GitLab CI/CD variables:
  # DATAROBOT_API_TOKEN
  # PULUMI_CONFIG_PASSPHRASE
  # OPENAI_API_KEY
  # AZURE_STORAGE_ACCOUNT
  # AZURE_STORAGE_KEY
  # GITLAB_API_TOKEN

before_script:
  - pip install go-task-bin
  - task install
  - source .venv/bin/activate

stages:
  - check
  - review
  - deploy
  - cleanup

lint:
  stage: check
  script:
    - task lint-check
  only:
    - merge_requests

test:
  stage: check
  script:
    - task test
  only:
    - merge_requests

review_app:
  stage: review
  script:
    - curl -fsSL https://get.pulumi.com | sh
    - export PATH="~/.pulumi/bin:$PATH"
    - pulumi login --cloud-url "azblob://dr-ai-apps-pulumi"
    - pulumi stack select --create gitlab-mr-$CI_MERGE_REQUEST_IID
    - pulumi up --yes --stack gitlab-mr-$CI_MERGE_REQUEST_IID
    - echo "Deploying review app for MR $CI_MERGE_REQUEST_IID"
    - STACK_OUTPUT="<br><br>$(pulumi stack output --shell)"
    - STACK_OUTPUT="${STACK_OUTPUT//$'\n'/<br>}"
    - |
      curl --header "PRIVATE-TOKEN: $GITLAB_API_TOKEN" \
         --data "body=Review Deployment: $STACK_OUTPUT" \
         "$CI_API_V4_URL/projects/$CI_PROJECT_ID/merge_requests/$CI_MERGE_REQUEST_IID/notes"
  only:
    - merge_requests
  when: manual

destroy_review_app:
  stage: cleanup
  script:
    - curl -fsSL https://get.pulumi.com | sh
    - export PATH="~/.pulumi/bin:$PATH"
    - pulumi login --cloud-url "azblob://dr-ai-apps-pulumi"
    - pulumi destroy --yes --stack gitlab-mr-$CI_MERGE_REQUEST_IID
    - pulumi stack rm gitlab-mr-$CI_MERGE_REQUEST_IID --yes
    - echo "Destroyed review app for MR $CI_MERGE_REQUEST_IID"
  only:
    - merge_requests
    - main
  when: manual
  needs:
    - job: review_app
      optional: true

deploy_ci:
  stage: deploy
  script:
    - curl -fsSL https://get.pulumi.com | sh
    - export PATH="~/.pulumi/bin:$PATH"
    - pulumi login --cloud-url "azblob://dr-ai-apps-pulumi"
    - pulumi stack select ci
    - pulumi up --yes --stack ci
    - echo "Deployed CI stack"
  only:
    - main
  when: on_success
```

## GitHub Actions Configuration

### Complete deploy workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Pulumi Deployment
on:
  pull_request:
    types: [opened, synchronize, reopened]

env:
  PULUMI_STACK_NAME: github-pr-${{ github.event.repository.name }}-${{ github.event.number }}

jobs:
  test:
    name: test-and-lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Decrypt Secrets
        run: gpg --quiet --batch --yes --decrypt --passphrase="$LARGE_SECRET_PASSPHRASE" --output .env .env.gpg
        env:
          LARGE_SECRET_PASSPHRASE: ${{ secrets.LARGE_SECRET_PASSPHRASE }}
      - uses: actions/setup-python@v5
        with:
          python-version: 3.12
      - name: Install Task
        run: pip install go-task-bin
      - name: Install Dependencies
        run: task install
      - name: Lint
        run: task lint-check
      - name: Test
        run: task test

  deploy:
    name: pulumi-deploy-stack
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - name: Decrypt Secrets
        run: gpg --quiet --batch --yes --decrypt --passphrase="$LARGE_SECRET_PASSPHRASE" --output .env .env.gpg
        env:
          LARGE_SECRET_PASSPHRASE: ${{ secrets.LARGE_SECRET_PASSPHRASE }}
      - uses: actions/setup-python@v5
        with:
          python-version: 3.12
      - name: Install Pulumi
        run: |
          curl -fsSL https://get.pulumi.com | sh
          echo "$HOME/.pulumi/bin" >> $GITHUB_PATH
      - name: Setup Project Dependencies
        run: |
          command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
          uv venv .venv
          source .venv/bin/activate
          uv pip install -r requirements.txt
      - name: Deploy with Pulumi
        id: pulumi_deploy
        run: |
          source .venv/bin/activate
          export $(grep -v '^#' .env | xargs)
          pulumi stack select --create $PULUMI_STACK_NAME
          pulumi up --yes
          PULUMI_OUTPUT=$(pulumi stack output --json)
          APPLICATION_URL=$(echo "$PULUMI_OUTPUT" | jq -r 'to_entries[] | select(.key | startswith("Data Analyst Application")) | .value')
          DEPLOYMENT_URL=$(echo "$PULUMI_OUTPUT" | jq -r 'to_entries[] | select(.key | startswith("Generative Analyst Deployment")) | .value')
          APP_ID=$(echo "$PULUMI_OUTPUT" | jq -r '.DATAROBOT_APPLICATION_ID // empty')
          LLM_ID=$(echo "$PULUMI_OUTPUT" | jq -r '.LLM_DEPLOYMENT_ID // empty')
          echo "application_url=${APPLICATION_URL}" >> $GITHUB_OUTPUT
          echo "deployment_url=${DEPLOYMENT_URL}" >> $GITHUB_OUTPUT
          echo "app_id=${APP_ID}" >> $GITHUB_OUTPUT
          echo "llm_id=${LLM_ID}" >> $GITHUB_OUTPUT
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
      - name: Comment PR with App URL
        uses: peter-evans/create-or-update-comment@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          issue-number: ${{ github.event.number }}
          body: |
            # 🚀 Your application is ready!
            ## Application Info
            - **Application URL:** [${{ steps.pulumi_deploy.outputs.application_url }}](${{ steps.pulumi_deploy.outputs.application_url }})
            - **Application ID:** `${{ steps.pulumi_deploy.outputs.app_id }}`
            ## LLM Deployment
            - **Deployment URL:** [${{ steps.pulumi_deploy.outputs.deployment_url }}](${{ steps.pulumi_deploy.outputs.deployment_url }})
            - **Deployment ID:** `${{ steps.pulumi_deploy.outputs.llm_id }}`
            ### Pulumi Stack
            - **Stack Name:** `${{ env.PULUMI_STACK_NAME }}`
```

### Destroy workflow

Create `.github/workflows/destroy.yml`:

```yaml
name: Pulumi Stack Destroy
on:
  workflow_dispatch:
    inputs:
      stack_name:
        description: 'Stack name to destroy (e.g. github-pr-repo-42)'
        required: true
        type: string

jobs:
  destroy:
    name: pulumi-destroy-stack
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: 3.12
      - name: Install Pulumi
        run: |
          curl -fsSL https://get.pulumi.com | sh
          echo "$HOME/.pulumi/bin" >> $GITHUB_PATH
      - name: Setup Dependencies
        run: |
          command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
          uv venv .venv
          source .venv/bin/activate
          uv pip install -r requirements.txt
      - name: Destroy Stack
        run: |
          source .venv/bin/activate
          pulumi stack select ${{ github.event.inputs.stack_name }}
          pulumi destroy --yes
          pulumi stack rm --yes ${{ github.event.inputs.stack_name }}
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
```

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

### GitHub: GPG-Encrypted Secrets

#### Automated Setup with GitHub CLI

**Quick setup using gh CLI:**

```bash
# Install GitHub CLI if needed
brew install gh  # macOS
# or see https://cli.github.com/ for other platforms

# Authenticate
gh auth login

# Run the setup script (interactive)
./scripts/setup-github-secrets.sh
```

The script will:
- Detect your repository automatically
- Prompt for each required secret
- Add secrets using `gh secret set`
- Handle optional secrets (LLM keys, cloud providers)

**Manual commands:**

```bash
# Add secrets one by one
echo "your-passphrase" | gh secret set LARGE_SECRET_PASSPHRASE
echo "your-token" | gh secret set PULUMI_ACCESS_TOKEN
echo "your-dr-token" | gh secret set DATAROBOT_API_TOKEN

# List all secrets
gh secret list

# Delete a secret
gh secret remove SECRET_NAME
```

#### Manual Setup via Web UI

**Encrypt your .env file:**

```bash
# Use the provided script (recommended)
./scripts/encrypt-secrets.sh

# Or manually with GPG:
gpg --symmetric --cipher-algo AES256 .env

# You'll be prompted for a passphrase
# This creates .env.gpg
```

**Add to repository:**

```bash
git add .env.gpg
git commit -m "Add encrypted secrets"
git push
```

**Configure GitHubSecret:**

1. Go to repository Settings → Secrets and variables → Actions
2. Create secret `LARGE_SECRET_PASSPHRASE` with your GPG passphrase
3. Workflow will decrypt at runtime

**Decrypt in workflow:**

```yaml
- name: Decrypt Secrets
  run: gpg --quiet --batch --yes --decrypt --passphrase="$LARGE_SECRET_PASSPHRASE" --output .env .env.gpg
  env:
    LARGE_SECRET_PASSPHRASE: ${{ secrets.LARGE_SECRET_PASSPHRASE }}
```

**Decrypt locally for testing:**

```bash
./scripts/decrypt-secrets.sh
# Or add as Task:
task decrypt-secrets
```

### GitLab: CI/CD Variables

#### Automated Setup with GitLab CLI

**Quick setup using glab CLI:**

```bash
# Install GitLab CLI if needed
brew install glab  # macOS
# or see https://gitlab.com/gitlab-org/cli for other platforms

# Authenticate
glab auth login

# Run the setup script (interactive)
./scripts/setup-gitlab-variables.sh
```

The script will:
- Detect your project automatically
- Prompt for each required variable
- Add variables using `glab variable set`
- Handle Pulumi backend selection (Azure/S3/GCS)
- Automatically mask sensitive values

**Manual commands:**

```bash
# Add variables one by one
glab variable set DATAROBOT_API_TOKEN "your-token" --masked
glab variable set PULUMI_CONFIG_PASSPHRASE "your-passphrase" --masked
glab variable set AZURE_STORAGE_ACCOUNT "account-name" --masked
glab variable set AZURE_STORAGE_KEY "account-key" --masked

# List all variables
glab variable list

# Update a variable
glab variable update VAR_NAME "new-value" --masked

# Delete a variable
glab variable delete VAR_NAME
```

#### Manual Setup via Web UI

**Configure in GitLab:**

1. Go to Project Settings → CI/CD → Variables
2. Add each secret as a variable
3. Mark as "Masked" to hide in logs
4. Mark as "Protected" for protected branches only

**Common variables:**

```
DATAROBOT_API_TOKEN
DATAROBOT_ENDPOINT
PULUMI_CONFIG_PASSPHRASE
OPENAI_API_KEY
OPENAI_API_BASE
AZURE_STORAGE_ACCOUNT
AZURE_STORAGE_KEY
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

**Reference in .gitlab-ci.yml:**

```yaml
variables:
  DATAROBOT_ENDPOINT: https://app.datarobot.com/api/v2
  # These are set in CI/CD variables (automatically available):
  # DATAROBOT_API_TOKEN: "$DATAROBOT_API_TOKEN"
  # PULUMI_CONFIG_PASSPHRASE: "$PULUMI_CONFIG_PASSPHRASE"
```

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

## Common patterns

### Pattern 1: GitLab with Azure DIY Backend

```yaml
# .gitlab-ci.yml
image: cimg/python:3.11-node

variables:
  DATAROBOT_ENDPOINT: https://app.datarobot.com/api/v2

before_script:
  - pip install go-task-bin
  - task install
  - source .venv/bin/activate

stages:
  - check
  - review
  - deploy

lint:
  stage: check
  script:
    - task lint-check
  only:
    - merge_requests

test:
  stage: check
  script:
    - task test
  only:
    - merge_requests

review_app:
  stage: review
  script:
    - curl -fsSL https://get.pulumi.com | sh
    - export PATH="~/.pulumi/bin:$PATH"
    - pulumi login --cloud-url "azblob://my-pulumi-state"
    - pulumi stack select --create mr-$CI_MERGE_REQUEST_IID
    - pulumi up --yes
  only:
    - merge_requests
  when: manual

deploy_prod:
  stage: deploy
  script:
    - curl -fsSL https://get.pulumi.com | sh
    - export PATH="~/.pulumi/bin:$PATH"
    - pulumi login --cloud-url "azblob://my-pulumi-state"
    - pulumi stack select prod
    - pulumi up --yes
  only:
    - main
```

### Pattern 2: GitHub with Pulumi Cloud

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  pull_request:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Decrypt Secrets
        run: gpg --quiet --batch --yes --decrypt --passphrase="$GPG_PASS" --output .env .env.gpg
        env:
          GPG_PASS: ${{ secrets.LARGE_SECRET_PASSPHRASE }}
      - uses: actions/setup-python@v5
        with:
          python-version: 3.12
      - name: Install Pulumi
        run: |
          curl -fsSL https://get.pulumi.com | sh
          echo "$HOME/.pulumi/bin" >> $GITHUB_PATH
      - name: Deploy
        run: |
          command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh
          uv venv .venv
          source .venv/bin/activate
          uv pip install -r requirements.txt
          export $(grep -v '^#' .env | xargs)
          STACK_NAME="${{ github.event_name == 'pull_request' && format('pr-{0}', github.event.number) || 'prod' }}"
          pulumi stack select --create $STACK_NAME
          pulumi up --yes
        env:
          PULUMI_ACCESS_TOKEN: ${{ secrets.PULUMI_ACCESS_TOKEN }}
```

### Pattern 3: Multi-environment deployment

```yaml
# .gitlab-ci.yml with multiple environments
stages:
  - check
  - review
  - staging
  - production

test:
  stage: check
  script:
    - task test
  only:
    - merge_requests
    - main

review_app:
  stage: review
  environment:
    name: review/$CI_MERGE_REQUEST_IID
    on_stop: destroy_review
  script:
    - pulumi login --cloud-url "azblob://pulumi-state"
    - pulumi stack select --create review-$CI_MERGE_REQUEST_IID
    - pulumi up --yes
  only:
    - merge_requests
  when: manual

destroy_review:
  stage: review
  environment:
    name: review/$CI_MERGE_REQUEST_IID
    action: stop
  script:
    - pulumi login --cloud-url "azblob://pulumi-state"
    - pulumi destroy --yes --stack review-$CI_MERGE_REQUEST_IID
    - pulumi stack rm review-$CI_MERGE_REQUEST_IID --yes
  only:
    - merge_requests
  when: manual

deploy_staging:
  stage: staging
  environment:
    name: staging
  script:
    - pulumi login --cloud-url "azblob://pulumi-state"
    - pulumi stack select staging
    - pulumi up --yes
  only:
    - main

deploy_production:
  stage: production
  environment:
    name: production
  script:
    - pulumi login --cloud-url "azblob://pulumi-state"
    - pulumi stack select production
    - pulumi up --yes
  only:
    - main
  when: manual
```

## Helper Scripts

This skill includes practical scripts and configuration examples in the `scripts/` directory:

**CI/CD Configurations:**
- `scripts/gitlab-ci.yml` - Complete GitLab CI/CD pipeline configuration
- `scripts/github-deploy.yml` - GitHub Actions deployment workflow
- `scripts/github-destroy.yml` - GitHub Actions destroy workflow

**Secrets Management:**
- `scripts/setup-github-secrets.sh` - Interactive GitHub secrets setup via gh CLI
- `scripts/setup-gitlab-variables.sh` - Interactive GitLab variables setup via glab CLI
- `scripts/encrypt-secrets.sh` - Encrypt .env file with GPG for GitHub Actions
- `scripts/decrypt-secrets.sh` - Decrypt .env.gpg for local development
- `scripts/taskfile-snippets.yaml` - Ready-to-use Task definitions for CI/CD operations

**Infrastructure Setup:**
- `scripts/pulumi-setup.sh` - Interactive Pulumi backend configuration

### Using the Scripts
**Set up GitHub secrets (automated):**
```bash
# Install GitHub CLI
brew install gh  # macOS
# See https://cli.github.com/ for other platforms

# Authenticate
gh auth login

# Run interactive setup
./scripts/setup-github-secrets.sh
```

**Set up GitLab variables (automated):**
```bash
# Install GitLab CLI
brew install glab  # macOS
# See https://gitlab.com/gitlab-org/cli for other platforms

# Authenticate
glab auth login

# Run interactive setup
./scripts/setup-gitlab-variables.sh
```
**Encrypt secrets for GitHub Actions:**
```bash
chmod +x scripts/encrypt-secrets.sh
./scripts/encrypt-secrets.sh
# Follow prompts, then add passphrase to GitHub Secrets
```

**Decrypt secrets locally:**
```bash
chmod +x scripts/decrypt-secrets.sh
./scripts/decrypt-secrets.sh
# Enter your passphrase
```

**Add CI/CD tasks to your Taskfile:**
```bash
# Copy relevant sections from taskfile-snippets.yaml to your Taskfile.yaml
cat scripts/taskfile-snippets.yaml >> Taskfile.yaml
# Then customize for your needs
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
