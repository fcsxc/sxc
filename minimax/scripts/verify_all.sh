#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 跑完整个验证样例。用法：bash scripts/verify_all.sh
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

PYTHON_BIN="${PYTHON:-python3}"
if [ -x "$HERE/.venv/bin/python" ]; then
  PYTHON_BIN="$HERE/.venv/bin/python"
fi

exec "$PYTHON_BIN" scripts/verify_all.py
