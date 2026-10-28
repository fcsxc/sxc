"""学记 StudyMemo — 核心业务：复习计划（艾宾浩斯遗忘曲线）与周报生成。"""
import datetime as dt
import json
import os
import uuid
from pathlib import Path

DATA_DIR = Path(os.environ.get("STUDYMEMO_DATA_DIR", Path(__file__).resolve().parent / "data"))
TASKS_FILE = DATA_DIR / "tasks.json"
LOG_FILE = DATA_DIR / "study_log.jsonl"

# 艾宾浩斯复习间隔（天）：学后第 1、2、4、7、15、30 天复习
INTERVALS = [1, 2, 4, 7, 15, 30]


def _today() -> str:
    return dt.date.today().isoformat()


def load_tasks() -> list[dict]:
    if not TASKS_FILE.exists():
        return []
    return json.loads(TASKS_FILE.read_text("utf-8"))


def save_tasks(tasks: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), "utf-8")


def add_task(title: str, category: str, note: str = "") -> dict:
    tasks = load_tasks()
    task = {
        "id": f"t{uuid.uuid4().hex[:12]}",
        "title": title,
        "category": category,
        "note": note,
        "created": _today(),
        "reviews": [],       # 每次复习的日期
        "stage": 0,          # 当前处于第几个复习间隔
        "mastered": False,
    }
    tasks.append(task)
    save_tasks(tasks)
    return task


def record_review(task_id: str, quality: str) -> dict:
    """打卡一次复习。quality: good / again（掌握 / 又忘了）。"""
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["reviews"].append({"date": _today(), "quality": quality})
            if quality == "good":
                if t["stage"] < len(INTERVALS) - 1:
                    t["stage"] += 1
                else:
                    t["mastered"] = True
            else:
                t["stage"] = 0  # 遗忘则回到第一个间隔
            save_tasks(tasks)
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": dt.datetime.now().isoformat(timespec="seconds"),
                    "task_id": task_id,
                    "title": t["title"],
                    "quality": quality,
                }, ensure_ascii=False) + "\n")
            return t
    raise KeyError(task_id)


def today_plan() -> list[dict]:
    """今日应复习清单：按遗忘曲线到期 + 薄弱点优先（由调用方排序）。"""
    today = dt.date.fromisoformat(_today())
    due = []
    for t in load_tasks():
        if t["mastered"] or not t["reviews"]:
            continue
        last = dt.date.fromisoformat(t["reviews"][-1]["date"])
        interval = INTERVALS[t["stage"]]
        next_due = last + dt.timedelta(days=interval)
        overdue = (today - next_due).days
        if overdue >= 0:
            due.append({**t, "due_days_ago": overdue})
    return due


def week_log(start: dt.date | None = None) -> list[dict]:
    """本周（或指定周）的打卡记录。"""
    if start is None:
        start = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
    rows = []
    if LOG_FILE.exists():
        for line in LOG_FILE.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            day = dt.date.fromisoformat(row["ts"][:10])
            if start <= day < start + dt.timedelta(days=7):
                rows.append(row)
    return rows


def weekly_report(profile: dict) -> str:
    """基于本周打卡 + PowerContext 档案生成周报（纯模板，无模型依赖）。"""
    rows = week_log()
    total = len(rows)
    good = sum(1 for r in rows if r["quality"] == "good")
    again = total - good
    titles = sorted({r["title"] for r in rows})
    goals = [g["text"] for g in profile.get("goals", [])]
    weak = [w["text"] for w in profile.get("weak_points", [])]
    prefs = [p["text"] for p in profile.get("preferences", [])]

    lines = [f"# 学记周报（{_today()} 所在周）", ""]
    lines.append(f"- 本周复习打卡 {total} 次：掌握 {good} 次，需重学 {again} 次。")
    if titles:
        lines.append("- 覆盖内容：" + "、".join(titles) + "。")
    else:
        lines.append("- 本周暂无打卡记录，记得按计划复习。")
    if goals:
        lines.append("")
        lines.append("## 对照目标（来自 PowerContext 档案）")
        for g in goals:
            lines.append(f"- {g}")
    if weak:
        lines.append("")
        lines.append("## 薄弱点提醒（来自 PowerContext 档案）")
        for w in weak:
            lines.append(f"- 仍需巩固：{w}")
    if prefs:
        lines.append("")
        lines.append("## 你的偏好（来自 PowerContext 档案）")
        for p in prefs:
            lines.append(f"- {p}")
    return "\n".join(lines)
