"""PowerContext 任务状态存储。

任务状态（已完成、待办、已有验证结果）以 Memory 条目形式写入 PowerContext，
模块重启后可以重新读取并用于后续上下文构造。

使用的 HTTP 接口（PowerContext 1.4.1）：
- ``POST /v1/scopes``                创建 / 复用 Scope
- ``POST /v1/memory/remember``       写入一条任务状态
- ``POST /v1/memory/entries/list``   读回任务状态
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from . import config
from .models import TaskState

STATE_KIND = "sdd-task-state"


def _slug(value: str) -> str:
    """把任意标题转成幂等键用的短标识。"""

    import hashlib

    cleaned = "".join(char if char.isalnum() else "-" for char in value.lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:40]}-{digest}"


class PowerContextError(RuntimeError):
    """PowerContext 不可用或返回异常。"""


class PowerContextStateStore:
    """基于 PowerContext HTTP API 的任务状态存储。"""

    def __init__(
        self,
        base_url: str | None = None,
        scope_title: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or config.POWERCONTEXT_URL).rstrip("/")
        self.scope_title = scope_title or config.POWERCONTEXT_SCOPE_TITLE
        self.timeout = timeout or config.POWERCONTEXT_TIMEOUT
        self._scope_id: str | None = None

    # ------------------------------------------------------------------ HTTP
    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise PowerContextError(f"{method} {url} -> HTTP {exc.code}: {detail[:400]}") from exc
        except urllib.error.URLError as exc:
            raise PowerContextError(
                f"{method} {url} -> 无法连接 PowerContext（{exc.reason}）。"
                "请先启动服务：scripts/start_powercontext.sh"
            ) from exc
        if not body.strip():
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"raw": body}

    # ------------------------------------------------------------------ Scope
    def scope_id(self) -> str:
        """取得（必要时创建）Scope ID。"""

        if self._scope_id:
            return self._scope_id
        existing = self._find_scope()
        if existing:
            self._scope_id = existing
            return existing
        response = self._request(
            "POST",
            "/v1/scopes",
            {
                "title": self.scope_title,
                "summary": "OrderFlow 退款额度任务：SDD 上下文与任务状态",
                "idempotency_key": f"sddctx-scope-{_slug(self.scope_title)}",
            },
        )
        scope_id = response.get("scope_id") if isinstance(response, dict) else None
        if not scope_id:
            raise PowerContextError(f"创建 Scope 失败，响应：{str(response)[:300]}")
        self._scope_id = scope_id
        return scope_id

    def _find_scope(self) -> str | None:
        try:
            response = self._request("GET", "/v1/scopes")
        except PowerContextError:
            return None
        items = response.get("items", []) if isinstance(response, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("title") == self.scope_title:
                return item.get("scope_id")
        return None

    # ------------------------------------------------------------------ 状态
    def save(self, state: TaskState) -> dict[str, Any]:
        """写入任务状态。"""

        scope_id = self.scope_id()
        response = self._request(
            "POST",
            "/v1/memory/remember",
            {
                "scope_id": scope_id,
                "kind": STATE_KIND,
                "text": state.to_json(),
                "reason": "SDD 任务状态",
            },
        )
        return response if isinstance(response, dict) else {}

    def entries(self) -> list[dict[str, Any]]:
        """列出 Scope 下的全部 Memory 条目。"""

        scope_id = self.scope_id()
        response = self._request("POST", "/v1/memory/entries/list", {"scope_id": scope_id})
        if not isinstance(response, dict):
            return []
        entries = response.get("entries") or []
        return [entry for entry in entries if isinstance(entry, dict)]

    def load(self) -> TaskState | None:
        """读回最近一次写入的任务状态。"""

        entries = self.entries()
        candidates = [entry for entry in entries if entry.get("kind") == STATE_KIND]
        for entry in reversed(candidates):
            text = entry.get("text")
            if not text:
                continue
            try:
                return TaskState.from_json(text)
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def health(self) -> dict[str, Any]:
        """探测 PowerContext 是否可用。"""

        try:
            response = self._request("GET", "/v1/ready")
        except PowerContextError:
            response = {"status": "unreachable"}
        return response if isinstance(response, dict) else {"status": "unknown"}
