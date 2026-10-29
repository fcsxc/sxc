"""上下文选择算法。

选择链路（每一步都由 seekdb 的真实查询结果驱动）：

    任务文本 ──▶ 规格候选（全文检索 / 关键词匹配）
                    │
                    ├─▶ 焦点模块 = 任务点名的模块 ∪ 命中规格的 applies_to
                    │
                    ├─▶ 代码符号（按焦点模块 + 关键词）
                    ├─▶ 测试用例（按被测模块 + 关键词）
                    └─▶ 已被取代的规格（说明哪些决策已经失效）
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from .models import ContextPack, TaskState
from .seekdb_store import SeekdbStore

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
SPEC_ID_RE = re.compile(r"SPEC-[A-Z0-9]+(?:-[A-Z0-9]+)+")

STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "is", "are", "for", "and", "or",
    "by", "with", "on", "at", "be", "as", "it", "this", "that", "from",
    "impl", "implement", "please", "need", "needs", "should", "must", "can",
}


def tokenize(text: str) -> list[str]:
    """中英混合分词：英文按单词（并拆开点号路径），中文按二元组。"""

    tokens: list[str] = []
    for word in IDENT_RE.findall(text):
        lowered = word.lower()
        if lowered not in STOPWORDS:
            tokens.append(lowered)
        if "." in word:
            for part in word.split("."):
                if len(part) > 1 and part.lower() not in STOPWORDS:
                    tokens.append(part.lower())
    for run in CJK_RE.findall(text):
        if len(run) == 1:
            tokens.append(run)
            continue
        for index in range(len(run) - 1):
            tokens.append(run[index : index + 2])
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def focus_modules(task: str, known_modules: Sequence[str]) -> list[str]:
    """任务文本里直接点名的模块。"""

    found: list[str] = []
    for module in known_modules:
        if not module:
            continue
        if module in task:
            found.append(module)
            continue
        tail = module.rsplit(".", 1)[-1]
        if len(tail) > 2 and re.search(rf"\b{re.escape(tail)}\b", task):
            found.append(module)
    return found


def _token_hits(text: str, tokens: Sequence[str]) -> int:
    lowered = text.lower()
    return sum(1 for token in tokens if token in lowered)


def rank_specs(
    candidates: list[dict[str, Any]],
    task: str,
    tokens: Sequence[str],
    explicit_modules: Sequence[str],
) -> list[tuple[float, dict[str, Any]]]:
    """给规格候选打分。

    打分项：数据库全文得分、关键词命中数、任务是否直接引用规格编号、
    规格声明的适用模块是否命中焦点模块。
    """

    referenced = {spec_id for spec_id in SPEC_ID_RE.findall(task)}
    ranked: list[tuple[float, dict[str, Any]]] = []
    for spec in candidates:
        haystack = " ".join(
            [spec["spec_id"], spec["title"], " ".join(spec["tags"]), spec["body"]]
        )
        score = float(spec.get("fts_score", 0.0))
        score += 1.2 * _token_hits(haystack, tokens)
        if spec["spec_id"] in referenced:
            score += 8.0
        if explicit_modules and set(spec["applies_to"]) & set(explicit_modules):
            score += 4.0
        ranked.append((score, spec))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["spec_id"]))
    return ranked


def rank_symbols(
    candidates: list[dict[str, Any]],
    task: str,
    tokens: Sequence[str],
    modules: Sequence[str],
) -> list[tuple[float, dict[str, Any]]]:
    ranked: list[tuple[float, dict[str, Any]]] = []
    for symbol in candidates:
        score = 0.0
        if symbol["module_path"] in modules:
            score += 5.0
        if symbol["name"] in task:
            score += 6.0
        score += 1.0 * _token_hits(
            " ".join([symbol["name"], symbol["signature"], symbol["docstring"]]), tokens
        )
        if symbol["kind"] in {"function", "class"}:
            score += 0.5
        ranked.append((score, symbol))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["symbol_id"]))
    return ranked


def rank_tests(
    candidates: list[dict[str, Any]],
    task: str,
    tokens: Sequence[str],
    modules: Sequence[str],
) -> list[tuple[float, dict[str, Any]]]:
    ranked: list[tuple[float, dict[str, Any]]] = []
    for case in candidates:
        score = 0.0
        if set(case["target_modules"]) & set(modules):
            score += 5.0
        if case["name"] in task:
            score += 4.0
        score += 1.0 * _token_hits(
            " ".join([case["name"], case["docstring"], case["asserts"]]), tokens
        )
        ranked.append((score, case))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["test_id"]))
    return ranked


def select_context(
    store: SeekdbStore,
    task: str,
    state: TaskState | None = None,
    spec_limit: int = 4,
    symbol_limit: int = 12,
    test_limit: int = 8,
) -> ContextPack:
    """根据开发任务构造上下文。"""

    tokens = tokenize(task)
    known_modules = store.modules()
    explicit = focus_modules(task, known_modules)

    spec_candidates = store.search_specs(task, tokens, limit=40)
    ranked_specs = rank_specs(spec_candidates, task, tokens, explicit)
    specs = [spec for score, spec in ranked_specs[:spec_limit] if score > 0]

    modules = _dedupe(list(explicit) + [m for spec in specs for m in spec["applies_to"]])

    symbol_candidates = store.search_symbols(modules, tokens, limit=80)
    ranked_symbols = rank_symbols(symbol_candidates, task, tokens, modules)
    symbols = [symbol for score, symbol in ranked_symbols[:symbol_limit] if score > 0]

    test_candidates = store.search_tests(modules, tokens, limit=80)
    ranked_tests = rank_tests(test_candidates, task, tokens, modules)
    tests = [case for score, case in ranked_tests[:test_limit] if score > 0]

    selected_ids = {spec["spec_id"] for spec in specs}
    superseded_ids: set[str] = set()
    for spec in specs:
        superseded_ids.update(spec["supersedes"])
    superseded = [
        spec
        for spec in store.superseded_specs()
        if spec["spec_id"] in superseded_ids or spec["spec_id"] in selected_ids
    ]

    pack = ContextPack(
        task=task,
        modules=modules,
        specs=[dict(spec, score=round(score, 3)) for score, spec in ranked_specs[:spec_limit] if score > 0],
        superseded_specs=superseded,
        symbols=[dict(symbol, score=round(score, 3)) for score, symbol in ranked_symbols[:symbol_limit] if score > 0],
        tests=[dict(case, score=round(score, 3)) for score, case in ranked_tests[:test_limit] if score > 0],
        state=state.to_dict() if state else None,
        queries=[record.to_dict() for record in store.query_log],
    )
    return pack
