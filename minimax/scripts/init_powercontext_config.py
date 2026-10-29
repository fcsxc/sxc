"""生成 PowerContext 的模型无关配置（模板模式：SQLite + 基础记忆）。

``powercontext config init --template`` 需要交互式终端，在无人值守环境里
不可用；这里直接调用 PowerContext 自己的配置生成函数，产出同样的内容。

用法：python scripts/init_powercontext_config.py [目标 .env 路径]
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV = PROJECT_DIR / ".data" / "powercontext" / ".env"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ENV
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        from powercontext.cli.config import (
            collect_configuration,
            update_environment_document,
            write_environment,
        )
    except ImportError as exc:  # pragma: no cover - 依赖缺失时给出明确提示
        print(f"[error] 无法导入 powercontext：{exc}", file=sys.stderr)
        print('       请先安装：pip install "powercontext[cli,server]==1.4.1"', file=sys.stderr)
        return 1

    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    configuration = collect_configuration(advanced=False)
    content = update_environment_document(existing, configuration)
    write_environment(target, content, backup=target.exists())
    print(f"[powercontext] 配置已生成：{target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
