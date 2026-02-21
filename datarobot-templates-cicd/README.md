# DataRobot Application Templates CI/CD Skill

This skill provides comprehensive guidance for setting up production-grade CI/CD pipelines for DataRobot application templates.

## Overview

Transform your DataRobot application templates from manual deployments to automated CI/CD workflows with:

- **Automated Testing**: Run linters and tests on every pull/merge request
- **Review Deployments**: Spin up full application stacks for PR validation
- **Continuous Delivery**: Automatically deploy changes when merged to main
- **Infrastructure as Code**: Use Pulumi for declarative infrastructure management
- **Secrets Management**: Secure handling of API keys and credentials
- **Multi-Platform Support**: Works with both GitLab and GitHub

## What's Included

### Documentation

- **SKILL.md**: Complete guidance for CI/CD setup
  - Quick start guide
  - Platform-specific configurations (GitLab, GitHub)
  - Pulumi state management strategies
  - Secrets management patterns
  - Troubleshooting guide

### Example Configurations

The `scripts/` directory contains ready-to-use configuration files:

- **gitlab-ci.yml**: Complete GitLab CI/CD pipeline
  - Automated testing and linting
  - Manual review app deployments
  - Continuous delivery on merge
  - Azure Blob Storage backend example

- **github-deploy.yml**: GitHub Actions deployment workflow
  - Automated testing and linting
  - PR-based review deployments
  - GPG-encrypted secrets
  - Pulumi Cloud backend example

- **github-destroy.yml**: GitHub Actions cleanup workflow
  - Manual stack destruction
  - Resource cleanup for review apps

- **setup-github-secrets.sh**: Automated GitHub secrets setup
  - Uses GitHub CLI (`gh`)
  - Interactive secret entry
  - Configures all required secrets for Actions

- **setup-gitlab-variables.sh**: Automated GitLab variables setup
  - Uses GitLab CLI (`glab`)
  - Interactive variable entry
  - Configures all required variables for CI/CD

- **encrypt-secrets.sh**: GPG encryption for .env files
  - Interactive encryption workflow
  - GitHub Actions secrets preparation
  - Step-by-step instructions

- **decrypt-secrets.sh**: GPG decryption for local development
  - Safe local secrets management
  - Testing workflow simulation

- **taskfile-snippets.yaml**: CI/CD Task definitions
  - Secrets management commands
  - Pulumi deployment tasks
  - CI/CD testing helpers
  - Copy/paste into your existing Taskfile

- **pulumi-setup.sh**: Interactive Pulumi setup script
  - Backend configuration (Cloud, Azure, AWS)
  - Initial stack creation
  - Credential management

## Quick Start

1. **Choose your platform**: GitLab or GitHub

2. **Copy the appropriate config**:
   ```bash
   # For GitLab
   cp scripts/gitlab-ci.yml .gitlab-ci.yml
   
   # For GitHub
   mkdir -p .github/workflows
   cp scripts/github-deploy.yml .github/workflows/deploy.yml
   cp scripts/github-destroy.yml .github/workflows/destroy.yml
   ```

3. **Set up Pulumi**:
   ```bash
   chmod +x scripts/pulumi-setup.sh
   ./scripts/pulumi-setup.sh
   ```

4. **Configure secrets** in your platform:
   
   For GitHub (automated):
   ```bash
   # Install GitHub CLI: brew install gh
   gh auth login
   ./scripts/setup-github-secrets.sh
   ```
   
   For GitLab (automated):
   ```bash
   # Install GitLab CLI: brew install glab
   glab auth login
   ./scripts/setup-gitlab-variables.sh
   ```

5. **Encrypt your secrets** (for GitHub only):
   ```bash
   ./scripts/encrypt-secrets.sh
   git add .env.gpg
   ```

6. **Add CI/CD tasks** to your existing Taskfile:
   ```bash
   # Copy relevant sections from taskfile-snippets.yaml
   cat scripts/taskfile-snippets.yaml >> Taskfile.yaml
   ```

## Key Features

### GitLab CI/CD
- Parallel test execution for faster feedback
- DIY backend support (Azure Blob, S3, GCS)
- MR-specific stack names for isolation
- Automatic commenting with deployment info
- Manual cleanup jobs

### GitHub Actions
- GPG-encrypted secrets for better management
- PR comments with deployment URLs
- Pulumi Cloud integration
- Manual destroy workflows
- Matrix testing support

### Pulumi Integration
- Centralized state management
- Stack isolation per environment
- Idempotent deployments
- Cross-machine synchronization
- Codespace compatibility

## Use Cases

### Development Teams
- Test infrastructure changes in isolation
- Review applications before merging
- Automatically deploy to staging/production
- Track infrastructure state across team

### DevOps Engineers
- Implement IaC for AI applications
- Manage multiple environments
- Automate deployment workflows
- Monitor infrastructure changes

### Data Scientists
- Deploy models with applications
- Test changes in review environments
- Collaborate on application features
- Focus on ML, not infrastructure

## Example Repositories

See these live implementations:

- **GitLab**: [demo-data-agent](https://gitlab.com/datarobot-oss/demo-data-agent)
- **GitHub**: [demo-talk-to-my-data-agent](https://github.com/datarobot-forks/demo-talk-to-my-data-agent)

## Platform Support

- ✅ GitLab CI/CD
- ✅ GitHub Actions
- ✅ Pulumi Cloud
- ✅ Azure Blob Storage
- ✅ AWS S3
- ✅ Google Cloud Storage

## Resources

- [SKILL.md](SKILL.md) - Complete documentation
- [Task](https://taskfile.dev) - Workflow management
- [Pulumi](https://www.pulumi.com/docs/) - Infrastructure as Code
- [DataRobot Application Templates](https://docs.datarobot.com/en/docs/workbench/wb-apps/app-templates/)

## Contributing

This skill is part of the DataRobot Agent Skills repository. Contributions welcome!

## License

See the main repository LICENSE file.
