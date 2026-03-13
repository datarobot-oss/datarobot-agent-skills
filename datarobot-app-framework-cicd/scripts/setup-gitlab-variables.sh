#!/usr/bin/env bash
# Add variables to GitLab project using GitLab CLI
# Requires: glab CLI (https://gitlab.com/gitlab-org/cli)

set -euo pipefail

echo "🔐 GitLab CI/CD Variables Setup"
echo "================================"
echo ""

# Check if glab is installed
if ! command -v glab &> /dev/null; then
    echo "❌ GitLab CLI (glab) not installed"
    echo ""
    echo "Install with:"
    echo "  macOS:   brew install glab"
    echo "  Linux:   See https://gitlab.com/gitlab-org/cli#installation"
    echo ""
    exit 1
fi

# Check if authenticated
if ! glab auth status &> /dev/null; then
    echo "❌ Not authenticated with GitLab CLI"
    echo "Run: glab auth login"
    exit 1
fi

echo "✅ GitLab CLI authenticated"
echo ""

# Get project (or use current)
PROJECT=$(glab repo view --output json 2>/dev/null | jq -r '.path_with_namespace' || echo "")
if [ -z "$PROJECT" ]; then
    read -rp "Enter project (group/project): " PROJECT
fi

echo "Project: $PROJECT"
echo ""

# Function to add a variable
add_variable() {
    local var_name=$1
    local var_description=$2
    local var_value=""
    local mask_flag="--masked"  # Mask by default for security

    echo "📝 Setting up: $var_name"
    echo "   $var_description"

    read -rsp "   Enter value: " var_value
    echo ""

    if [ -n "$var_value" ]; then
        # GitLab CLI command to set variable
        glab variable set "$var_name" "$var_value" --scope="*" $mask_flag --repo "$PROJECT" 2>/dev/null || \
        glab variable update "$var_name" "$var_value" --scope="*" $mask_flag --repo "$PROJECT" 2>/dev/null
        echo "   ✅ Added $var_name"
    else
        echo "   ⏭️  Skipped (empty value)"
    fi
    echo ""
}

# Function to add a plain (non-masked) variable
add_plain_variable() {
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
        glab variable set "$var_name" "$var_value" --scope="*" --repo "$PROJECT" 2>/dev/null || \
        glab variable update "$var_name" "$var_value" --scope="*" --repo "$PROJECT" 2>/dev/null
        echo "   ✅ Set $var_name=$var_value"
    else
        echo "   ⏭️  Skipped (empty value)"
    fi
    echo ""
}

# Add variables
echo "─── Masked variables (secrets) ─────────────────────────────────────────"
echo "This setup requires ONE masked CI/CD variable for the GPG passphrase."
echo "All other credentials (DATAROBOT_API_TOKEN, PULUMI_ACCESS_TOKEN, LLM keys, etc.)"
echo "are stored encrypted in .env.gpg and loaded automatically by the pipeline."
echo ""

# Core variable: the GPG passphrase to decrypt .env.gpg
add_variable "CICD_SECRET_PASSPHRASE" "GPG passphrase for decrypting .env.gpg"

# GitLab API token for commenting on MRs (not in .env since it's GitLab-specific)
echo ""
echo "📝 GitLab API Token for MR comments"
echo "   Create at: https://gitlab.com/-/profile/personal_access_tokens"
echo "   Required scopes: api"
add_variable "GITLAB_API_TOKEN" "GitLab personal access token (for posting MR comments)"

# Add plain (non-masked) Pulumi stack name variables
echo ""
echo "─── Plain variables (not sensitive) ────────────────────────────────────"
echo "Pulumi stack names are not secrets — they are plain CI/CD variables."
echo ""

add_plain_variable "PULUMI_STACK_CI_NAME" \
    "Pulumi stack deployed on every merge to the default branch" \
    "ci"
add_plain_variable "PULUMI_STACK_REVIEW_NAME" \
    "Pulumi stack name prefix for MR review apps (MR IID appended automatically in the pipeline)" \
    "review"

echo ""
echo "🎉 Variables setup complete!"
echo ""
echo "View all variables:  glab variable list --repo $PROJECT"
echo "Manage in UI:        https://gitlab.com/$PROJECT/-/settings/ci_cd#js-cicd-variables-settings"
echo ""
echo "Next steps:"
echo "1. Ensure your .env.gpg is committed to the repository"
echo "2. Push your .gitlab-ci.yml to trigger pipelines"
echo "3. Test with a merge request"
