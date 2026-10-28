#!/usr/bin/env python3
"""Validate the exported Dify DSL and its required integration points."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DSL_PATH = ROOT / "when-night-remembers.yml"


def main() -> int:
    dsl = yaml.safe_load(DSL_PATH.read_text(encoding="utf-8"))
    graph = dsl["workflow"]["graph"]
    nodes = graph["nodes"]
    edges = graph["edges"]
    ids = [node["id"] for node in nodes]
    assert len(ids) == len(set(ids)), "duplicate node IDs"
    for edge in edges:
        assert edge["source"] in ids and edge["target"] in ids, edge
    types = [node["data"]["type"] for node in nodes]
    assert types[0] == "start" and types[-1] == "answer"
    code_nodes = [node for node in nodes if node["data"]["type"] == "code"]
    for node in code_nodes:
        ast.parse(node["data"]["code"])
    env_names = [item["name"] for item in dsl["workflow"]["environment_variables"]]
    assert "powercontext_url" in env_names
    urls = [node["data"].get("url", "") for node in nodes if node["data"]["type"] == "http-request"]
    assert any(url.endswith("/v1/context/prepare") for url in urls)
    assert any(url.endswith("/v1/memory/remember") for url in urls)
    result = {
        "ok": True,
        "dsl": DSL_PATH.name,
        "version": dsl["version"],
        "mode": dsl["app"]["mode"],
        "nodes": types,
        "http_endpoints": urls,
        "environment_variables": env_names,
        "code_nodes_compiled": len(code_nodes),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
