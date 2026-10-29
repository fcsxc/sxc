"""上下文模块的数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SpecItem:
    """一条规格条目。"""

    spec_id: str
    title: str
    status: str
    applies_to: list[str]
    supersedes: list[str]
    tags: list[str]
    source_path: str
    body: str
    revision: int = 1

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def search_text(self) -> str:
        return " ".join(
            [self.spec_id, self.title, self.status, " ".join(self.tags), " ".join(self.applies_to), self.body]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodeSymbol:
    """代码中的一个符号（函数 / 类 / 方法）。"""

    symbol_id: str
    file_path: str
    module_path: str
    name: str
    kind: str
    signature: str
    docstring: str
    line_start: int
    line_end: int
    source: str

    def search_text(self) -> str:
        return " ".join([self.symbol_id, self.module_path, self.name, self.kind, self.signature, self.docstring])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestCase:
    """一个测试用例。"""

    test_id: str
    file_path: str
    name: str
    module_path: str
    docstring: str
    asserts: str
    target_modules: list[str] = field(default_factory=list)

    def search_text(self) -> str:
        return " ".join([self.test_id, self.module_path, self.name, self.docstring, self.asserts])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TaskState:
    """任务状态：模块重启后由 PowerContext 读回并复用。"""

    task_id: str
    task: str
    done: list[str] = field(default_factory=list)
    todo: list[str] = field(default_factory=list)
    verifications: list[dict[str, Any]] = field(default_factory=list)
    context_digest: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "TaskState":
        import json

        data = json.loads(payload)
        return cls(
            task_id=data.get("task_id", ""),
            task=data.get("task", ""),
            done=list(data.get("done", [])),
            todo=list(data.get("todo", [])),
            verifications=list(data.get("verifications", [])),
            context_digest=data.get("context_digest", ""),
            updated_at=data.get("updated_at", ""),
        )


@dataclass
class ContextPack:
    """一次开发任务的上下文。"""

    task: str
    modules: list[str] = field(default_factory=list)
    specs: list[dict[str, Any]] = field(default_factory=list)
    superseded_specs: list[dict[str, Any]] = field(default_factory=list)
    symbols: list[dict[str, Any]] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    state: dict[str, Any] | None = None
    queries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
