#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# 一键准备：安装依赖 -> 导入工程资料到 seekdb -> 构造开发上下文。
#
# 用法：bash start.sh
# ---------------------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR="${VENV_DIR:-$HERE/.venv}"
TASK="${TASK:-为 OrderFlow 的 orderflow.refund 模块实现 SPEC-REFUND-014：按退款原因决定运费是否可退，优惠券按 SPEC-PRICE-003 分摊，并按 SPEC-REFUND-020 把单次退款金额限制为订单实付金额的 50%。需要实现的符号是 orderflow.refund.refundable_amount。}"

if [ ! -d "$VENV_DIR" ]; then
  echo "[1/3] 创建虚拟环境：$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[2/3] 安装依赖"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo "[3/3] 导入工程资料到 seekdb 并构造上下文"
python -m sddctx.cli import
python -m sddctx.cli context --task "$TASK" --out artifacts/context-pack.md --quiet

echo
echo "完成。上下文包：artifacts/context-pack.md"
echo "下一步："
echo "  bash scripts/start_powercontext.sh            # 后台另开一个终端启动 PowerContext"
echo "  bash scripts/verify_all.py                    # 跑完整验证样例"
