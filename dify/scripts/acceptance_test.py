#!/usr/bin/env python3
"""Exercise the exact PowerContext calls used by the Dify Chatflow."""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any


def post(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {path} failed: HTTP {exc.code}: {detail}") from exc


def assert_memory(content: str, required: list[str]) -> None:
    missing = [value for value in required if value not in content]
    if missing:
        raise AssertionError(f"prepared context is missing {missing!r}: {content!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    run_id = uuid.uuid4().hex

    scope = post(
        base_url,
        "/v1/scopes",
        {
            "title": "雾港夜话验收档案",
            "summary": "验证 Dify 工作流使用的 PowerContext 记忆写入与跨会话召回。",
            "idempotency_key": f"memory-tavern-acceptance-{run_id}",
        },
    )
    scope_id = scope["scope_id"]

    first_memory = post(
        base_url,
        "/v1/memory/remember",
        {
            "scope_id": scope_id,
            "kind": "decision",
            "text": (
                "第一回合：玩家把会唱歌的铜钥匙交给守夜人墨灯，约定满月之夜回来取回；"
                "玩家选择沿着雾中的蓝色灯影调查失踪的摆渡人。"
            ),
            "reason": "雾港夜话第一回合的玩家行动与选择，供下一次会话召回",
        },
    )
    first_context = post(
        base_url,
        "/v1/context/prepare",
        {
            "scope_id": scope_id,
            "query": "我回来了。你还记得铜钥匙和满月之约吗？",
            "max_bytes": 4000,
        },
    )
    first_content = first_context.get("content") or ""
    assert_memory(first_content, ["会唱歌的铜钥匙", "满月之夜", "蓝色灯影"])

    second_memory = post(
        base_url,
        "/v1/memory/remember",
        {
            "scope_id": scope_id,
            "kind": "decision",
            "text": (
                "第二回合：玩家选择 A，在满月前把铜钥匙暂借给摆渡人的妹妹，"
                "钥匙唱出了通往潮汐钟楼的旋律，但守夜人提醒玩家必须在午夜前归还。"
            ),
            "reason": "雾港夜话第二回合的选择结果，供后续剧情继续承接",
        },
    )
    historical_context = post(
        base_url,
        "/v1/context/prepare",
        {
            "scope_id": scope_id,
            "query": "会唱歌的铜钥匙 满月之夜 蓝色灯影 最初的选择",
            "max_bytes": 4000,
        },
    )
    historical_content = historical_context.get("content") or ""
    assert_memory(historical_content, ["会唱歌的铜钥匙", "满月之夜", "蓝色灯影"])

    continuing_context = post(
        base_url,
        "/v1/context/prepare",
        {
            "scope_id": scope_id,
            "query": "摆渡人的妹妹 潮汐钟楼 午夜前归还 铜钥匙",
            "max_bytes": 4000,
        },
    )
    continuing_content = continuing_context.get("content") or ""
    assert_memory(continuing_content, ["铜钥匙", "摆渡人的妹妹", "潮汐钟楼", "午夜前归还"])

    result = {
        "ok": True,
        "ran_at": datetime.now(UTC).isoformat(),
        "powercontext_version": "1.4.1",
        "base_url": base_url,
        "scope_id": scope_id,
        "turns": [
            {
                "turn": 1,
                "remember": first_memory,
                "prepare_status": first_context.get("status"),
                "recalled": ["会唱歌的铜钥匙", "满月之夜", "蓝色灯影"],
                "content_bytes": first_context.get("content_bytes"),
            },
            {
                "turn": 2,
                "remember": second_memory,
                "historical_prepare_status": historical_context.get("status"),
                "historical_recalled": ["会唱歌的铜钥匙", "满月之夜", "蓝色灯影"],
                "continuing_prepare_status": continuing_context.get("status"),
                "continuing_recalled": ["铜钥匙", "摆渡人的妹妹", "潮汐钟楼", "午夜前归还"],
                "historical_content_bytes": historical_context.get("content_bytes"),
                "continuing_content_bytes": continuing_context.get("content_bytes"),
            },
        ],
        "dify_contract": {
            "context_node": "POST /v1/context/prepare",
            "remember_node": "POST /v1/memory/remember",
            "scope_input": "将 scope_id 填入启动变量 memory_id",
        },
    }
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        from pathlib import Path

        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
