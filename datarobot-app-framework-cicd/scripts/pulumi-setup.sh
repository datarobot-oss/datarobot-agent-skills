#!/usr/bin/env bash
# Pulumi setup script for DataRobot Application Templates
# This script helps initialize Pulumi with different backend options

set -euo pipefail

# Resolve the repo root (script lives at repo_root/infra/scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOTENV="$REPO_ROOT/.env"

echo "🎯 DataRobot Application Template - Pulumi Setup"
echo "=================================================="
echo ""

# Detect existing stacks on a different backend and offer to migrate them.
# Must be called AFTER exporting any required cloud credentials to the environment
# but BEFORE calling `pulumi login` for the new backend.
migrate_stacks_if_needed() {
    local target_backend_url="$1"

    # Get the current backend URL from `pulumi whoami --verbose`
    local current_backend
    current_backend=$(pulumi whoami --verbose 2>/dev/null | grep "Backend URL:" | awk '{print $3}' || true)

    # Nothing to do if Pulumi isn't logged in or backend is already the target
    [[ -z "$current_backend" || "$current_backend" == "$target_backend_url" ]] && return 0

    # Collect Pulumi.<stackname>.yaml stack config files (skip the root Pulumi.yaml)
    local stack_files=()
    while IFS= read -r -d '' f; do
        stack_files+=("$f")
    done < <(find . -maxdepth 1 -name "Pulumi.*.yaml" -not -name "Pulumi.yaml" -print0 2>/dev/null)

    # No local stacks — nothing to migrate
    [[ ${#stack_files[@]} -eq 0 ]] && return 0

    echo ""
    echo "⚠️  Existing Pulumi stacks detected on a different backend"
    echo "   Current backend : $current_backend"
    echo "   Target backend  : $target_backend_url"
    echo ""
    echo "   Stacks found:"
    for f in "${stack_files[@]}"; do
        local sname
        sname=$(basename "$f" .yaml | sed 's/^Pulumi\.//')
        echo "     - $sname"
    done
    echo ""
    read -rp "Migrate these stacks to the new backend? [y/N]: " MIGRATE_CHOICE

    if [[ "$MIGRATE_CHOICE" != "y" && "$MIGRATE_CHOICE" != "Y" ]]; then
        echo "⏭️  Skipping stack migration"
        return 0
    fi

    # Export all stacks while still logged into the old backend
    local tmpdir
    tmpdir=$(mktemp -d)
    local stack_names=()

    for f in "${stack_files[@]}"; do
        local stack_name
        stack_name=$(basename "$f" .yaml | sed 's/^Pulumi\.//')
        stack_names+=("$stack_name")
        echo "   📤 Exporting stack '$stack_name' from $current_backend..."
        pulumi stack export --stack "$stack_name" --file "$tmpdir/$stack_name.json"
    done

    # Login to the new backend (cloud credentials must already be in the environment)
    pulumi login "$target_backend_url"

    # Import each stack into the new backend
    for stack_name in "${stack_names[@]}"; do
        echo "   📥 Importing stack '$stack_name' into $target_backend_url..."
        pulumi stack select --create "$stack_name"
        pulumi stack import --file "$tmpdir/$stack_name.json"
        echo "   ✅ Migrated stack: $stack_name"
    done

    rm -rf "$tmpdir"
    echo ""
    echo "✅ Stack migration complete"
}

# Function to setup Pulumi Cloud backend
setup_pulumi_cloud() {
    echo ""
    echo "🌐 Setting up Pulumi Cloud backend"
    echo "-----------------------------------"
    echo "1. Go to https://app.pulumi.com/account/tokens"
    echo "2. Create a new access token"
    echo "3. Enter the token below"
    echo ""
    local token_hint=""
    [[ -n "${PULUMI_ACCESS_TOKEN:-}" ]] && token_hint=" [already set, press Enter to keep]"
    read -rsp "Pulumi Access Token${token_hint}: " PULUMI_TOKEN
    echo ""
    PULUMI_TOKEN="${PULUMI_TOKEN:-${PULUMI_ACCESS_TOKEN:-}}"

    export PULUMI_ACCESS_TOKEN="$PULUMI_TOKEN"
    migrate_stacks_if_needed "https://api.pulumi.com"
    pulumi login
    echo "✅ Logged in to Pulumi Cloud"
}

# Function to setup Azure Blob backend
setup_azure_backend() {
    echo ""
    echo "☁️  Setting up Azure Blob Storage backend"
    echo "----------------------------------------"
    local acct_default="${AZURE_STORAGE_ACCOUNT:-}"
    local acct_hint=""
    [[ -n "$acct_default" ]] && acct_hint=" [$acct_default]"
    read -rp "Azure Storage Account${acct_hint}: " AZURE_ACCOUNT
    AZURE_ACCOUNT="${AZURE_ACCOUNT:-$acct_default}"

    read -rp "Azure Container Name: " AZURE_CONTAINER

    local key_hint=""
    [[ -n "${AZURE_STORAGE_KEY:-}" ]] && key_hint=" [already set, press Enter to keep]"
    read -rsp "Azure Storage Key${key_hint}: " AZURE_KEY
    echo ""
    AZURE_KEY="${AZURE_KEY:-${AZURE_STORAGE_KEY:-}}"

    export AZURE_STORAGE_ACCOUNT="$AZURE_ACCOUNT"
    export AZURE_STORAGE_KEY="$AZURE_KEY"

    migrate_stacks_if_needed "azblob://$AZURE_CONTAINER"
    pulumi login "azblob://$AZURE_CONTAINER"
    echo "✅ Logged in to Azure Blob backend"

    # Add to .env if it exists
    if [[ -f "$DOTENV" ]]; then
        echo "AZURE_STORAGE_ACCOUNT=$AZURE_ACCOUNT" >> "$DOTENV"
        echo "AZURE_STORAGE_KEY=$AZURE_KEY" >> "$DOTENV"
        echo "📝 Added Azure credentials to $DOTENV"
    fi
}

# Function to setup AWS S3 backend
setup_s3_backend() {
    echo ""
    echo "☁️  Setting up AWS S3 backend"
    echo "----------------------------"
    read -rp "S3 Bucket Name: " S3_BUCKET

    local aws_key_default="${AWS_ACCESS_KEY_ID:-}"
    local aws_key_hint=""
    [[ -n "$aws_key_default" ]] && aws_key_hint=" [$aws_key_default]"
    read -rp "AWS Access Key ID${aws_key_hint}: " AWS_KEY_ID
    AWS_KEY_ID="${AWS_KEY_ID:-$aws_key_default}"

    local aws_secret_hint=""
    [[ -n "${AWS_SECRET_ACCESS_KEY:-}" ]] && aws_secret_hint=" [already set, press Enter to keep]"
    read -rsp "AWS Secret Access Key${aws_secret_hint}: " AWS_SECRET
    echo ""
    AWS_SECRET="${AWS_SECRET:-${AWS_SECRET_ACCESS_KEY:-}}"

    export AWS_ACCESS_KEY_ID="$AWS_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$AWS_SECRET"

    migrate_stacks_if_needed "s3://$S3_BUCKET"
    pulumi login "s3://$S3_BUCKET"
    echo "✅ Logged in to S3 backend"

    # Add to .env if it exists
    if [[ -f "$DOTENV" ]]; then
        echo "AWS_ACCESS_KEY_ID=$AWS_KEY_ID" >> "$DOTENV"
        echo "AWS_SECRET_ACCESS_KEY=$AWS_SECRET" >> "$DOTENV"
        echo "📝 Added AWS credentials to $DOTENV"
    fi
}

# Function to create initial stack
create_stack() {
    echo ""
    echo "📚 Creating Pulumi stack"
    echo "------------------------"

    # List stacks already in the current backend
    local existing_stacks
    existing_stacks=$(pulumi stack ls --json 2>/dev/null \
        | python3 -c "import sys,json; [print(s['name']) for s in json.load(sys.stdin)]" 2>/dev/null \
        || true)

    if [[ -n "$existing_stacks" ]]; then
        echo "Existing stacks in current backend:"
        while IFS= read -r s; do
            echo "  - $s"
        done <<< "$existing_stacks"
        echo ""
    fi

    read -rp "Stack name (e.g., dev, staging, prod): " STACK_NAME

    # If the name already exists in the current backend, offer to just select it
    if echo "$existing_stacks" | grep -qx "$STACK_NAME" 2>/dev/null; then
        echo ""
        echo "✅ Stack '$STACK_NAME' found in the current backend"
        read -rp "Select and use it? [Y/n]: " USE_EXISTING
        if [[ "$USE_EXISTING" != "n" && "$USE_EXISTING" != "N" ]]; then
            pulumi stack select "$STACK_NAME"
            echo "✅ Selected existing stack: $STACK_NAME"
            return 0
        fi
    fi

    # Check for a local Pulumi.<name>.yaml that doesn't exist in the current backend yet
    local stack_config="Pulumi.${STACK_NAME}.yaml"
    if [[ -f "$stack_config" ]] && ! echo "$existing_stacks" | grep -qx "$STACK_NAME" 2>/dev/null; then
        echo ""
        echo "📄 Found local stack config '$stack_config' but no matching stack in the current backend"
        read -rp "Import an exported stack state file into the current backend? [y/N]: " IMPORT_CHOICE
        if [[ "$IMPORT_CHOICE" == "y" || "$IMPORT_CHOICE" == "Y" ]]; then
            read -rp "Path to exported state JSON file: " STATE_FILE
            if [[ -n "$STATE_FILE" && -f "$STATE_FILE" ]]; then
                pulumi stack select --create "$STACK_NAME"
                pulumi stack import --file "$STATE_FILE"
                echo "✅ Imported stack '$STACK_NAME' into current backend"
                return 0
            else
                echo "⚠️  State file not found — creating a fresh stack instead"
            fi
        fi
    fi

    pulumi stack select --create "$STACK_NAME"
    echo "✅ Created and selected stack: $STACK_NAME"

    echo ""
    echo "📋 Available commands:"
    echo "  pulumi up          - Deploy the stack"
    echo "  pulumi destroy     - Destroy the stack"
    echo "  pulumi stack ls    - List all stacks"
    echo "  pulumi stack output - View stack outputs"
}

# Configure CI/CD secrets and variables by running the appropriate setup script.
setup_cicd() {
    echo ""
    echo "🔐 Configure CI/CD secrets and variables"
    echo "-----------------------------------------"
    echo "1) GitHub Actions"
    echo "2) GitLab CI/CD"
    echo "3) Skip"
    read -rp "Selection [1-3]: " CICD_CHOICE

    case $CICD_CHOICE in
        1)
            bash "$SCRIPT_DIR/setup-github-secrets.sh"
            ;;
        2)
            bash "$SCRIPT_DIR/setup-gitlab-variables.sh"
            ;;
        3)
            echo "⏭️  Skipping — run setup-github-secrets.sh or setup-gitlab-variables.sh manually"
            ;;
        *)
            echo "❌ Invalid selection"
            ;;
    esac
}

# Main setup flow
main() {
    # Source .env so existing vars are available as defaults throughout setup
    if [[ -f "$DOTENV" ]]; then
        set -a
        # shellcheck source=/dev/null
        source "$DOTENV"
        set +a
    fi

    if ! command -v pulumi &> /dev/null; then
        echo "❌ Pulumi is not installed. Install it from https://www.pulumi.com/docs/install/ and re-run this script."
        exit 1
    fi

    echo ""
    echo "🔧 Choose Pulumi backend:"
    echo "1) Pulumi Cloud (recommended)"
    echo "2) Azure Blob Storage"
    echo "3) AWS S3"
    echo "4) Skip (already configured)"
    read -rp "Selection [1-4]: " BACKEND_CHOICE

    case $BACKEND_CHOICE in
        1)
            setup_pulumi_cloud
            ;;
        2)
            setup_azure_backend
            ;;
        3)
            setup_s3_backend
            ;;
        4)
            echo "⏭️  Skipping backend setup"
            ;;
        *)
            echo "❌ Invalid selection"
            exit 1
            ;;
    esac

    create_stack
    setup_cicd

    echo ""
    echo "🎉 Pulumi setup complete!"
    echo ""
    echo "Next steps:"
    echo "1. Run 'pulumi up' to deploy your application"
    echo "2. Push .env.gpg and your CI/CD workflow files to trigger your first pipeline"
}

# Run main function
main
