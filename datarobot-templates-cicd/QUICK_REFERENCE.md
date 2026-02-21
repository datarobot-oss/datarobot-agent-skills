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
./scripts/setup-github-secrets.sh
```

### Manual Commands
```bash
# Add individual secrets
echo "your-value" | gh secret set SECRET_NAME

# Required secrets
echo "your-gpg-passphrase" | gh secret set LARGE_SECRET_PASSPHRASE
echo "your-pulumi-token" | gh secret set PULUMI_ACCESS_TOKEN
echo "your-dr-token" | gh secret set DATAROBOT_API_TOKEN

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
./scripts/setup-gitlab-variables.sh
```

### Manual Commands
```bash
# Add individual variables (masked for security)
glab variable set VAR_NAME "your-value" --masked

# Required variables
glab variable set DATAROBOT_API_TOKEN "your-token" --masked
glab variable set PULUMI_CONFIG_PASSPHRASE "your-passphrase" --masked
glab variable set GITLAB_API_TOKEN "your-gitlab-token" --masked

# For Azure backend
glab variable set AZURE_STORAGE_ACCOUNT "account-name" --masked
glab variable set AZURE_STORAGE_KEY "account-key" --masked

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
./scripts/encrypt-secrets.sh

# Manual
gpg --symmetric --cipher-algo AES256 .env
git add .env.gpg
git commit -m "Add encrypted secrets"
```

### Decrypt .env Locally
```bash
# Automated
./scripts/decrypt-secrets.sh

# Manual
gpg --quiet --batch --yes --decrypt --output .env .env.gpg
```

## Pulumi Setup

### Interactive Setup
```bash
./scripts/pulumi-setup.sh
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

## Common Task Commands

### From taskfile-snippets.yaml
```bash
# Secrets
task encrypt-secrets
task decrypt-secrets
task verify-secrets

# Pulumi
task pulumi-login-cloud
task pulumi-login-azure
task pulumi-deploy
task pulumi-destroy
task pulumi-output

# Testing
task ci-test-local
task ci-simulate-deploy
```

## Quick Start Workflow

### GitHub
```bash
# 1. Install tools
brew install gh

# 2. Setup
gh auth login
./scripts/setup-github-secrets.sh
./scripts/encrypt-secrets.sh
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
./scripts/setup-gitlab-variables.sh
git add .gitlab-ci.yml

# 3. Push and test
git commit -m "Add CI/CD"
git push
```
