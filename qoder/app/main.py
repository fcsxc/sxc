"""学记 StudyMemo — Flask 入口与路由。"""
import os

from flask import Flask, jsonify, redirect, render_template, request, url_for

from . import core, pc

app = Flask(__name__)

# 把任务标题与档案里的薄弱点做简单匹配，用于「薄弱点优先」排序
WEAK_HINT = ("错", "难", "薄弱", "不懂", "混淆")


def _sort_by_weakness(tasks: list[dict]) -> list[dict]:
    try:
        weak_texts = " ".join(w["text"] for w in pc.profile_snapshot()["weak_points"])
    except pc.PowerContextError:
        weak_texts = ""
    def rank(t):
        title = t["title"]
        if any(k in title for k in WEAK_HINT) or (weak_texts and title in weak_texts):
            return (0, -t["due_days_ago"])
        return (1, -t["due_days_ago"])
    return sorted(tasks, key=rank)


@app.route("/")
def index():
    profile = {}
    pc_ok = True
    try:
        profile = pc.profile_snapshot()
    except pc.PowerContextError as e:
        pc_ok = False
        profile = {"error": str(e)}
    due = _sort_by_weakness(core.today_plan())
    tasks = core.load_tasks()
    return render_template(
        "index.html",
        profile=profile, pc_ok=pc_ok,
        due=due, tasks=tasks,
        total_reviews=len(core.week_log()),
    )


@app.route("/tasks", methods=["POST"])
def add_task():
    title = (request.form.get("title") or "").strip()
    category = (request.form.get("category") or "通用").strip()
    note = (request.form.get("note") or "").strip()
    if not title:
        return redirect(url_for("index"))
    core.add_task(title, category, note)
    return redirect(url_for("index"))


@app.route("/review/<task_id>", methods=["POST"])
def review(task_id):
    quality = request.form.get("quality", "good")
    try:
        t = core.record_review(task_id, quality)
        if quality == "again":
            # 打卡「又忘了」时，把薄弱点写进 PowerContext 档案
            pc.write_memory("weak_point", t["title"], f"复习打卡质量=again（分类：{t['category']}）")
    except KeyError:
        pass
    return redirect(url_for("index"))


@app.route("/profile", methods=["POST"])
def profile():
    """手动维护学习档案（写入 PowerContext 记忆）。"""
    kind = request.form.get("kind", "goal")
    text = (request.form.get("text") or "").strip()
    if text:
        try:
            pc.write_memory(kind, text, "用户通过页面手动写入档案")
        except pc.PowerContextError:
            pass
    return redirect(url_for("index"))


@app.route("/report")
def report():
    profile = {}
    try:
        profile = pc.profile_snapshot()
    except pc.PowerContextError:
        profile = {}
    markdown = core.weekly_report(profile)
    return render_template("report.html", markdown=markdown)


@app.route("/healthz")
def healthz():
    return jsonify({"app": "ok", "powercontext": pc.health()["ok"]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
