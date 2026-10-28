#!/usr/bin/env python3
"""Validate the exported Dify DSL and the PowerContext integration contract."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DSL_PATH = ROOT / "when-night-remembers.yml"


def node_by_type(nodes: list[dict[str, Any]], node_type: str) -> dict[str, Any]:
    matches = [node for node in nodes if node["data"]["type"] == node_type]
    assert len(matches) == 1, f"expected exactly one {node_type} node, found {len(matches)}"
    return matches[0]


def execute_code_node(node: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    code = node["data"]["code"]
    tree = ast.parse(code)
    namespace: dict[str, Any] = {}
    exec(compile(tree, filename="<dify-code-node>", mode="exec"), namespace)
    result = namespace["main"](**arguments)
    assert isinstance(result, dict), "Code node main() must return a dict"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional path to write the validation report as JSON")
    args = parser.parse_args()

    raw = DSL_PATH.read_bytes()
    dsl = yaml.safe_load(raw)
    assert dsl["kind"] == "app", "DSL kind must be app"
    assert dsl["app"]["mode"] == "advanced-chat", "app must use advanced-chat mode"
    dependencies = dsl.get("dependencies", [])
    marketplace_ids = [
        item.get("value", {}).get("marketplace_plugin_unique_identifier", "")
        for item in dependencies
        if item.get("type") == "marketplace"
    ]
    assert any(value.startswith("langgenius/openai:") for value in marketplace_ids), marketplace_ids
    graph = dsl["workflow"]["graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    ids = [node["id"] for node in nodes]
    assert len(ids) == len(set(ids)), "duplicate node IDs"
    for edge in edges:
        assert edge["source"] in ids and edge["target"] in ids, edge

    types = [node["data"]["type"] for node in nodes]
    expected_types = ["start", "code", "http-request", "llm", "code", "http-request", "answer"]
    assert types == expected_types, f"unexpected node order: {types}"
    for source, target in zip(nodes, nodes[1:]):
        assert any(edge["source"] == source["id"] and edge["target"] == target["id"] for edge in edges), (
            f"missing edge {source['id']} -> {target['id']}"
        )

    start = nodes[0]
    start_variables = start["data"].get("variables", [])
    memory_vars = [item for item in start_variables if item.get("variable") == "memory_id"]
    assert len(memory_vars) == 1 and memory_vars[0].get("required") is True

    env_names = [item["name"] for item in dsl["workflow"]["environment_variables"]]
    assert "powercontext_url" in env_names

    http_nodes = [node for node in nodes if node["data"]["type"] == "http-request"]
    endpoints = [node["data"]["url"] for node in http_nodes]
    assert endpoints[0].endswith("/v1/context/prepare"), endpoints
    assert endpoints[1].endswith("/v1/memory/remember"), endpoints
    for node in http_nodes:
        data = node["data"]
        assert data["method"].lower() == "post"
        assert data["authorization"]["type"] == "no-auth"
        assert data["body"]["type"] == "json"
        assert data["body"]["data"][0]["value"].startswith("{{#") and data["body"]["data"][0]["value"].endswith("#}}")
        assert "Content-Type" in data["headers"]

    code_nodes = [node for node in nodes if node["data"]["type"] == "code"]
    prepared = execute_code_node(code_nodes[0], {"memory_id": "scp_demo", "query": "铜钥匙"})
    payload = json.loads(prepared["payload"])
    assert payload == {"scope_id": "scp_demo", "query": "铜钥匙", "max_bytes": 4000}, payload
    remembered = execute_code_node(
        code_nodes[1],
        {"memory_id": "scp_demo", "query": "我选 A", "narration": "钥匙响了一声。"},
    )
    payload = json.loads(remembered["payload"])
    assert payload["scope_id"] == "scp_demo"
    assert payload["kind"] == "decision"
    assert "我选 A" in payload["text"] and "钥匙响了一声。" in payload["text"]

    llm = node_by_type(nodes, "llm")
    assert llm["data"]["model"]["mode"] == "chat"
    assert llm["data"]["model"]["provider"] and llm["data"]["model"]["name"]
    prompt_text = "\n".join(item["text"] for item in llm["data"]["prompt_template"])
    assert "{{#1761580000003.body#}}" in prompt_text
    assert "{{#sys.query#}}" in prompt_text
    answer = nodes[-1]
    assert answer["data"]["answer"] == "{{#1761580000004.text#}}"

    result = {
        "ok": True,
        "dsl": DSL_PATH.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "version": dsl["version"],
        "mode": dsl["app"]["mode"],
        "nodes": types,
        "http_endpoints": endpoints,
        "environment_variables": env_names,
        "dependencies": marketplace_ids,
        "code_nodes_compiled": len(code_nodes),
        "code_nodes_executed": len(code_nodes),
        "model": {
            "provider": llm["data"]["model"]["provider"],
            "name": llm["data"]["model"]["name"],
        },
        "checks": [
            "unique_node_ids",
            "valid_edges",
            "expected_node_order",
            "required_memory_id",
            "marketplace_dependencies",
            "powercontext_environment_variable",
            "powercontext_http_contract",
            "python_code_compilation",
            "python_code_execution",
            "llm_prompt_wiring",
            "answer_wiring",
        ],
    }
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
