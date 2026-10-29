#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 重置本地状态：删除 seekdb 索引目录与 PowerContext 本地数据。
# 重置后重新执行 start.sh 与 scripts/start_powercontext.sh 即可回到干净起点。
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

rm -rf "$HERE/.data"
echo "已重置：.data/ 已删除（seekdb 索引 + PowerContext 本地库）"
echo "重新初始化：bash start.sh && bash scripts/start_powercontext.sh"
