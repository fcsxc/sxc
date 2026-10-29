#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 启动 PowerContext Server（模板模式：SQLite + 基础记忆，不需要模型 API Key）。
#
# 用法：bash scripts/start_powercontext.sh
# 停止：在前台进程按 Ctrl+C，或 kill 该 PID。
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

CONFIG_DIR="${POWERCONTEXT_CONFIG_DIR:-$HERE/.data/powercontext}"
ENV_FILE="$CONFIG_DIR/.env"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "[powercontext] 首次启动，生成配置：$ENV_FILE"
  if ! command -v powercontext >/dev/null 2>&1; then
    echo "[powercontext] 未找到 powercontext 命令，请先安装：" >&2
    echo "  pip install \"powercontext[cli,server]==1.4.1\"" >&2
    exit 1
  fi
  powercontext config init --template --language zh --output "$ENV_FILE" || {
    echo "[powercontext] config init 失败，尝试非交互模式" >&2
    printf 'y\n' | powercontext config init --template --language zh --output "$ENV_FILE"
  }
fi

export POWERCONTEXT_URL="${POWERCONTEXT_URL:-http://127.0.0.1:8000}"
echo "[powercontext] 启动服务：$POWERCONTEXT_URL"
exec powercontext server run --env-file "$ENV_FILE"
