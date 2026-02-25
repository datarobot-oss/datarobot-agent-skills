#!/usr/bin/env bash
# GPG decryption script for .env files
# Used for local development and testing CI/CD workflows

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🔓 Decrypt .env.gpg file"
echo "========================"
echo ""

if [ ! -f "$REPO_ROOT/.env.gpg" ]; then
    echo "❌ Error: .env.gpg file not found in project root"
    echo "Run ./encrypt-secrets.sh first to create it"
    exit 1
fi

if [ -f "$REPO_ROOT/.env" ]; then
    echo "⚠️  Warning: .env already exists"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted"
        exit 0
    fi
fi

echo "Enter your encryption passphrase:"
gpg --quiet --batch --yes --decrypt --output "$REPO_ROOT/.env" "$REPO_ROOT/.env.gpg"

if [ -f "$REPO_ROOT/.env" ]; then
    echo ""
    echo "✅ Successfully decrypted .env.gpg → .env"
    echo ""
    echo "⚠️  Remember: Never commit .env to git!"
    echo "   Make sure .env is in your .gitignore"
else
    echo "❌ Error: Decryption failed"
    echo "Check your passphrase and try again"
    exit 1
fi
