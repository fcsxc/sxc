"""学记 StudyMemo — 种子数据：创建示例任务，便于评审快速体验。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import core  # noqa: E402

SAMPLES = [
    ("B+ 树索引结构与聚簇索引", "数据库", "OceanBase 大赛复习"),
    ("SQL 执行计划与索引选择", "数据库", "重点：回表与覆盖索引"),
    ("向量检索与混合检索原理", "数据库", "seekdb 相关"),
    ("Transformer 注意力机制", "算法", "论文阅读笔记"),
    ("英语六级高频词汇 List 3", "英语", "每天 30 分钟"),
]

if __name__ == "__main__":
    for title, cat, note in SAMPLES:
        t = core.add_task(title, cat, note)
        print("created:", t["id"], title)
    print("done")
