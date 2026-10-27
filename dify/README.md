# 雾港夜话：会记住你的守夜人

一个用 Dify Chatflow 编排、用 PowerContext 保存跨会话剧情记忆的轻量互动故事应用。

## 作品创意

雾港每晚都会忘掉一个人，只有酒馆守夜人“墨灯”记得住。玩家每次告诉墨灯一个在雾港做出的行动，墨灯都会：

1. 召回同一记忆档案里过去的物品、承诺和线索；
2. 接住其中至少一个旧细节，讲述一段短剧情；
3. 给出 A/B 两个选择，让玩家继续故事。

每次交互都会写回 PowerContext。换一个 Dify 会话，只要使用同一个记忆档案 ID，墨灯仍能接住上一回合的线索。

## Dify 与 PowerContext 的分工

- **Dify**：解析输入，组装请求，调用 PowerContext，调用大模型生成剧情，写回本回合记忆，并输出回答。
- **PowerContext**：提供跨会话的长期记忆。`/v1/context/prepare` 召回旧事，`/v1/memory/remember` 保存新剧情。

调用顺序：

```text
开始
  -> 组装记忆查询（Code）
  -> 召回旧日记忆（HTTP: /v1/context/prepare）
  -> 守夜人墨灯（LLM）
  -> 封装本回合记忆（Code）
  -> 封存本回合记忆（HTTP: /v1/memory/remember）
  -> 回答
```

## 文件说明

| 文件 | 用途 |
|---|---|
| `when-night-remembers.yml` | 可直接导入 Dify 的 Chatflow DSL |
| `scripts/powercontext_smoke_test.py` | 创建演示 Scope、写入记忆并验证召回 |
| `evidence/powercontext-smoke-test.json` | 本次实际运行 PowerContext 1.4.1 的读写结果 |

## 运行环境

- Dify Community：建议 1.5 或更高版本，已使用 advanced-chat DSL `0.1.5`
- 模型：DSL 默认使用 OpenAI Provider 的 `gpt-4o-mini`；导入后可换成任意已配置的 Chat 模型
- PowerContext：1.4.1
- Python：3.11+
- 不要求 Embedding 模型；本作品使用 PowerContext 的显式 Memory 与全文召回能力

## 启动 PowerContext

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install "powercontext[cli,server]==1.4.1"

powercontext config init --template --output .env
powercontext server run --env-file .env
```

默认监听 `http://127.0.0.1:8000`。若 SQLite 默认目录不可写，在 `.env` 中设置：

```dotenv
POWERCONTEXT_SERVER_DATABASE_URL=sqlite+aiosqlite:///C:/absolute/path/powercontext.db
```

确认服务：

```bash
curl http://127.0.0.1:8000/health/live
# {"status":"ok"}
```

本目录的真实读写验证：

```bash
python scripts/powercontext_smoke_test.py --base-url http://127.0.0.1:8000
```

脚本会输出一个 `scope_id`，并验证“会唱歌的铜钥匙”能被下一次上下文准备召回。实际运行结果见 `evidence/powercontext-smoke-test.json`。

## 导入 Dify

1. 在 Dify 的 **Studio / 创建应用 / 导入 DSL** 中导入 `when-night-remembers.yml`。
2. 打开应用的环境变量，确认 `powercontext_url`：
   - Dify 与 PowerContext 都在宿主机：`http://127.0.0.1:8000`
   - Dify 在 Docker、PowerContext 在宿主机：`http://host.docker.internal:8000`
   - Linux Docker 需为 Dify 容器增加 `host.docker.internal:host-gateway`
3. 打开 LLM 节点，将模型重新绑定到当前工作区可用的 Chat 模型。
4. 发布应用。

## 验证样例

### 准备

运行 `powercontext_smoke_test.py` 并记录输出的 `scope_id`。

### 第一回合

- 记忆档案 ID：上一步的 `scope_id`
- 输入：

```text
我把一枚会唱歌的铜钥匙交给守夜人，约好满月回来取。
```

预期表现：

- 墨灯用第一人称讲出一段雾港剧情；
- 回应中接住“会唱歌的铜钥匙”或“满月之约”；
- 以 A/B 两个选择结束。

### 第二回合

- 结束当前 Dify 会话并新建会话；
- 使用**同一个**记忆档案 ID；
- 输入：

```text
我回来了。你还记得我留下的东西吗？
```

预期表现：

- 墨灯至少提到“会唱歌的铜钥匙”或“满月之约”；
- 说明这是来自旧日的记忆，而不是把它当成全新物品；
- 继续给出 A/B 选择。

### 重置

创建新的 Scope，并在下一回合使用新的 `scope_id` 即可从空白记忆重新开始。

## 异常与限制

- PowerContext 未启动或地址不可达时，Dify 对应 HTTP 节点会报错；按上面的健康检查先确认服务可用。
- 本作品使用显式长期记忆，不依赖 Embedding 模型；PowerContext 返回 `empty` 时，守夜人会把本轮视为第一次相遇。
- 示例剧情由 LLM 生成，因此具体措辞不固定，但记忆中的关键物品和承诺应保持稳定。
- Scope ID 只是数据分区键，不是访问控制；实际部署时应由可信应用为每个用户分配独立 Scope。

## 参考资料

- Dify HTTP Request 节点：https://docs.dify.ai/en/cloud/use-dify/nodes/http-request
- PowerContext API 快速开始：https://powercontext.oceanbase.io/zh/docs/develop/api-quickstart/
- 赛题参考工作流：https://github.com/dzh-gitcode/dify-workflows
