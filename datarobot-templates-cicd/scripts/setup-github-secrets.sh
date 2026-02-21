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
    read -p "Enter repository (owner/repo): " REPO
fi

echo "Repository: $REPO"
echo ""

# Function to add a secret
add_secret() {
    local secret_name=$1
    local secret_description=$2
    local secret_value=""
    
    echo "📝 Setting up: $secret_name"
    echo "   $secret_description"
    
    if [ "$secret_name" = "LARGE_SECRET_PASSPHRASE" ]; then
        # For GPG passphrase, offer to read from user input
        echo "   (This is your GPG encryption passphrase)"
        read -sp "   Enter value: " secret_value
        echo ""
    else
        read -sp "   Enter value: " secret_value
        echo ""
    fi
    
    if [ -n "$secret_value" ]; then
        echo "$secret_value" | gh secret set "$secret_name" --repo "$REPO"
        echo "   ✅ Added $secret_name"
    else
        echo "   ⏭️  Skipped (empty value)"
    fi
    echo ""
}

# Add secrets
echo "Add GitHub Actions secrets:"
echo "Press Enter to skip any secret"
echo ""

add_secret "LARGE_SECRET_PASSPHRASE" "GPG passphrase for decrypting .env.gpg"
add_secret "PULUMI_ACCESS_TOKEN" "Token from https://app.pulumi.com/account/tokens"
add_secret "DATAROBOT_API_TOKEN" "DataRobot API token"

# Optional secrets
read -p "Add optional secrets (LLM, cloud providers)? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    add_secret "OPENAI_API_KEY" "OpenAI API key (if using OpenAI)"
    add_secret "AZURE_STORAGE_ACCOUNT" "Azure Storage account (if using Azure Pulumi backend)"
    add_secret "AZURE_STORAGE_KEY" "Azure Storage key (if using Azure Pulumi backend)"
    add_secret "AWS_ACCESS_KEY_ID" "AWS Access Key (if using S3 Pulumi backend)"
    add_secret "AWS_SECRET_ACCESS_KEY" "AWS Secret Key (if using S3 Pulumi backend)"
fi

echo ""
echo "🎉 Secrets setup complete!"
echo ""
echo "View all secrets:"
echo "  gh secret list --repo $REPO"
echo ""
echo "Next steps:"
echo "1. Verify secrets are set correctly"
echo "2. Push your .github/workflows to trigger actions"
echo "3. Test with a pull request"
