"""sddctx —— 面向软件持续演进的 SDD 上下文模块。

模块职责：
1. 把规格条目、代码符号、测试用例导入 seekdb（嵌入式 OceanBase seekdb）；
2. 根据开发任务从数据库检索出「当前有效的规格 + 相关代码 + 相关测试」；
3. 用 PowerContext 保存任务状态，模块重启后可读取并复用。

三项技术的分工见 ``minimax/docs/07-一页技术说明.md``。
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
