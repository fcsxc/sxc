"""上下文模块配置。

所有路径都可以用环境变量覆盖，方便评审在干净环境中复现。
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
WORKSPACE_DIR = PROJECT_DIR / "workspace"
SPECS_DIR = WORKSPACE_DIR / "specs"
TESTS_DIR = WORKSPACE_DIR / "tests"
CODE_DIR = WORKSPACE_DIR

DATA_DIR = Path(os.environ.get("SDDCTX_DATA_DIR", str(PROJECT_DIR / ".data")))
SEEKDB_DIR = Path(os.environ.get("SDDCTX_SEEKDB_DIR", str(DATA_DIR / "seekdb")))
SEEKDB_DATABASE = os.environ.get("SDDCTX_SEEKDB_DATABASE", "sdd")

POWERCONTEXT_URL = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000")
POWERCONTEXT_SCOPE_TITLE = os.environ.get("SDDCTX_SCOPE_TITLE", "orderflow-refund-sdd")
POWERCONTEXT_TIMEOUT = float(os.environ.get("SDDCTX_HTTP_TIMEOUT", "30"))

MINIMAX_API_KEY_ENV = "MINIMAX_API_KEY"
MINIMAX_BASE_URL = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "MiniMax-Text-01")
MINIMAX_TIMEOUT = float(os.environ.get("SDDCTX_MINIMAX_TIMEOUT", "300"))

ARTIFACTS_DIR = PROJECT_DIR / "artifacts"


def ensure_data_dir() -> Path:
    """创建并返回数据目录。"""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
