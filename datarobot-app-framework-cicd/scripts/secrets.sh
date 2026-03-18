#!/usr/bin/env bash
# Secrets management: encrypt or decrypt .env using GPG symmetric encryption.
# Usage: secrets.sh encrypt | decrypt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOTENV="$REPO_ROOT/.env"
DOTENV_GPG="$REPO_ROOT/.env.gpg"

confirm_overwrite() {
    local file="$1"
    if [[ -f "$file" ]]; then
        read -rp "⚠️  $file already exists. Overwrite? (y/N): " reply
        [[ "${reply,,}" == "y" ]] || { echo "Aborted."; exit 0; }
    fi
}

cmd="${1:-}"

case "$cmd" in
  encrypt)
    echo "🔒 Encrypt .env → .env.gpg"
    echo "==========================="
    [[ -f "$DOTENV" ]] || { echo "❌ $DOTENV not found."; exit 1; }
    confirm_overwrite "$DOTENV_GPG"
    echo "Enter a strong passphrase (save it — you'll need it as CICD_SECRET_PASSPHRASE):"
    gpg --symmetric --cipher-algo AES256 --batch --yes --output "$DOTENV_GPG" "$DOTENV"
    echo "✅ Encrypted: $DOTENV_GPG"
    echo ""
    echo "Next steps:"
    echo "  git add .env.gpg && git commit -m 'Update encrypted secrets'"
    echo "  gh secret set CICD_SECRET_PASSPHRASE   # if not already set"
    ;;

  decrypt)
    echo "🔓 Decrypt .env.gpg → .env"
    echo "==========================="
    [[ -f "$DOTENV_GPG" ]] || { echo "❌ $DOTENV_GPG not found."; exit 1; }
    confirm_overwrite "$DOTENV"
    echo "Enter your passphrase:"
    gpg --quiet --decrypt --output "$DOTENV" "$DOTENV_GPG"
    echo "✅ Decrypted: $DOTENV"
    echo "⚠️  Never commit .env — keep it in .gitignore."
    ;;

  *)
    echo "Usage: $(basename "$0") encrypt | decrypt"
    exit 1
    ;;
esac
