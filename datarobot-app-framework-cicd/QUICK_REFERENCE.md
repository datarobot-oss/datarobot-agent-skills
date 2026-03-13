# CI/CD Setup Quick Reference

## GitHub Secrets Setup

### Using GitHub CLI (Automated)
```bash
# Install gh CLI
brew install gh  # macOS
# or: https://cli.github.com/

# Authenticate
gh auth login

# Run setup script
./infra/scripts/setup-github-secrets.sh
```

### Manual Commands
```bash
# Add individual secrets
echo "your-value" | gh secret set SECRET_NAME

# Only ONE secret is required — all other credentials live in .env.gpg
echo "your-gpg-passphrase" | gh secret set CICD_SECRET_PASSPHRASE

# List secrets
gh secret list

# Delete a secret
gh secret remove SECRET_NAME
```

## GitLab Variables Setup

### Using GitLab CLI (Automated)
```bash
# Install glab CLI
brew install glab  # macOS
# or: https://gitlab.com/gitlab-org/cli

# Authenticate
glab auth login

# Run setup script
./infra/scripts/setup-gitlab-variables.sh
```

### Manual Commands
```bash
# Add individual variables (masked for security)
glab variable set VAR_NAME "your-value" --masked

# Only TWO variables are required — all other credentials live in .env.gpg
# CICD_SECRET_PASSPHRASE: GPG passphrase to decrypt .env.gpg
glab variable set CICD_SECRET_PASSPHRASE "your-gpg-passphrase" --masked
# GITLAB_API_TOKEN: needed for posting MR comments (GitLab-specific, not in .env)
glab variable set GITLAB_API_TOKEN "your-gitlab-token" --masked

# List variables
glab variable list

# Update a variable
glab variable update VAR_NAME "new-value" --masked

# Delete a variable
glab variable delete VAR_NAME
```

## Secrets Management

### Encrypt .env for GitHub
```bash
# Automated
./infra/scripts/encrypt-secrets.sh

# Manual
gpg --symmetric --cipher-algo AES256 .env
git add .env.gpg
git commit -m "Add encrypted secrets"
```

### Decrypt .env Locally
```bash
# Automated
./infra/scripts/decrypt-secrets.sh

# Manual
gpg --quiet --batch --yes --decrypt --output .env .env.gpg
```

## Pulumi Setup

### Interactive Setup
```bash
./infra/scripts/pulumi-setup.sh
```

### Manual Setup
```bash
# Pulumi Cloud
pulumi login

# Azure Blob
export AZURE_STORAGE_ACCOUNT=myaccount
export AZURE_STORAGE_KEY=mykey
pulumi login azblob://container-name

# AWS S3
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
pulumi login s3://bucket-name
```

## Migrating Stacks to a Different Backend

Run `pulumi-setup.sh` — it detects backend mismatches automatically. For manual migration:

```bash
# 1. Check current backend and local stacks
pulumi whoami --verbose   # note "Backend URL:"
ls Pulumi.*.yaml          # stack files present locally

# 2. Export each stack (while still on the old backend)
pulumi stack export --stack <stackname> --file <stackname>-backup.json

# 3. Login to the new backend (set credentials first)
pulumi login azblob://my-container   # or s3://, or pulumi login for Cloud

# 4. Import into new backend
pulumi stack select --create <stackname>
pulumi stack import --file <stackname>-backup.json
rm <stackname>-backup.json
```

> Migration is needed when `pulumi whoami --verbose` shows a different Backend URL than
> the CI/CD target (e.g., local `file://` vs CI `azblob://`).

## Common Task Commands

### From taskfile-snippets.yaml
> ⚠️ Tasks are namespaced under `infra:` (included from `infra/Taskfile.yaml`)
```bash
# Secrets
task infra:encrypt-secrets
task infra:decrypt-secrets
task infra:verify-secrets

# Pulumi
task infra:pulumi-login-cloud
task infra:pulumi-login-azure
task infra:pulumi-deploy
task infra:pulumi-destroy
task infra:pulumi-output

# Testing
task infra:ci-test-local
task infra:ci-simulate-deploy
```

## Quick Start Workflow

### GitHub
```bash
# 1. Install tools
brew install gh

# 2. Setup
gh auth login
./infra/scripts/encrypt-secrets.sh     # encrypts .env → .env.gpg
./infra/scripts/setup-github-secrets.sh  # sets only CICD_SECRET_PASSPHRASE
git add .env.gpg .github/

# 3. Push and test
git commit -m "Add CI/CD"
git push
```

### GitLab
```bash
# 1. Install tools
brew install glab

# 2. Setup
glab auth login
./infra/scripts/setup-gitlab-variables.sh
git add .gitlab-ci.yml

# 3. Push and test
git commit -m "Add CI/CD"
git push
```
