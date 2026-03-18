#!/usr/bin/env bash
# Configure GitHub repository for CI/CD: secrets, Actions variables, and labels.
# Requires: gh CLI (https://cli.github.com/)

set -euo pipefail

echo "🔐 GitHub CI/CD Setup"
echo "======================"
echo ""

if ! command -v gh &>/dev/null; then
    echo "❌ GitHub CLI (gh) not installed"
    echo "Install: brew install gh  |  https://github.com/cli/cli#installation"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo "❌ Not authenticated. Run: gh auth login"
    exit 1
fi

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)
if [[ -z "$REPO" ]]; then
    read -rp "Enter repository (owner/repo): " REPO
fi
echo "Repository: $REPO"
echo ""

add_secret() {
    local name="$1" desc="$2" value=""
    echo "📝 Secret: $name"
    echo "   $desc"
    read -rsp "   Value: " value; echo ""
    if [[ -n "$value" ]]; then
        echo "$value" | gh secret set "$name" --repo "$REPO"
        echo "   ✅ Set"
    else
        echo "   ⏭️  Skipped"
    fi
    echo ""
}

add_variable() {
    local name="$1" desc="$2" default="${3:-}" value=""
    echo "📝 Variable: $name"
    echo "   $desc"
    if [[ -n "$default" ]]; then
        read -rp "   Value [$default]: " value
        value="${value:-$default}"
    else
        read -rp "   Value: " value
    fi
    if [[ -n "$value" ]]; then
        gh variable set "$name" --body "$value" --repo "$REPO"
        echo "   ✅ Set $name=$value"
    else
        echo "   ⏭️  Skipped"
    fi
    echo ""
}

echo "─── Secrets ────────────────────────────────────────────────────────────"
echo "Only one secret is required. All other credentials are stored in .env.gpg."
echo ""
add_secret "CICD_SECRET_PASSPHRASE" "GPG passphrase for decrypting .env.gpg"

echo "─── Variables ──────────────────────────────────────────────────────────"
echo "Stack names are not sensitive — stored as plain Actions variables."
echo ""
add_variable "PULUMI_STACK_CI_NAME" \
    "Stack deployed on every merge to main" "ci"
add_variable "PULUMI_STACK_REVIEW_NAME" \
    "Stack name prefix for PR review apps (PR number appended automatically)" "review"

echo "─── Azure OIDC (optional) ───────────────────────────────────────────────"
echo "Only needed if deploying Azure resources. Leave blank to skip."
echo "See: https://learn.microsoft.com/azure/developer/github/connect-from-azure"
echo ""
add_variable "AZURE_CLIENT_ID"       "Azure app registration client ID"
add_variable "AZURE_TENANT_ID"       "Azure tenant ID"
add_variable "AZURE_SUBSCRIPTION_ID" "Azure subscription ID"

echo "─── Labels ─────────────────────────────────────────────────────────────"
echo "Creating 'deploy' label for triggering review app deployments..."
gh label create deploy --description "Deploy a review app for this PR" \
    --color 0075ca --repo "$REPO" 2>/dev/null \
    && echo "   ✅ Created 'deploy' label" \
    || echo "   ℹ️  Label already exists"
echo ""

echo "🎉 Setup complete!"
echo ""
echo "View secrets:   gh secret list --repo $REPO"
echo "View variables: gh variable list --repo $REPO"
echo ""
echo "Next steps:"
echo "  1. Commit .env.gpg if not already: git add .env.gpg && git commit"
echo "  2. Copy workflow files to .github/workflows/"
echo "  3. Copy .github/actions/decrypt-secrets/ to your repo"
echo "  4. Push to trigger the CD workflow"
