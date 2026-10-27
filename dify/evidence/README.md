# 运行证据

`powercontext-smoke-test.json` 由 `scripts/powercontext_smoke_test.py` 在以下环境实际生成：

- PowerContext `1.4.1`
- Python `3.12`
- SQLite 持久化
- 服务地址：`http://127.0.0.1:8000`

验证内容：

1. 调用 `POST /v1/memory/remember` 写入“会唱歌的铜钥匙”剧情记忆。
2. 调用 `POST /v1/context/prepare`，查询词为“铜钥匙 守夜人 满月 酒馆”。
3. 返回 `status: ready`，并在 `content` 中召回相同的剧情记忆。

这证明 Dify DSL 中的两个 HTTP 节点所调用的 PowerContext 接口能够完成真实的记忆写入和跨请求召回。

Dify Chatflow 的实际剧情文案会随所配置的大模型变化，因此本证据聚焦于可稳定核验的技术链路：

```text
Dify HTTP Node -> PowerContext /v1/memory/remember -> 持久化
Dify HTTP Node -> PowerContext /v1/context/prepare -> 召回
```
