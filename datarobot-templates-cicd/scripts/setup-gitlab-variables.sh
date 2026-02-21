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
    read -p "Enter project (group/project): " PROJECT
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
    
    read -sp "   Enter value: " var_value
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

# Add variables
echo "Add GitLab CI/CD variables:"
echo "Press Enter to skip any variable"
echo ""

# Core variables
add_variable "DATAROBOT_API_TOKEN" "DataRobot API token"
add_variable "PULUMI_CONFIG_PASSPHRASE" "Pulumi configuration passphrase"

# Optional: Pulumi backend
read -p "Using Pulumi DIY backend? (Azure/S3/GCS) (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Choose backend:"
    echo "1) Azure Blob Storage"
    echo "2) AWS S3"
    echo "3) Google Cloud Storage"
    read -p "Selection [1-3]: " BACKEND_CHOICE
    
    case $BACKEND_CHOICE in
        1)
            add_variable "AZURE_STORAGE_ACCOUNT" "Azure Storage account name"
            add_variable "AZURE_STORAGE_KEY" "Azure Storage account key"
            ;;
        2)
            add_variable "AWS_ACCESS_KEY_ID" "AWS Access Key ID"
            add_variable "AWS_SECRET_ACCESS_KEY" "AWS Secret Access Key"
            ;;
        3)
            add_variable "GOOGLE_CREDENTIALS" "GCP service account JSON"
            ;;
    esac
fi

# Optional: LLM keys
read -p "Add LLM API keys? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    add_variable "OPENAI_API_KEY" "OpenAI API key (if using OpenAI)"
    add_variable "OPENAI_API_BASE" "OpenAI API base URL (if using Azure OpenAI)"
fi

# GitLab API token for commenting on MRs
echo ""
echo "📝 GitLab API Token for MR comments"
echo "   Create at: https://gitlab.com/-/profile/personal_access_tokens"
echo "   Required scopes: api"
add_variable "GITLAB_API_TOKEN" "GitLab personal access token"

echo ""
echo "🎉 Variables setup complete!"
echo ""
echo "View all variables:"
echo "  glab variable list --repo $PROJECT"
echo ""
echo "Manage in UI:"
echo "  https://gitlab.com/$PROJECT/-/settings/ci_cd#js-cicd-variables-settings"
echo ""
echo "Next steps:"
echo "1. Verify variables are set correctly"
echo "2. Push your .gitlab-ci.yml to trigger pipelines"
echo "3. Test with a merge request"
