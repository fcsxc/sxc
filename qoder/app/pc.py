"""学记 StudyMemo — PowerContext 记忆客户端。

通过 PowerContext 1.4.1 HTTP API 读写「学习档案」记忆：
- 目标 (goal)
- 薄弱知识点 (weak_point)
- 偏好 (preference)
- 里程碑 (milestone)

这些记忆跨会话、跨重启持久化，是复习计划排序和周报生成的数据来源。

对接端点（已在本项目开发环境实测）：
- POST /v1/scopes                创建/复用应用 Scope（幂等键 studymemo-v1）
- POST /v1/memory/remember       写入一条记忆
- POST /v1/memory/entries/list   召回 Scope 内活跃记忆
- POST /v1/context/prepare       按查询召回 PreparedContext
- GET  /health/ready             健康检查
"""
import json
import os
import urllib.error
import urllib.request

PC_BASE_URL = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000")
SCOPE_ID = os.environ.get("STUDYMEMO_SCOPE_ID", "")

HEADERS = {"Content-Type": "application/json"}


class PowerContextError(RuntimeError):
    pass


def _req(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{PC_BASE_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise PowerContextError(f"PowerContext {method} {path} -> {e.code}: {detail}") from e
    except Exception as e:  # 网络/解析错误统一包装
        raise PowerContextError(f"PowerContext {method} {path} 失败: {e}") from e


def ensure_scope() -> str:
    """获取（或创建）本应用专用的 Scope（幂等键冲突时按标题复用已有 Scope）。"""
    global SCOPE_ID
    if SCOPE_ID:
        return SCOPE_ID
    try:
        res = _req("POST", "/v1/scopes", {
            "title": "studymemo",
            "summary": "学记 StudyMemo 学习档案",
            "idempotency_key": "studymemo-v1",
        })
        sid = res.get("scope_id")
    except PowerContextError as e:
        # 幂等键已存在但参数不同（409）：按标题复用已有 Scope
        if "scope_idempotency_conflict" not in str(e):
            raise
        items = _req("GET", "/v1/scopes").get("items") or []
        sid = next((it["scope_id"] for it in items if it.get("title") == "studymemo"), None)
    if not sid:
        raise PowerContextError("创建/复用 scope 失败")
    SCOPE_ID = sid
    return sid


def recall_memories() -> list[dict]:
    """召回当前档案中的全部活跃记忆。"""
    scope_id = ensure_scope()
    res = _req("POST", "/v1/memory/entries/list", {"scope_id": scope_id})
    return res.get("entries") or []


def write_memory(kind: str, content: str, reason: str = "学记应用写入") -> dict:
    """写入一条学习档案记忆（相同 kind+text 已存在时幂等跳过）。"""
    scope_id = ensure_scope()
    for it in recall_memories():
        if it.get("kind") == kind and it.get("text") == content:
            return {"existed": True, "entry": it, "scope_id": scope_id}
    res = _req("POST", "/v1/memory/remember", {
        "scope_id": scope_id,
        "kind": kind,
        "text": content,
        "reason": reason,
    })
    return {"existed": False, "response": res, "scope_id": scope_id}


def recall_prepared_context(query: str) -> dict:
    """按查询召回 PreparedContext（带字节预算的活跃记忆选集）。"""
    scope_id = ensure_scope()
    return _req("POST", "/v1/context/prepare", {
        "scope_id": scope_id,
        "query": query,
    })


def profile_snapshot() -> dict:
    """把召回的记忆整理成结构化档案，供页面展示与逻辑使用。"""
    profile = {"goals": [], "weak_points": [], "preferences": [], "milestones": []}
    for it in recall_memories():
        kind = it.get("kind", "")
        text = it.get("text", "")
        artifact = it.get("artifact") or {}
        kind_map = {
            "goal": "goals",
            "weak_point": "weak_points",
            "preference": "preferences",
            "milestone": "milestones",
        }
        bucket = kind_map.get(kind, "milestones")
        profile[bucket].append({
            "text": text,
            "artifact_id": artifact.get("artifact_id", ""),
            "revision": artifact.get("revision", ""),
            "state": it.get("state", "active"),
        })
    return profile


def health() -> dict:
    try:
        res = _req("GET", "/health/ready")
        return {"ok": True, "detail": res}
    except PowerContextError as e:
        return {"ok": False, "detail": str(e)}


if __name__ == "__main__":
    print("health:", health())
    print("scope:", ensure_scope())
    print("memories:", recall_memories())
