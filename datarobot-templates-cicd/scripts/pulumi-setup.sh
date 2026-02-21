#!/usr/bin/env bash
# Pulumi setup script for DataRobot Application Templates
# This script helps initialize Pulumi with different backend options

set -euo pipefail

echo "🎯 DataRobot Application Template - Pulumi Setup"
echo "=================================================="
echo ""

# Function to install Pulumi if not present
install_pulumi() {
    if ! command -v pulumi &> /dev/null; then
        echo "📦 Installing Pulumi..."
        curl -fsSL https://get.pulumi.com | sh
        export PATH="$HOME/.pulumi/bin:$PATH"
        echo "✅ Pulumi installed successfully"
    else
        echo "✅ Pulumi already installed"
    fi
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
    read -sp "Pulumi Access Token: " PULUMI_TOKEN
    echo ""
    
    export PULUMI_ACCESS_TOKEN="$PULUMI_TOKEN"
    pulumi login
    echo "✅ Logged in to Pulumi Cloud"
}

# Function to setup Azure Blob backend
setup_azure_backend() {
    echo ""
    echo "☁️  Setting up Azure Blob Storage backend"
    echo "----------------------------------------"
    read -p "Azure Storage Account: " AZURE_ACCOUNT
    read -p "Azure Container Name: " AZURE_CONTAINER
    read -sp "Azure Storage Key: " AZURE_KEY
    echo ""
    
    export AZURE_STORAGE_ACCOUNT="$AZURE_ACCOUNT"
    export AZURE_STORAGE_KEY="$AZURE_KEY"
    
    pulumi login "azblob://$AZURE_CONTAINER"
    echo "✅ Logged in to Azure Blob backend"
    
    # Add to .env if it exists
    if [ -f .env ]; then
        echo "AZURE_STORAGE_ACCOUNT=$AZURE_ACCOUNT" >> .env
        echo "AZURE_STORAGE_KEY=$AZURE_KEY" >> .env
        echo "📝 Added Azure credentials to .env file"
    fi
}

# Function to setup AWS S3 backend
setup_s3_backend() {
    echo ""
    echo "☁️  Setting up AWS S3 backend"
    echo "----------------------------"
    read -p "S3 Bucket Name: " S3_BUCKET
    read -p "AWS Access Key ID: " AWS_KEY_ID
    read -sp "AWS Secret Access Key: " AWS_SECRET
    echo ""
    
    export AWS_ACCESS_KEY_ID="$AWS_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$AWS_SECRET"
    
    pulumi login "s3://$S3_BUCKET"
    echo "✅ Logged in to S3 backend"
    
    # Add to .env if it exists
    if [ -f .env ]; then
        echo "AWS_ACCESS_KEY_ID=$AWS_KEY_ID" >> .env
        echo "AWS_SECRET_ACCESS_KEY=$AWS_SECRET" >> .env
        echo "📝 Added AWS credentials to .env file"
    fi
}

# Function to create initial stack
create_stack() {
    echo ""
    echo "📚 Creating Pulumi stack"
    echo "------------------------"
    read -p "Stack name (e.g., dev, staging, prod): " STACK_NAME
    
    pulumi stack select --create "$STACK_NAME"
    echo "✅ Created and selected stack: $STACK_NAME"
    
    echo ""
    echo "📋 Available commands:"
    echo "  pulumi up       - Deploy the stack"
    echo "  pulumi destroy  - Destroy the stack"
    echo "  pulumi stack ls - List all stacks"
    echo "  pulumi stack output - View stack outputs"
}

# Main setup flow
main() {
    install_pulumi
    
    echo ""
    echo "🔧 Choose Pulumi backend:"
    echo "1) Pulumi Cloud (recommended)"
    echo "2) Azure Blob Storage"
    echo "3) AWS S3"
    echo "4) Skip (already configured)"
    read -p "Selection [1-4]: " BACKEND_CHOICE
    
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
    
    echo ""
    echo "🎉 Pulumi setup complete!"
    echo ""
    echo "Next steps:"
    echo "1. Configure your DataRobot credentials in .env"
    echo "2. Run 'pulumi up' to deploy your application"
    echo "3. Set up CI/CD using the examples in scripts/"
}

# Run main function
main
