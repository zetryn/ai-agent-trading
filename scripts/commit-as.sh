#!/usr/bin/env bash
# commit-as.sh — commit + push dengan identity tertentu tanpa ubah global git config.
#
# Usage:
#   ./scripts/commit-as.sh zetryn   "feat: pesan commit"
#   ./scripts/commit-as.sh cry      "fix: pesan commit"
#   ./scripts/commit-as.sh aldirrss "chore: pesan commit"
#
# Optional: tambah remote dan branch (default: origin main)
#   ./scripts/commit-as.sh zetryn "pesan" origin main
#
# Identity yang tersedia:
#   zetryn   → name="zetryn"   email="team@zetryn.com"       remote=origin (zetryn/ai-agent-trading)
#   cry      → name="cry"      email="cry@users.noreply.github.com"
#   aldirrss → name="aldirrss" email="aldialputra@gmail.com"

set -euo pipefail

IDENTITY="${1:-}"
MESSAGE="${2:-}"
REMOTE="${3:-origin}"
BRANCH="${4:-main}"

if [[ -z "$IDENTITY" || -z "$MESSAGE" ]]; then
    echo "Usage: $0 <identity> <commit message> [remote] [branch]"
    echo "  identity: zetryn | cry | aldirrss"
    exit 1
fi

case "$IDENTITY" in
    zetryn)
        AUTHOR_NAME="zetryn"
        AUTHOR_EMAIL="team@zetryn.com"
        ;;
    cry)
        AUTHOR_NAME="cry"
        AUTHOR_EMAIL="cry@users.noreply.github.com"
        ;;
    aldirrss)
        AUTHOR_NAME="aldirrss"
        AUTHOR_EMAIL="aldialputra@gmail.com"
        ;;
    *)
        echo "Identity tidak dikenal: $IDENTITY"
        echo "Pilihan: zetryn | cry | aldirrss"
        exit 1
        ;;
esac

echo "==> Identity  : $AUTHOR_NAME <$AUTHOR_EMAIL>"
echo "==> Remote    : $REMOTE/$BRANCH"
echo "==> Message   : $MESSAGE"
echo ""

# Stage semua perubahan (atau biarkan user stage manual sebelum jalankan script)
# git add -A  ← dinonaktifkan; user stage dulu dengan 'git add' sebelum pakai script ini

GIT_AUTHOR_NAME="$AUTHOR_NAME" \
GIT_AUTHOR_EMAIL="$AUTHOR_EMAIL" \
GIT_COMMITTER_NAME="$AUTHOR_NAME" \
GIT_COMMITTER_EMAIL="$AUTHOR_EMAIL" \
git commit -m "$MESSAGE"

echo ""
echo "==> Pushing ke $REMOTE $BRANCH ..."
git push "$REMOTE" "$BRANCH"

echo ""
echo "Done. Commit oleh: $AUTHOR_NAME <$AUTHOR_EMAIL>"
