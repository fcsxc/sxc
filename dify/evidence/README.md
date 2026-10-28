# 运行证据

本目录保存可重复执行的验收结果。证据文件由仓库内脚本生成，不依赖作者本地缓存。

## `powercontext-acceptance.json`

生成命令：

```bash
python scripts/acceptance_test.py \
  --base-url http://127.0.0.1:8000 \
  --output evidence/powercontext-acceptance.json
```

实际环境：

- PowerContext `1.4.1`
- Python `3.12`
- SQLite 持久化
- Server：`http://127.0.0.1:8000`

验证内容：

1. 通过 `POST /v1/scopes` 创建独立剧情 Scope。
2. 通过 `POST /v1/memory/remember` 写入第一回合行动。
3. 通过 `POST /v1/context/prepare` 召回“会唱歌的铜钥匙”“满月之夜”“蓝色灯影”。
4. 写入第二回合选择后，再次召回新旧故事线索。
5. 输出 `ok: true`、两次 `prepare_status: ready`、记忆 Artifact ID 和召回关键词。

这些请求与 Dify Chatflow 中两个 HTTP Request 节点的契约完全一致，证明 Dify 使用的后端记忆链路真实可用。

## `powercontext-smoke-test.json`

最小演示：创建 Scope、写入“会唱歌的铜钥匙”，随后通过上下文准备接口召回同一记忆。

## `dsl-validation.json`

生成命令：

```bash
python scripts/validate_dsl.py --output evidence/dsl-validation.json
```

校验 Dify 应用模式、节点顺序、节点 ID、连线、环境变量、两个 PowerContext HTTP 端点、Code 节点语法与执行结果、LLM Prompt 和 Answer 引用关系。

## `dify-cloud-e2e.json` / `dify-cloud-e2e.md`

Dify Cloud 的真实运行记录。应用使用 `advanced-chat`、`openai / gpt-4.1`，连接 PowerContext `1.4.1` 的公网 HTTPS 入口。

测试输入：

```text
我回来了。你还记得铜钥匙和摆渡人的妹妹吗？
```

实际输出成功召回“会唱歌的铜钥匙”“满月前归还的钥匙”和“摆渡人的妹妹”，其中“摆渡人的妹妹”没有出现在本轮输入中，证明长期记忆参与了生成。输出包含【场景】【余波】【选择】，并以 A/B 选项结束。

完整回复、Scope、模型和核验项见两个证据文件。
