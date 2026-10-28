#!/usr/bin/env bash
# 学记 StudyMemo 一键启动（Linux / macOS）
# 1) 准备 PowerContext 配置（SQLite + 基础记忆，无需模型 API）
# 2) 启动 PowerContext Server（后台，端口 8000）
# 3) 启动学记 Flask 应用（端口 5000）
set -euo pipefail
cd "$(dirname "$0")"

PC_PORT="${PC_PORT:-8000}"
APP_PORT="${APP_PORT:-5000}"
CONFIG_DIR="${CONFIG_DIR:-powercontext-config}"

mkdir -p "$CONFIG_DIR"
ENV_FILE="$CONFIG_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "== 生成 PowerContext 配置（模板模式：SQLite + 基础记忆，无需模型 API） =="
  echo Y | powercontext config init --template --language zh --output "$ENV_FILE"
fi

echo "== 启动 PowerContext Server（端口 $PC_PORT） =="
if ss -ltn 2>/dev/null | grep -q ":$PC_PORT " || lsof -i :$PC_PORT >/dev/null 2>&1; then
  echo "PowerContext 已在运行"
else
  (cd "$CONFIG_DIR" && nohup powercontext server run --env-file .env > powercontext.log 2>&1 &)
  sleep 8
  echo "PowerContext 已后台启动，日志：$CONFIG_DIR/powercontext.log"
fi

echo "== 启动学记应用（端口 $APP_PORT） =="
export POWERCONTEXT_URL="http://127.0.0.1:$PC_PORT"
export PORT="$APP_PORT"
python3 -m app.main
