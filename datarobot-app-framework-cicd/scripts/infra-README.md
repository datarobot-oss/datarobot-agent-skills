# Infrastructure and CI/CD Scripts

This directory contains all CI/CD and infrastructure-related scripts for the application template.

## Directory Structure

```
project-root/
├── infra/
│   ├── Taskfile.yaml               # ⚠️ CI/CD tasks go HERE (copy from infra/scripts/taskfile-snippets.yaml)
│   └── scripts/                    # CI/CD scripts directory
│       ├── setup-github-secrets.sh     # GitHub secrets setup (gh CLI)
│       ├── setup-gitlab-variables.sh   # GitLab variables setup (glab CLI)
│       ├── encrypt-secrets.sh          # Encrypt root .env → .env.gpg
│       ├── decrypt-secrets.sh          # Decrypt root .env.gpg → .env
│       ├── pulumi-setup.sh             # Pulumi backend configuration
│       ├── gitlab-ci.yml               # GitLab CI/CD template
│       ├── github-deploy.yml           # GitHub Actions deploy template
│       ├── github-destroy.yml          # GitHub Actions destroy template
│       ├── taskfile-snippets.yaml      # Source for infra/Taskfile.yaml (do NOT paste into root Taskfile.yml)
│       └── README.md                   # This file
├── .env                            # Secrets (never commit!)
├── .env.gpg                        # Encrypted secrets (commit this)
├── .gitlab-ci.yml                  # Copied from infra/scripts/gitlab-ci.yml
├── .github/
│   └── workflows/
│       ├── deploy.yml              # Copied from infra/scripts/github-deploy.yml
│       └── destroy.yml             # Copied from infra/scripts/github-destroy.yml
└── Taskfile.yml                    # Root Taskfile — ONLY add includes entry for infra/Taskfile.yaml
```

## Scripts Overview

### Secrets Management

#### `encrypt-secrets.sh`
Encrypts `../../.env` to `../../.env.gpg` using GPG for GitHub Actions.

**Usage:**
```bash
cd infra/scripts
./encrypt-secrets.sh
# Or from root: task encrypt-secrets
```

#### `decrypt-secrets.sh`
Decrypts `../../.env.gpg` to `../../.env` for local development.

**Usage:**
```bash
cd infra/scripts
./decrypt-secrets.sh
# Or from root: task decrypt-secrets
```

#### `setup-github-secrets.sh`
Interactive setup of GitHub repository secrets using `gh` CLI.

**Usage:**
```bash
cd infra/scripts
./setup-github-secrets.sh
# Or from root: task setup-github-secrets
```

**Prerequisites:**
- GitHub CLI installed: `brew install gh`
- Authenticated: `gh auth login`

#### `setup-gitlab-variables.sh`
Interactive setup of GitLab project variables using `glab` CLI.

**Usage:**
```bash
cd infra/scripts
./setup-gitlab-variables.sh
# Or from root: task setup-gitlab-vars
```

**Prerequisites:**
- GitLab CLI installed: `brew install glab`
- Authenticated: `glab auth login`

### Infrastructure Setup

#### `pulumi-setup.sh`
Interactive Pulumi backend configuration with support for:
- Pulumi Cloud
- Azure Blob Storage
- AWS S3
- Google Cloud Storage

**Usage:**
```bash
cd infra/scripts
./pulumi-setup.sh
```

### CI/CD Configuration Templates

#### `gitlab-ci.yml`
Complete GitLab CI/CD pipeline template with:
- Automated linting and testing
- Manual review app deployments
- Continuous delivery on merge to main
- Pulumi DIY backend support

**Setup:**
```bash
cp infra/scripts/gitlab-ci.yml .gitlab-ci.yml
```

#### `github-deploy.yml`
GitHub Actions deployment workflow with:
- Automated testing and linting
- PR-based review deployments
- GPG-encrypted secrets support
- PR comments with deployment URLs

**Setup:**
```bash
mkdir -p .github/workflows
cp infra/scripts/github-deploy.yml .github/workflows/deploy.yml
```

#### `github-destroy.yml`
GitHub Actions workflow for manual stack cleanup.

**Setup:**
```bash
cp infra/scripts/github-destroy.yml .github/workflows/destroy.yml
```

### Taskfile Integration

#### `taskfile-snippets.yaml`
Contains Task definitions to copy to `infra/Taskfile.yaml`.

> ⚠️ **Do NOT paste these tasks into the root `Taskfile.yml`.** Instead:
> 1. Copy this file: `cp infra/scripts/taskfile-snippets.yaml infra/Taskfile.yaml`
> 2. Add a single `includes` entry to the root `Taskfile.yml`:
>    ```yaml
>    includes:
>      infra:
>        taskfile: ./infra/Taskfile.yaml
>        dir: .
>    ```
> 3. Run tasks as: `task infra:encrypt-secrets`, `task infra:setup-github-secrets`, etc.

## Quick Start

### For GitLab

1. **Setup infrastructure:**
   ```bash
   cp infra/scripts/gitlab-ci.yml .gitlab-ci.yml
   ```

2. **Configure secrets:**
   ```bash
   task setup-gitlab-vars
   ```

3. **Push and test:**
   ```bash
   git add .gitlab-ci.yml
   git commit -m "Add GitLab CI/CD"
   git push
   ```

### For GitHub

1. **Setup infrastructure:**
   ```bash
   mkdir -p .github/workflows
   cp infra/scripts/github-deploy.yml .github/workflows/deploy.yml
   cp infra/scripts/github-destroy.yml .github/workflows/destroy.yml
   ```

2. **Encrypt secrets:**
   ```bash
   task encrypt-secrets
   git add .env.gpg
   ```

3. **Configure GitHub secrets:**
   ```bash
   task setup-github-secrets
   ```

4. **Push and test:**
   ```bash
   git add .github/ .env.gpg
   git commit -m "Add GitHub Actions CI/CD"
   git push
   ```

## File Locations

- **Secrets**: `.env` and `.env.gpg` are in the **project root**, not in `infra/`
- **Scripts**: All scripts are in `infra/scripts/` directory
- **CI/CD configs**: Copied from `infra/scripts/` to their standard locations (`.gitlab-ci.yml`, `.github/workflows/`)
- **Taskfile**: `infra/Taskfile.yaml` contains all CI/CD tasks. Root `Taskfile.yml` includes it via `includes: {infra: {taskfile: ./infra/Taskfile.yaml}}`

## Security Notes

- **Never commit `.env`** - Add to `.gitignore`
- **Do commit `.env.gpg`** - It's encrypted and safe
- **Store GPG passphrase** in GitHub Secrets as `CICD_SECRET_PASSPHRASE`
- **Mark GitLab variables** as "Masked" to hide in logs
- **Rotate credentials** regularly

## Troubleshooting

### Scripts won't run
```bash
chmod +x infra/scripts/*.sh
```

### Can't find .env
Make sure `.env` is in the project root, not in `infra/`

### GPG decryption fails
Ensure you're using the same passphrase used for encryption

### gh/glab commands fail
Make sure you're authenticated:
```bash
gh auth login    # GitHub
glab auth login  # GitLab
```

## Resources

- [DataRobot CI/CD Skill Documentation](../SKILL.md)
- [Task Documentation](https://taskfile.dev)
- [Pulumi Documentation](https://www.pulumi.com/docs/)
- [GitHub Actions](https://docs.github.com/actions)
- [GitLab CI/CD](https://docs.gitlab.com/ci/)
