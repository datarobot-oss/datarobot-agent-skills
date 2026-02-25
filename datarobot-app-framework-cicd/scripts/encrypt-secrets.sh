#!/usr/bin/env bash
# GPG encryption script for .env files
# Used for GitHub Actions secrets management
# See: https://docs.github.com/en/actions/security-for-github-actions/using-encrypted-secrets

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🔒 Encrypt .env file with GPG"
echo "=============================="
echo ""

if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "❌ Error: .env file not found in project root"
    echo "Create a .env file in the project root first with your secrets"
    exit 1
fi

if [ -f "$REPO_ROOT/.env.gpg" ]; then
    echo "⚠️  Warning: .env.gpg already exists"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted"
        exit 0
    fi
fi

echo "Enter a strong passphrase for encryption:"
echo "(You'll need to add this to GitHub Secrets as CICD_SECRET_PASSPHRASE)"
echo ""

gpg --symmetric --cipher-algo AES256 --output "$REPO_ROOT/.env.gpg" "$REPO_ROOT/.env"

if [ -f "$REPO_ROOT/.env.gpg" ]; then
    echo ""
    echo "✅ Successfully encrypted .env → .env.gpg"
    echo ""
    echo "Next steps:"
    echo "1. Add .env.gpg to git:"
    echo "   git add .env.gpg"
    echo "   git commit -m 'Add encrypted secrets'"
    echo ""
    echo "2. Add the passphrase to GitHub:"
    echo "   - Go to Settings → Secrets and variables → Actions"
    echo "   - Create new secret: CICD_SECRET_PASSPHRASE"
    echo "   - Paste your passphrase as the value"
    echo ""
    echo "3. Ensure .env is in .gitignore (never commit plaintext secrets!)"
    echo ""
    echo "⚠️  IMPORTANT: Store your passphrase securely!"
    echo "   If you lose it, you'll need to re-encrypt with a new passphrase."
else
    echo "❌ Error: Encryption failed"
    exit 1
fi

