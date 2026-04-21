# CI/CD Setup

This directory contains GitHub Actions workflows for deploying to DataRobot using Pulumi Cloud.

## Workflows

| File | Trigger | What it does |
|------|---------|--------------|
| `cd.yml` | Automatic — every merge to `main` | Deploys `main` to the persistent CI stack |
| `deploy-pr.yml` | Manual — you choose branch and stack name | Deploys a preview stack from a PR branch |
| `destroy.yml` | Manual — you enter the stack name | Destroys a named Pulumi stack |

`cd.yml` is the only workflow that runs automatically. Everything else requires you to trigger it from the Actions tab.

## One-time setup

### 1. Create a Pulumi Cloud account

Sign up at [app.pulumi.com](https://app.pulumi.com) (free tier is sufficient for most projects).

Create an access token: click your **profile icon → Access Tokens → Create token**. Copy the token — you will need it in step 3.

### 2. Get a DataRobot API key

Ask your DataRobot admin to create a **service account** user (e.g. `ci-bot@your-org.com`) and generate an API key under **Developer Tools → API Key**. Using a service account instead of a personal API key prevents CI/CD from breaking when people leave the team.

> If you are just getting started, you can use your own personal API key temporarily and replace it later.

### 3. Add GitHub Secrets

Go to: **Settings → Secrets and variables → Actions → Secrets tab → New repository secret**

| Secret name | Where to get it |
|-------------|----------------|
| `DATAROBOT_API_TOKEN` | DataRobot → Developer Tools → API Key |
| `PULUMI_ACCESS_TOKEN` | Pulumi Cloud → Profile → Access Tokens |

Both secrets are required. The workflows will not run without them.

### 4. (Optional) Set a custom CI stack name

The `cd.yml` workflow deploys to a Pulumi stack named `ci` by default. To use a different name, add a repository variable:

**Settings → Secrets and variables → Actions → Variables tab → New repository variable**

| Variable name | Value |
|---------------|-------|
| `PULUMI_STACK_CI_NAME` | Your preferred stack name (e.g. `ci`, `prod`, `staging`) |

Skip this step if `ci` is fine.

## How to trigger deployments

**Automatic deploy (merge to main):**
`cd.yml` runs automatically every time code is merged to `main`. No action needed.

**Manual PR preview deploy:**
1. Open a PR and get ready to test it in a live environment.
2. Go to **Actions → Deploy (PR Preview)** in the GitHub UI.
3. Click **Run workflow**.
4. Select your PR branch from the dropdown.
5. Enter a stack name — tip: use the PR number (e.g. `pr-42`) so it's easy to track.
6. Click **Run workflow**. Each stack is isolated, so multiple PRs can have their own live environment.

**Destroy a stack (manual cleanup):**
1. Go to **Actions → Destroy Stack**.
2. Click **Run workflow → Run workflow**.
3. Enter the exact stack name you want to destroy (e.g. `pr-42` or `ci`).

> The CI stack (`ci`) is recreated automatically on the next merge to `main`. Destroy it only if you want to tear everything down.
