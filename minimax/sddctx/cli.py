"""上下文模块命令行入口。

常用命令：

    python -m sddctx.cli import                     # 导入规格/代码/测试到 seekdb
    python -m sddctx.cli context --task "..."       # 构造开发上下文包
    python -m sddctx.cli state save --task "..."    # 保存任务状态到 PowerContext
    python -m sddctx.cli state show                 # 读回任务状态
    python -m sddctx.cli agent apply --task "..."   # 用 MiniMax 完成代码修改
    python -m sddctx.cli query --sql "SELECT ..."   # 直接查询 seekdb
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import config
from .agent import (
    MiniMaxClient,
    MiniMaxError,
    MmxCliClient,
    build_prompt,
    extract_files,
    signature_mismatches,
    undefined_names,
    write_files,
)
from .context_pack import render_context_json, render_context_pack, summarize
from .importer import load_code_symbols, load_specs, load_test_cases
from .models import TaskState
from .seekdb_store import SeekdbStore
from .selector import select_context
from .state_store import PowerContextError, PowerContextStateStore


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _open_store(args: argparse.Namespace) -> SeekdbStore:
    store = SeekdbStore(args.db_dir, args.database)
    store.open()
    store.ensure_schema()
    return store


def cmd_import(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    specs = load_specs(Path(args.specs), root)
    symbols = load_code_symbols(Path(args.code), root)
    tests = load_test_cases(Path(args.tests), root)
    store = _open_store(args)
    try:
        store.upsert_specs(specs)
        store.upsert_symbols(symbols)
        store.upsert_tests(tests)
        stats = store.stats()
        print(f"规格条目 {len(specs)} 条，代码符号 {len(symbols)} 个，测试用例 {len(tests)} 个")
        print(f"seekdb 统计：{stats}")
        if args.log:
            Path(args.log).write_text(
                json.dumps([record.to_dict() for record in store.query_log], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"查询日志已写入 {args.log}")
    finally:
        store.close()
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store = _open_store(args)
    state: TaskState | None = None
    try:
        state_store = PowerContextStateStore(scope_title=args.scope_title)
        try:
            state = state_store.load()
        except PowerContextError as exc:
            print(f"[warn] 未读取到 PowerContext 状态：{exc}", file=sys.stderr)
        pack = select_context(
            store,
            args.task,
            state=state,
            spec_limit=args.spec_limit,
            symbol_limit=args.symbol_limit,
            test_limit=args.test_limit,
        )
        markdown = render_context_pack(pack)
        if args.out:
            Path(args.out).write_text(markdown, encoding="utf-8")
            print(f"上下文包已写入 {args.out}")
        if args.json_out:
            Path(args.json_out).write_text(render_context_json(pack), encoding="utf-8")
            print(f"上下文 JSON 已写入 {args.json_out}")
        if args.log:
            Path(args.log).write_text(
                json.dumps([record.to_dict() for record in store.query_log], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if not args.quiet:
            print(markdown)
        else:
            print(json.dumps(summarize(pack), ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


def cmd_state_save(args: argparse.Namespace) -> int:
    state = TaskState(
        task_id=args.task_id or f"TASK-{dt.datetime.now().strftime('%Y%m%d%H%M%S')}",
        task=args.task,
        done=list(args.done or []),
        todo=list(args.todo or []),
        verifications=json.loads(Path(args.verifications).read_text(encoding="utf-8"))
        if args.verifications
        else [],
        context_digest=args.context_digest or "",
        updated_at=dt.datetime.now().isoformat(timespec="seconds"),
    )
    store = PowerContextStateStore(scope_title=args.scope_title)
    response = store.save(state)
    print(f"任务状态已写入 PowerContext（scope={store.scope_id()}）")
    print(json.dumps(response, ensure_ascii=False, indent=2)[:600])
    return 0


def cmd_state_show(args: argparse.Namespace) -> int:
    store = PowerContextStateStore(scope_title=args.scope_title)
    state = store.load()
    if state is None:
        print("（PowerContext 中没有任务状态）")
        return 1
    print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_agent_apply(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store = _open_store(args)
    try:
        state_store = PowerContextStateStore(scope_title=args.scope_title)
        try:
            state = state_store.load()
        except PowerContextError:
            state = None
        pack = select_context(store, args.task, state=state)
        markdown = render_context_pack(pack)
    finally:
        store.close()

    targets: dict[str, str] = {}
    for relative in args.target:
        path = root / relative
        if not path.exists():
            print(f"[error] 目标文件不存在：{relative}", file=sys.stderr)
            return 2
        targets[relative] = path.read_text(encoding="utf-8")

    references: dict[str, str] = {}
    for relative in getattr(args, "reference", []) or []:
        path = root / relative
        if path.exists():
            references[relative] = path.read_text(encoding="utf-8")

    client = (
        MmxCliClient(model=args.model)
        if args.protocol == "mmx-cli"
        else MiniMaxClient(model=args.model)
    )
    feedback: str | None = None
    attempts: list[dict[str, Any]] = []
    written: list[str] = []
    for attempt in range(1, args.max_attempts + 1):
        prompt = build_prompt(args.task, markdown, targets, feedback, references)
        print(f"[MiniMax] 第 {attempt} 次请求，提示词 {len(prompt)} 字符 …")
        response = client.chat(prompt, system=None)
        files = extract_files(
            response.content,
            fallback_path=next(iter(targets)) if len(targets) == 1 else None,
        )
        allowed = set(targets)
        rejected = {path: content for path, content in files.items() if path not in allowed}
        files = {path: content for path, content in files.items() if path in allowed}
        attempts.append(
            {
                "attempt": attempt,
                "response": response.to_dict(),
                "parsed_files": sorted(files),
                "rejected_files": sorted(rejected),
            }
        )
        if rejected:
            print(
                f"[guard] 拒绝写入非目标文件（已忽略）：{', '.join(sorted(rejected))}",
                file=sys.stderr,
            )
        if not files:
            print("[warn] 模型输出里没有解析到文件块", file=sys.stderr)
            feedback = "上一次输出没有包含要求的文件块，请严格按 ### FILE: <路径> + 代码块格式输出。"
            continue
        written = write_files(root, files, dry_run=args.dry_run, allowed=set(targets))
        print(f"[MiniMax] 已写入：{', '.join(written)}")
        missing: dict[str, list[str]] = {}
        mismatches: dict[str, list[str]] = {}
        for relative, content in files.items():
            undefined = undefined_names(content)
            if undefined:
                missing[relative] = undefined
            problems = signature_mismatches(content, references)
            if problems:
                mismatches[relative] = problems
        if missing:
            print(f"[lint] 发现未定义的名字：{missing}", file=sys.stderr)
        if mismatches:
            print(f"[lint] 发现签名不匹配的调用：{mismatches}", file=sys.stderr)
        if args.test_command or args.test_argv:
            import subprocess

            if args.test_argv:
                # 列表形式：不经 shell，避免可执行文件路径含空格时的引号问题
                completed = subprocess.run(
                    list(args.test_argv),
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                )
            else:
                completed = subprocess.run(
                    args.test_command,
                    shell=True,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                )
            attempts[-1]["test_command"] = args.test_command or " ".join(args.test_argv)
            attempts[-1]["test_exit_code"] = completed.returncode
            print(f"[test] 退出码 {completed.returncode}")
            if completed.returncode == 0:
                break
            feedback_parts = [
                f"测试命令 `{args.test_command}` 退出码 {completed.returncode}。",
            ]
            if missing:
                for relative, names in missing.items():
                    feedback_parts.append(
                        f"静态检查发现 `{relative}` 里这些名字没有定义也没有导入：{', '.join(names)}。"
                        "请在文件头补上对应的 import 语句（可用上文「建议的 import 语句」）。"
                    )
            if mismatches:
                for relative, problems in mismatches.items():
                    feedback_parts.append(
                        f"静态检查发现 `{relative}` 里对既有函数的调用与真实签名不符：\n"
                        + "\n".join(f"- {problem}" for problem in problems)
                        + "\n请按真实签名调用。"
                    )
            feedback_parts.append("stdout:\n" + completed.stdout[-4000:])
            feedback_parts.append("stderr:\n" + completed.stderr[-4000:])
            feedback = "\n".join(feedback_parts)
    if args.record:
        Path(args.record).parent.mkdir(parents=True, exist_ok=True)
        Path(args.record).write_text(
            json.dumps(
                {
                    "task": args.task,
                    "model": client.model,
                    "attempts": attempts,
                    "written": written,
                    "context_pack": markdown,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"MiniMax 调用记录已写入 {args.record}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    store = _open_store(args)
    try:
        rows = store.execute(args.sql)
        for row in rows:
            print(" | ".join("" if value is None else str(value) for value in row))
        print(f"[{len(rows)} 行]")
    finally:
        store.close()
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = _open_store(args)
    try:
        print(json.dumps(store.stats(), ensure_ascii=False, indent=2))
        print("模块：", ", ".join(store.modules()))
    finally:
        store.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sddctx", description="SDD 上下文模块")
    parser.add_argument("--db-dir", default=str(config.SEEKDB_DIR))
    parser.add_argument("--database", default=config.SEEKDB_DATABASE)
    parser.add_argument("--root", default=str(config.WORKSPACE_DIR))
    parser.add_argument("--scope-title", default=config.POWERCONTEXT_SCOPE_TITLE)
    sub = parser.add_subparsers(dest="command", required=True)

    importer = sub.add_parser("import", help="把规格/代码/测试导入 seekdb")
    importer.add_argument("--specs", default=str(config.SPECS_DIR))
    importer.add_argument("--code", default=str(config.WORKSPACE_DIR))
    importer.add_argument("--tests", default=str(config.TESTS_DIR))
    importer.add_argument("--log", default="")
    importer.set_defaults(func=cmd_import)

    context = sub.add_parser("context", help="根据任务构造开发上下文")
    context.add_argument("--task", required=True)
    context.add_argument("--out", default="")
    context.add_argument("--json-out", default="")
    context.add_argument("--log", default="")
    context.add_argument("--spec-limit", type=int, default=4)
    context.add_argument("--symbol-limit", type=int, default=14)
    context.add_argument("--test-limit", type=int, default=12)
    context.add_argument("--quiet", action="store_true")
    context.set_defaults(func=cmd_context)

    state = sub.add_parser("state", help="任务状态（PowerContext）")
    state_sub = state.add_subparsers(dest="state_command", required=True)

    state_save = state_sub.add_parser("save", help="保存任务状态")
    state_save.add_argument("--task", required=True)
    state_save.add_argument("--task-id", default="")
    state_save.add_argument("--done", action="append", default=[])
    state_save.add_argument("--todo", action="append", default=[])
    state_save.add_argument("--verifications", default="")
    state_save.add_argument("--context-digest", default="")
    state_save.set_defaults(func=cmd_state_save)

    state_show = state_sub.add_parser("show", help="读回任务状态")
    state_show.set_defaults(func=cmd_state_show)

    agent = sub.add_parser("agent", help="MiniMax 参与代码修改")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)

    agent_apply = agent_sub.add_parser("apply", help="用上下文包驱动 MiniMax 修改代码")
    agent_apply.add_argument("--task", required=True)
    agent_apply.add_argument("--target", action="append", required=True)
    agent_apply.add_argument("--reference", action="append", default=[])
    agent_apply.add_argument("--model", default=config.MINIMAX_MODEL)
    agent_apply.add_argument(
        "--protocol",
        default=os.environ.get("MINIMAX_PROTOCOL", "minimax"),
        choices=["minimax", "mmx-cli", "anthropic"],
        help="MiniMax 调用方式：minimax=官方 HTTP API，mmx-cli=官方 mmx 命令行，anthropic=兼容接口",
    )
    agent_apply.add_argument("--max-attempts", type=int, default=2)
    agent_apply.add_argument(
        "--test-command",
        default="",
        help=(
            "用于验证模型产出的命令，在工程根目录下用 shell 执行。"
            "若可执行文件路径包含空格，Windows 下需要自行加引号；"
            "更推荐改用 --test-argv（列表形式，不经 shell）"
        ),
    )
    agent_apply.add_argument(
        "--test-argv",
        action="append",
        default=[],
        help="验证命令的参数列表形式（不经 shell），可重复传入；与 --test-command 二选一",
    )
    agent_apply.add_argument("--dry-run", action="store_true")
    agent_apply.add_argument("--record", default="")
    agent_apply.set_defaults(func=cmd_agent_apply)

    query = sub.add_parser("query", help="直接执行一条 seekdb SQL")
    query.add_argument("--sql", required=True)
    query.set_defaults(func=cmd_query)

    stats = sub.add_parser("stats", help="查看各表记录数")
    stats.set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (PowerContextError, MiniMaxError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
