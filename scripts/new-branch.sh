#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <branch-name>"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RAW_NAME="$1"
SANITIZED="$(printf '%s' "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//')"

if [[ -z "$SANITIZED" ]]; then
  echo "Branch name cannot be empty after sanitizing."
  exit 1
fi

BRANCH_NAME="codex/$SANITIZED"
git checkout -b "$BRANCH_NAME"
echo "$BRANCH_NAME"
