#!/usr/bin/env bash
# Manage GPG-encrypted .env secrets for local development.
#
# Usage:
#   ./secrets.sh encrypt   — encrypt .env → .env.gpg  (commit .env.gpg, never .env)
#   ./secrets.sh decrypt   — decrypt .env.gpg → .env
#
# CI decrypts inline using the CICD_SECRET_PASSPHRASE GitHub secret; this script
# is for developer convenience only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOTENV="$REPO_ROOT/.env"
DOTENV_GPG="$REPO_ROOT/.env.gpg"

# ── helpers ──────────────────────────────────────────────────────────────────

confirm_overwrite() {
    local file="$1"
    if [[ -f "$file" ]]; then
        echo "⚠️  Warning: $file already exists"
        read -rp "Overwrite? (y/N): " REPLY
        if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
            echo "Aborted"
            exit 0
        fi
    fi
}

# ── encrypt ──────────────────────────────────────────────────────────────────

cmd_encrypt() {
    echo "🔒 Encrypt .env → .env.gpg"
    echo "==========================="
    echo ""

    if [[ ! -f "$DOTENV" ]]; then
        echo "❌ Error: .env not found in project root"
        echo "Create a .env file first with your secrets."
        exit 1
    fi

    confirm_overwrite "$DOTENV_GPG"

    echo "Enter a strong passphrase for encryption:"
    echo "(Add this to GitHub Secrets as CICD_SECRET_PASSPHRASE)"
    echo ""

    gpg --symmetric --cipher-algo AES256 --output "$DOTENV_GPG" "$DOTENV"

    echo ""
    echo "✅ Encrypted .env → .env.gpg"
    echo ""
    echo "Next steps:"
    echo "  1. git add .env.gpg && git commit -m 'chore: add encrypted secrets'"
    echo "  2. Add CICD_SECRET_PASSPHRASE to GitHub repository secrets"
    echo "  3. Confirm .env is in .gitignore — never commit plaintext secrets!"
}

# ── decrypt ──────────────────────────────────────────────────────────────────

cmd_decrypt() {
    echo "🔓 Decrypt .env.gpg → .env"
    echo "==========================="
    echo ""

    if [[ ! -f "$DOTENV_GPG" ]]; then
        echo "❌ Error: .env.gpg not found in project root"
        echo "Run './secrets.sh encrypt' first."
        exit 1
    fi

    confirm_overwrite "$DOTENV"

    gpg --quiet --decrypt --output "$DOTENV" "$DOTENV_GPG"

    echo ""
    echo "✅ Decrypted .env.gpg → .env"
    echo ""
    echo "⚠️  Remember: never commit .env to git!"
}

# ── entry point ───────────────────────────────────────────────────────────────

case "${1:-}" in
    encrypt) cmd_encrypt ;;
    decrypt) cmd_decrypt ;;
    *)
        echo "Usage: $0 {encrypt|decrypt}"
        echo ""
        echo "  encrypt   Encrypt .env → .env.gpg for committing to the repo"
        echo "  decrypt   Decrypt .env.gpg → .env for local development"
        exit 1
        ;;
esac
