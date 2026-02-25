#!/usr/bin/env bash
# Add secrets to GitHub repository using GitHub CLI
# Requires: gh CLI (https://cli.github.com/)

set -euo pipefail

echo "🔐 GitHub Secrets Setup"
echo "======================="
echo ""

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI (gh) not installed"
    echo ""
    echo "Install with:"
    echo "  macOS:   brew install gh"
    echo "  Linux:   See https://github.com/cli/cli#installation"
    echo ""
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "❌ Not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI authenticated"
echo ""

# Get repository (or use current)
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")
if [ -z "$REPO" ]; then
    read -rp "Enter repository (owner/repo): " REPO
fi

echo "Repository: $REPO"
echo ""

# Function to add a secret (masked)
add_secret() {
    local secret_name=$1
    local secret_description=$2
    local secret_value=""

    echo "📝 Setting up secret: $secret_name"
    echo "   $secret_description"

    read -rsp "   Enter value: " secret_value
    echo ""

    if [ -n "$secret_value" ]; then
        echo "$secret_value" | gh secret set "$secret_name" --repo "$REPO"
        echo "   ✅ Added $secret_name"
    else
        echo "   ⏭️  Skipped (empty value)"
    fi
    echo ""
}

# Function to add a plain (non-secret) Actions variable
add_variable() {
    local var_name=$1
    local var_description=$2
    local default_value=${3:-}
    local var_value=""

    echo "📝 Setting up variable: $var_name"
    echo "   $var_description"
    if [ -n "$default_value" ]; then
        read -rp "   Enter value [$default_value]: " var_value
        var_value="${var_value:-$default_value}"
    else
        read -rp "   Enter value: " var_value
    fi

    if [ -n "$var_value" ]; then
        gh variable set "$var_name" --body "$var_value" --repo "$REPO"
        echo "   ✅ Set $var_name=$var_value"
    else
        echo "   ⏭️  Skipped (empty value)"
    fi
    echo ""
}

# Add secrets
echo "─── Secrets (encrypted) ────────────────────────────────────────────────"
echo "This setup requires ONE secret."
echo "All other credentials (DATAROBOT_API_TOKEN, PULUMI_ACCESS_TOKEN, LLM keys, etc.)"
echo "are stored encrypted in .env.gpg and loaded automatically by the workflow."
echo ""

add_secret "CICD_SECRET_PASSPHRASE" "GPG passphrase for decrypting .env.gpg"

# Add plain CI/CD variables (not sensitive — visible in logs)
echo "─── Variables (plain text) ─────────────────────────────────────────────"
echo "Pulumi stack names are not secrets — they are plain Actions variables."
echo ""

add_variable "PULUMI_STACK_CI_NAME" \
    "Pulumi stack deployed on every merge to the default branch" \
    "ci"
add_variable "PULUMI_STACK_REVIEW_NAME" \
    "Pulumi stack name prefix for PR review apps (PR number appended automatically in the workflow)" \
    "review"

# Create the deploy label (used to gate PR review deployments)
echo "─── Labels ─────────────────────────────────────────────────────────────"
LABEL_NAME="deploy"
LABEL_COLOR="0075ca"
LABEL_DESC="Trigger a review app deployment for this PR"

if gh label list --repo "$REPO" --json name -q '.[].name' | grep -qx "$LABEL_NAME"; then
    echo "✅ Label '$LABEL_NAME' already exists"
else
    gh label create "$LABEL_NAME" \
        --color "$LABEL_COLOR" \
        --description "$LABEL_DESC" \
        --repo "$REPO"
    echo "✅ Created label '$LABEL_NAME'"
fi
echo ""

echo "🎉 Secrets, variables, and labels setup complete!"
echo ""
echo "View all secrets:   gh secret list --repo $REPO"
echo "View all variables: gh variable list --repo $REPO"
echo "View all labels:    gh label list --repo $REPO"
echo ""
echo "Next steps:"
echo "1. Ensure your .env.gpg is committed to the repository"
echo "2. Push your .github/workflows to trigger actions"
echo "3. Add the '$LABEL_NAME' label to a PR to trigger a review deployment"
