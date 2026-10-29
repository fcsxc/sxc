"""seekdb（嵌入式 OceanBase seekdb）存储与检索。

工程资料（规格 / 代码符号 / 测试用例）全部写入 seekdb，上下文检索通过
真实 SQL 完成；每一条执行过的 SQL 都会记录下来，作为「数据库实际参与」的证据。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import CodeSymbol, SpecItem, TestCase


def literal(value: Any) -> str:
    """把 Python 值渲染成 SQL 字面量（驱动不支持参数绑定）。"""

    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    escaped = text.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def identifier(value: str) -> str:
    """把数据库名渲染成 SQL 标识符（CREATE DATABASE 不接受字符串字面量）。"""

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value or ""):
        raise ValueError(f"非法的数据库名：{value!r}")
    return f"`{value}`"


@dataclass
class QueryRecord:
    """一次 SQL 执行的记录。"""

    sql: str
    rows: int
    duration_ms: float
    ok: bool = True
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "rows": self.rows,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "error": self.error,
        }


SPEC_COLUMNS = (
    "spec_id, title, status, applies_to, supersedes, tags, source_path, revision, body"
)
SYMBOL_COLUMNS = (
    "symbol_id, file_path, module_path, name, kind, signature, docstring, line_start, line_end, source"
)
TEST_COLUMNS = "test_id, file_path, name, module_path, docstring, asserts, target_modules"


class SeekdbStore:
    """工程资料的 seekdb 存储。"""

    def __init__(self, db_dir: Path | str, database: str = "sdd") -> None:
        self.db_dir = Path(db_dir)
        self.database = database
        self.query_log: list[QueryRecord] = []
        self.fts_enabled = False
        self._instance = None
        self._connection = None
        self._cursor = None

    # ------------------------------------------------------------------ 生命周期
    def open(self) -> "SeekdbStore":
        import pylibseekdb as seekdb

        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._instance = seekdb.open(db_dir=str(self.db_dir))
        try:
            self._connection = self._instance.connect(database=self.database, autocommit=True)
        except Exception:
            fallback = self._instance.connect(database="test", autocommit=True)
            fallback_cursor = fallback.cursor()
            fallback_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {identifier(self.database)}")
            fallback.close()
            self._connection = self._instance.connect(database=self.database, autocommit=True)
        self._cursor = self._connection.cursor()
        return self

    def close(self) -> None:
        for closable in (self._cursor, self._connection, self._instance):
            if closable is None:
                continue
            try:
                closable.close()
            except Exception:  # pragma: no cover - 关闭失败不影响结果
                pass
        self._cursor = self._connection = self._instance = None

    def __enter__(self) -> "SeekdbStore":
        return self.open()

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # ------------------------------------------------------------------ 执行
    def execute(self, sql: str) -> list[tuple]:
        """执行一条 SQL，返回结果行，并记录到查询日志。"""

        if self._cursor is None:
            raise RuntimeError("SeekdbStore 尚未打开")
        started = time.perf_counter()
        rows: list[tuple] = []
        try:
            self._cursor.execute(sql)
            try:
                rows = list(self._cursor.fetchall() or [])
            except Exception:
                rows = []
            self.query_log.append(
                QueryRecord(
                    sql=sql,
                    rows=len(rows),
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                )
            )
            return rows
        except Exception as exc:
            self.query_log.append(
                QueryRecord(
                    sql=sql,
                    rows=0,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    ok=False,
                    error=str(exc),
                )
            )
            raise

    # ------------------------------------------------------------------ 表结构
    def ensure_schema(self) -> None:
        """建库建表；优先建立带 IK 分词器的全文索引，失败则退回普通表。"""

        self.execute(f"CREATE DATABASE IF NOT EXISTS {identifier(self.database)}")
        ddl_with_fts = """
        CREATE TABLE IF NOT EXISTS spec_item (
            spec_id VARCHAR(128) NOT NULL,
            title VARCHAR(512) NOT NULL,
            status VARCHAR(32) NOT NULL,
            applies_to VARCHAR(1024) NOT NULL,
            supersedes VARCHAR(512) NOT NULL,
            tags VARCHAR(512) NOT NULL,
            source_path VARCHAR(512) NOT NULL,
            revision INT NOT NULL,
            body MEDIUMTEXT NOT NULL,
            search_text MEDIUMTEXT NOT NULL,
            PRIMARY KEY (spec_id),
            FULLTEXT INDEX idx_spec_search (search_text) WITH PARSER ik
        ) ORGANIZATION = HEAP
        """
        ddl_plain = """
        CREATE TABLE IF NOT EXISTS spec_item (
            spec_id VARCHAR(128) NOT NULL,
            title VARCHAR(512) NOT NULL,
            status VARCHAR(32) NOT NULL,
            applies_to VARCHAR(1024) NOT NULL,
            supersedes VARCHAR(512) NOT NULL,
            tags VARCHAR(512) NOT NULL,
            source_path VARCHAR(512) NOT NULL,
            revision INT NOT NULL,
            body MEDIUMTEXT NOT NULL,
            search_text MEDIUMTEXT NOT NULL,
            PRIMARY KEY (spec_id)
        ) ORGANIZATION = HEAP
        """
        symbol_ddl = """
        CREATE TABLE IF NOT EXISTS code_symbol (
            symbol_id VARCHAR(512) NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            module_path VARCHAR(256) NOT NULL,
            name VARCHAR(256) NOT NULL,
            kind VARCHAR(32) NOT NULL,
            signature VARCHAR(1024) NOT NULL,
            docstring MEDIUMTEXT NOT NULL,
            line_start INT NOT NULL,
            line_end INT NOT NULL,
            source MEDIUMTEXT NOT NULL,
            search_text MEDIUMTEXT NOT NULL,
            PRIMARY KEY (symbol_id)
        ) ORGANIZATION = HEAP
        """
        test_ddl = """
        CREATE TABLE IF NOT EXISTS test_case (
            test_id VARCHAR(512) NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            name VARCHAR(256) NOT NULL,
            module_path VARCHAR(256) NOT NULL,
            docstring MEDIUMTEXT NOT NULL,
            asserts MEDIUMTEXT NOT NULL,
            target_modules VARCHAR(1024) NOT NULL,
            search_text MEDIUMTEXT NOT NULL,
            PRIMARY KEY (test_id)
        ) ORGANIZATION = HEAP
        """
        try:
            self.execute(ddl_with_fts)
            self.fts_enabled = True
        except Exception:
            self.execute(ddl_plain)
            self.fts_enabled = False
        self.execute(symbol_ddl)
        self.execute(test_ddl)

    # ------------------------------------------------------------------ 写入
    def upsert_specs(self, specs: Iterable[SpecItem]) -> int:
        """写入（更新）规格条目；内容变化时 revision 自增。"""

        current = {
            row[0]: (row[1], row[2])
            for row in self.execute(f"SELECT spec_id, body, revision FROM spec_item")
        }
        count = 0
        for spec in specs:
            revision = spec.revision
            previous = current.get(spec.spec_id)
            if previous is not None:
                revision = previous[1] + 1 if previous[0] != spec.body else previous[1]
            values = ", ".join(
                [
                    literal(spec.spec_id),
                    literal(spec.title),
                    literal(spec.status),
                    literal(",".join(spec.applies_to)),
                    literal(",".join(spec.supersedes)),
                    literal(",".join(spec.tags)),
                    literal(spec.source_path),
                    str(int(revision)),
                    literal(spec.body),
                    literal(spec.search_text()),
                ]
            )
            self.execute(
                "INSERT INTO spec_item (spec_id, title, status, applies_to, supersedes, tags, source_path,"
                f" revision, body, search_text) VALUES ({values})"
                " ON DUPLICATE KEY UPDATE title = VALUES(title), status = VALUES(status),"
                " applies_to = VALUES(applies_to), supersedes = VALUES(supersedes), tags = VALUES(tags),"
                " source_path = VALUES(source_path), revision = VALUES(revision), body = VALUES(body),"
                " search_text = VALUES(search_text)"
            )
            count += 1
        return count

    def upsert_symbols(self, symbols: Iterable[CodeSymbol]) -> int:
        count = 0
        for symbol in symbols:
            values = ", ".join(
                [
                    literal(symbol.symbol_id),
                    literal(symbol.file_path),
                    literal(symbol.module_path),
                    literal(symbol.name),
                    literal(symbol.kind),
                    literal(symbol.signature),
                    literal(symbol.docstring),
                    str(int(symbol.line_start)),
                    str(int(symbol.line_end)),
                    literal(symbol.source),
                    literal(symbol.search_text()),
                ]
            )
            self.execute(
                "INSERT INTO code_symbol (symbol_id, file_path, module_path, name, kind, signature,"
                f" docstring, line_start, line_end, source, search_text) VALUES ({values})"
                " ON DUPLICATE KEY UPDATE file_path = VALUES(file_path), module_path = VALUES(module_path),"
                " name = VALUES(name), kind = VALUES(kind), signature = VALUES(signature),"
                " docstring = VALUES(docstring), line_start = VALUES(line_start), line_end = VALUES(line_end),"
                " source = VALUES(source), search_text = VALUES(search_text)"
            )
            count += 1
        return count

    def upsert_tests(self, tests: Iterable[TestCase]) -> int:
        count = 0
        for case in tests:
            values = ", ".join(
                [
                    literal(case.test_id),
                    literal(case.file_path),
                    literal(case.name),
                    literal(case.module_path),
                    literal(case.docstring),
                    literal(case.asserts),
                    literal(",".join(case.target_modules)),
                    literal(case.search_text()),
                ]
            )
            self.execute(
                "INSERT INTO test_case (test_id, file_path, name, module_path, docstring, asserts,"
                f" target_modules, search_text) VALUES ({values})"
                " ON DUPLICATE KEY UPDATE file_path = VALUES(file_path), name = VALUES(name),"
                " module_path = VALUES(module_path), docstring = VALUES(docstring), asserts = VALUES(asserts),"
                " target_modules = VALUES(target_modules), search_text = VALUES(search_text)"
            )
            count += 1
        return count

    # ------------------------------------------------------------------ 检索
    def _like_clause(self, column: str, tokens: Sequence[str]) -> str:
        clauses = [f"{column} LIKE {literal(f'%{token}%')}" for token in tokens if token]
        return " AND (" + " OR ".join(clauses) + ")" if clauses else ""

    def search_specs(
        self,
        task_text: str,
        tokens: Sequence[str],
        limit: int = 30,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        """检索规格条目：全文检索 + 关键词模糊匹配。"""

        hits: dict[str, dict[str, Any]] = {}

        if self.fts_enabled and task_text.strip():
            sql = (
                f"SELECT {SPEC_COLUMNS}, MATCH(search_text) AGAINST ({literal(task_text)}) AS fts_score"
                " FROM spec_item"
                f" WHERE status = {literal(status)}"
                f"   AND MATCH(search_text) AGAINST ({literal(task_text)})"
                " ORDER BY fts_score DESC"
                f" LIMIT {int(limit)}"
            )
            for row in self.execute(sql):
                record = _spec_row(row)
                record["fts_score"] = float(row[-1] or 0.0)
                hits[record["spec_id"]] = record

        like_clause = self._like_clause("search_text", tokens[:12])
        if like_clause:
            sql = (
                f"SELECT {SPEC_COLUMNS} FROM spec_item"
                f" WHERE status = {literal(status)}{like_clause}"
                f" LIMIT {int(limit)}"
            )
            for row in self.execute(sql):
                record = _spec_row(row)
                record.setdefault("fts_score", 0.0)
                hits.setdefault(record["spec_id"], record)
        return list(hits.values())

    def search_symbols(
        self,
        modules: Sequence[str],
        tokens: Sequence[str],
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """检索代码符号：按模块过滤 + 关键词匹配。"""

        hits: dict[str, dict[str, Any]] = {}

        if modules:
            module_list = ", ".join(literal(module) for module in modules)
            sql = (
                f"SELECT {SYMBOL_COLUMNS} FROM code_symbol"
                f" WHERE module_path IN ({module_list})"
                f" LIMIT {int(limit)}"
            )
            for row in self.execute(sql):
                record = _symbol_row(row)
                hits[record["symbol_id"]] = record

        like_clause = self._like_clause("search_text", tokens[:12])
        if like_clause:
            sql = (
                f"SELECT {SYMBOL_COLUMNS} FROM code_symbol"
                f" WHERE 1 = 1{like_clause}"
                f" LIMIT {int(limit)}"
            )
            for row in self.execute(sql):
                record = _symbol_row(row)
                hits.setdefault(record["symbol_id"], record)
        return list(hits.values())

    def search_tests(
        self,
        modules: Sequence[str],
        tokens: Sequence[str],
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """检索测试用例：按被测模块过滤 + 关键词匹配。"""

        hits: dict[str, dict[str, Any]] = {}

        if modules:
            module_list = ", ".join(literal(module) for module in modules)
            conditions = " OR ".join(
                f"target_modules LIKE {literal(f'%{module}%')}" for module in modules
            )
            sql = (
                f"SELECT {TEST_COLUMNS} FROM test_case"
                f" WHERE ({conditions})"
                f" LIMIT {int(limit)}"
            )
            for row in self.execute(sql):
                record = _test_row(row)
                hits[record["test_id"]] = record

        like_clause = self._like_clause("search_text", tokens[:12])
        if like_clause:
            sql = (
                f"SELECT {TEST_COLUMNS} FROM test_case"
                f" WHERE 1 = 1{like_clause}"
                f" LIMIT {int(limit)}"
            )
            for row in self.execute(sql):
                record = _test_row(row)
                hits.setdefault(record["test_id"], record)
        return list(hits.values())

    def superseded_specs(self) -> list[dict[str, Any]]:
        """返回已被取代的规格条目（用于说明「哪些决策已经失效」）。"""

        rows = self.execute(f"SELECT {SPEC_COLUMNS} FROM spec_item WHERE status <> 'active'")
        return [_spec_row(row) for row in rows]

    def stats(self) -> dict[str, int]:
        """各表记录数。"""

        stats: dict[str, int] = {}
        for table in ("spec_item", "code_symbol", "test_case"):
            rows = self.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = int(rows[0][0]) if rows else 0
        return stats

    def modules(self) -> list[str]:
        """库中已知的代码模块。"""

        rows = self.execute("SELECT DISTINCT module_path FROM code_symbol ORDER BY module_path")
        return [row[0] for row in rows]

    def spec_by_id(self, spec_id: str) -> dict[str, Any] | None:
        rows = self.execute(
            f"SELECT {SPEC_COLUMNS} FROM spec_item WHERE spec_id = {literal(spec_id)}"
        )
        return _spec_row(rows[0]) if rows else None


def _split(value: Any) -> list[str]:
    if value is None:
        return []
    return [part for part in str(value).split(",") if part]


def _spec_row(row: Sequence[Any]) -> dict[str, Any]:
    return {
        "spec_id": row[0],
        "title": row[1],
        "status": row[2],
        "applies_to": _split(row[3]),
        "supersedes": _split(row[4]),
        "tags": _split(row[5]),
        "source_path": row[6],
        "revision": int(row[7]),
        "body": row[8],
        "fts_score": 0.0,
    }


def _symbol_row(row: Sequence[Any]) -> dict[str, Any]:
    return {
        "symbol_id": row[0],
        "file_path": row[1],
        "module_path": row[2],
        "name": row[3],
        "kind": row[4],
        "signature": row[5],
        "docstring": row[6],
        "line_start": int(row[7]),
        "line_end": int(row[8]),
        "source": row[9],
    }


def _test_row(row: Sequence[Any]) -> dict[str, Any]:
    return {
        "test_id": row[0],
        "file_path": row[1],
        "name": row[2],
        "module_path": row[3],
        "docstring": row[4],
        "asserts": row[5],
        "target_modules": _split(row[6]),
    }
