# 雾港夜话：会记住你的守夜人

一个用 **Dify Chatflow** 编排、由 **PowerContext** 提供跨会话剧情记忆的互动故事应用。

## 1. 作品创意

雾港每晚都会忘掉一个人，只有酒馆守夜人“墨灯”记得住。玩家告诉墨灯自己在雾港做了什么，墨灯会：

1. 从同一记忆档案召回旧物品、旧承诺和旧线索；
2. 至少接住一个旧细节，生成一段 120 到 220 字的哥特奇幻短剧；
3. 给出 A/B 选择，玩家的下一次选择又会被写入记忆，推动剧情继续分叉。

换一个 Dify 会话，只要填写同一个 PowerContext `scope_id`，墨灯仍能接住上一回合留下的线索。作品的乐趣来自“每句话都会留下后果”，而 PowerContext 让这种后果真正跨会话存在。

## 2. 技术分工

```text
Dify Chatflow
  Start(memory_id)
    -> Code：构造召回请求
    -> HTTP POST /v1/context/prepare
    -> LLM：依据召回内容续写剧情并给出 A/B 选择
    -> Code：封装本回合行动、选择和剧情结果
    -> HTTP POST /v1/memory/remember
    -> Answer

PowerContext 1.4.1
  Scope：隔离每个玩家的剧情档案
  /v1/context/prepare：按当前行动召回相关旧记忆
  /v1/memory/remember：保存玩家行动、选择与剧情结果
```

- **Dify** 负责输入、请求构造、HTTP 调用、大模型生成、记忆封装和最终回答，是应用的核心编排层。
- **PowerContext** 负责长期记忆和上下文复用，是跨会话剧情的真实数据来源，不是只做健康检查的装饰组件。
- 本作品不要求 Embedding 模型，使用 PowerContext 的显式 Memory 与全文召回能力。

## 3. 交付物

| 文件 | 用途 |
|---|---|
| `when-night-remembers.yml` | 可直接导入 Dify 的 advanced-chat DSL |
| `scripts/acceptance_test.py` | 创建 Scope，完成两回合真实写入与召回验收 |
| `scripts/powercontext_smoke_test.py` | 最小写入/召回冒烟测试 |
| `scripts/validate_dsl.py` | 校验 DSL 节点、连线、HTTP 契约、环境变量及 Code 节点语法 |
| `powercontext.env.example` | PowerContext Server 环境变量模板 |
| `evidence/powercontext-acceptance.json` | PowerContext 1.4.1 的两回合实际运行结果 |
| `evidence/powercontext-smoke-test.json` | 最小写入/召回实际结果 |
| `evidence/dsl-validation.json` | DSL 静态校验结果 |
| `evidence/dify-cloud-e2e.json` | Dify Cloud 使用 `gpt-4.1` 的真实运行记录与核验结果 |
| `evidence/dify-cloud-e2e.md` | Dify 实际输入、完整输出和跨会话召回说明 |

## 4. 运行环境

- Dify Community 1.5+ 或 Dify Cloud（DSL `0.1.5`，`advanced-chat` 模式）
- 一个已配置的 Chat 模型；DSL 默认使用 `openai / gpt-4.1`，导入后可重新绑定为工作区可用模型
- PowerContext `1.4.1`
- Python `3.11+`
- 不需要 Embedding 或 Rerank 服务

## 5. 启动 PowerContext

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install "powercontext[cli,server]==1.4.1"
cp powercontext.env.example .env
# 将 POWERCONTEXT_SERVER_DATABASE_URL 改为本机可写的绝对路径
powercontext server run --env-file .env
```

确认服务：

```bash
curl http://127.0.0.1:8000/health/live
# {"status":"ok"}
curl http://127.0.0.1:8000/health/ready
```

## 6. 创建可重复使用的剧情档案

执行：

```bash
python scripts/acceptance_test.py --base-url http://127.0.0.1:8000 \
  --output evidence/powercontext-acceptance.json
```

脚本会创建新的 Scope，写入两回合剧情，并验证旧记忆在后续查询中仍可召回。记录输出中的 `scope_id`，它将作为 Dify 应用的“记忆档案 ID”。

如果只想快速生成一个空白档案，可运行：

```bash
python scripts/powercontext_smoke_test.py --base-url http://127.0.0.1:8000
```

## 7. 配置 Dify 与 PowerContext 的网络连接

### 方案 A：Dify 与 PowerContext 都在本机/Docker

将 DSL 环境变量 `powercontext_url` 设置为：

```text
http://host.docker.internal:8000
```

Linux Docker 部署 Dify 时，需要为 Dify 容器增加：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### 方案 B：Dify Cloud

Dify Cloud 不能访问你电脑上的 `127.0.0.1`。需要把 PowerContext 临时暴露为公网 HTTPS 地址，例如使用 Serveo 或 Cloudflare Tunnel，然后把该 HTTPS 地址填入 `powercontext_url`：

```bash
# 示例：需要本机 SSH 可以访问 serveo.net
ssh -R 80:localhost:8000 serveo.net
```

终端会输出一个 `https://...` 地址。先从另一个网络或浏览器确认 `/health/live` 可访问，再在 Dify 应用的环境变量中填写它。

不要提交隧道地址、API Key、密码或数据库文件。隧道地址是临时地址，重新启动后需要重新配置。

## 8. 导入并发布 Dify 应用

1. 在 Dify 的 **Studio -> 创建应用 -> 导入 DSL** 中导入 `when-night-remembers.yml`。
2. 打开应用环境变量，将 `powercontext_url` 改为第 7 节确认过的地址。
3. 打开“守夜人墨灯”LLM 节点，将模型重新绑定到工作区可用的 Chat 模型。
4. 发布应用。
5. 在应用启动表单的“记忆档案 ID”中填写第 6 节输出的 `scope_id`。

## 9. 完整验样

### 第一回合

- 记忆档案 ID：`scope_id`
- 输入：

```text
我把一枚会唱歌的铜钥匙交给守夜人，约好满月回来取。我要沿着雾里的蓝色灯影去找失踪的摆渡人。
```

预期：

- 输出包含【场景】【余波】【选择】；
- 接住“会唱歌的铜钥匙”“满月之约”“蓝色灯影”等当前输入；
- 给出 A/B 两个选择。

### 第二回合（跨会话）

- 结束当前 Dify 会话并新建会话；
- 使用**同一个** `scope_id`；
- 输入：

```text
我回来了。你还记得我留下的东西吗？
```

预期：

- 墨灯提到“会唱歌的铜钥匙”“满月之约”或“蓝色灯影”中的至少一个；
- 把这些内容当作旧日记忆，而不是全新物品；
- 继续给出 A/B 选择。

### 第三回合（选择影响剧情）

- 使用同一个 `scope_id`；
- 输入：

```text
我选 A。满月之前，我要把钥匙暂借给摆渡人的妹妹。
```

预期：

- 剧情承接第二回合的旧线索；
- 本次选择与结果会再次写入 PowerContext；
- 后续新会话询问“摆渡人的妹妹 / 潮汐钟楼 / 午夜前归还”时，能够召回第三回合产生的记忆。

### 重置

重新运行 `acceptance_test.py` 或 `powercontext_smoke_test.py` 创建新的 Scope，并用新的 `scope_id` 开始即可。

## 10. 验证记录

`evidence/dify-cloud-e2e.json` 是 Dify Cloud 的真实运行结果：以 `openai / gpt-4.1` 执行完整 Chatflow，成功召回 PowerContext 中保存的“会唱歌的铜钥匙”“满月前归还的钥匙”和“摆渡人的妹妹”，并返回 A/B 选择。

`evidence/powercontext-acceptance.json` 是 PowerContext `1.4.1` 的实际运行结果，验证了：

1. `POST /v1/scopes` 创建独立 Scope；
2. 第一回合通过 `POST /v1/memory/remember` 写入剧情；
3. `POST /v1/context/prepare` 召回“会唱歌的铜钥匙”“满月之夜”“蓝色灯影”；
4. 第二回合写入“摆渡人的妹妹”“潮汐钟楼”“午夜前归还”；
5. 旧记忆仍可召回，新记忆也能在后续查询中召回。

运行 DSL 静态校验：

```bash
python scripts/validate_dsl.py
```

校验内容包括 JSON/YAML 可解析性、节点与连线完整性、PowerContext HTTP 契约、环境变量、模型节点和 Python Code 节点语法。

## 11. 已知限制

- Dify Cloud 需要公网 HTTPS 后端；localhost 或 `host.docker.internal` 只在本地/Docker Dify 中可用。
- 模型输出措辞会变化，验收关注是否接住旧线索、输出完整场景和 A/B 选择，不要求固定文案。
- Scope ID 是数据分区键，不是访问控制。生产环境应由可信应用为每个用户分配独立 Scope。
- PowerContext 不可达时，Dify HTTP 节点会报错；应先检查 `/health/live` 和 `/health/ready`。

## 12. 参考资料

- Dify HTTP Request 节点：https://docs.dify.ai/en/cloud/use-dify/nodes/http-request
- PowerContext API 快速开始：https://powercontext.oceanbase.io/zh/docs/develop/api-quickstart/
- 赛题规则：https://oceanbase.yuque.com/org-wiki-obtech-vh7w9r/hc3pio/lhfslihtnnb8yqh6
- 赛题参考工作流：https://github.com/dzh-gitcode/dify-workflows
