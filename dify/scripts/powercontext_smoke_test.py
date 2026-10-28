#!/usr/bin/env python3
"""Create a demo scope, write one memory, and verify it can be recalled."""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import uuid
from typing import Any


def post(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {path} failed: HTTP {exc.code}: {detail}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--scope-id")
    parser.add_argument("--idempotency-key")
    args = parser.parse_args()
    idempotency_key = args.idempotency_key or f"when-night-remembers-demo-{uuid.uuid4().hex}"

    scope_id = args.scope_id
    if not scope_id:
        try:
            scope = post(
                args.base_url,
                "/v1/scopes",
                {
                    "title": "雾港夜话演示档案",
                    "summary": "Dify + PowerContext 的跨会话剧情记忆演示",
                    "idempotency_key": idempotency_key,
                },
            )
        except RuntimeError as exc:
            if "scope_idempotency_conflict" not in str(exc):
                raise
            scope = post(
                args.base_url,
                "/v1/scopes",
                {
                    "title": "雾港夜话演示档案",
                    "summary": "Dify + PowerContext 的跨会话剧情记忆演示",
                    "idempotency_key": f"{idempotency_key}-{uuid.uuid4().hex}",
                },
            )
        scope_id = scope["scope_id"]

    remembered = post(
        args.base_url,
        "/v1/memory/remember",
        {
            "scope_id": scope_id,
            "kind": "decision",
            "text": "玩家在雾港酒馆把一枚会唱歌的铜钥匙交给守夜人，并约定满月时回来取回。",
            "reason": "第一幕中玩家做出的明确剧情选择",
        },
    )
    prepared = post(
        args.base_url,
        "/v1/context/prepare",
        {
            "scope_id": scope_id,
            "query": "铜钥匙 守夜人 满月 酒馆",
            "max_bytes": 4000,
        },
    )

    content = prepared.get("content") or ""
    ok = prepared.get("status") in {"ready", "empty"} and (
        prepared.get("status") == "empty" or "会唱歌的铜钥匙" in content
    )
    result = {
        "ok": ok,
        "scope_id": scope_id,
        "remember": remembered,
        "prepare": prepared,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
