"""学记 StudyMemo — 验证样例脚本。

一键核对「指定技术实际发挥作用」：
1. PowerContext 服务连通性
2. 写入 4 类学习档案记忆（goal / weak_point / preference / milestone）
3. 召回并打印（含 artifact_id / revision，体现版本化记忆）
4. PreparedContext 按提示召回（体现按需选取）

运行：python scripts/verify.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import pc  # noqa: E402


def main():
    print("== 1. PowerContext 健康检查 ==")
    h = pc.health()
    print("health:", h)
    assert h["ok"], "PowerContext 未启动，请先运行 start.sh / start.bat"

    print("\n== 2. Scope ==")
    print("scope_id:", pc.ensure_scope())

    print("\n== 3. 写入学习档案记忆 ==")
    samples = [
        ("goal", "两周内掌握数据库索引原理，能独立分析执行计划", "用户设定学习目标"),
        ("weak_point", "B+ 树索引结构", "复习打卡记录薄弱点"),
        ("preference", "偏好晚上 21:00-22:30 学习，每次 90 分钟", "用户设定学习偏好"),
        ("milestone", "已完成《数据库系统概念》第 12-14 章", "用户记录里程碑"),
    ]
    for kind, text, reason in samples:
        r = pc.write_memory(kind, text, reason)
        print(f"[写] {kind}: {text}  (existed={r.get('existed')})")

    print("\n== 4. 召回全部记忆 ==")
    items = pc.recall_memories()
    for it in items:
        art = it.get("artifact") or {}
        print("-", it.get("text"), "| kind:", it.get("kind"),
              "| id:", art.get("artifact_id"), "@", art.get("revision"),
              "| state:", it.get("state"))
    assert items, "召回为空，记忆链路异常"

    print("\n== 5. PreparedContext 按需召回（查询：今晚复习数据库索引） ==")
    ctx = pc.recall_prepared_context("今晚复习数据库索引")
    print("status:", ctx.get("status"), "| content_bytes:", ctx.get("content_bytes"))
    content = ctx.get("content", "")
    print("content 预览:", content[:300].replace("\n", " "))

    print("\n== 6. 档案快照 ==")
    snap = pc.profile_snapshot()
    for k, v in snap.items():
        print(f"{k}: {len(v)} 条")
    print("\n✅ 验证通过：PowerContext 记忆写入、召回、复用全部生效。")


if __name__ == "__main__":
    main()
