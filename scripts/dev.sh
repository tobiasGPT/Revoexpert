#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_PYTHON="$ROOT_DIR/.venv/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
  exec "$VENV_PYTHON" ffmpeg_editor.py
else
  exec python3 ffmpeg_editor.py
fi
