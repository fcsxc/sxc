# 学记 StudyMemo —— 让学习、科研更高效的复习与周报助手

> OceanBase 数据库大赛 · Qoder 赛道作品
> 用 Qoder 开发 · 核心功能基于 PowerContext 记忆服务

## 一、解决的问题

学习科研中有三个高频痛点：

1. **复习没节奏**：学过就忘，不知道今天该复习什么，考前突击。
2. **状态记不住**：自己的薄弱点、目标、偏好散落在聊天记录和便签里，工具不会"记得你"。
3. **周报靠拼凑**：每周要从聊天记录里一条条翻学习记录，手工拼周报。

学记 StudyMemo 用 **PowerContext** 把「学习档案」（目标 / 薄弱点 / 偏好 / 里程碑）持久化为跨会话记忆，按艾宾浩斯遗忘曲线自动排出每日复习计划，并一键生成对照目标的周报。

## 二、核心功能

| 功能 | 说明 | PowerContext 的作用 |
| --- | --- | --- |
| 今日复习计划 | 按遗忘曲线（1/2/4/7/15/30 天间隔）自动排期 | 召回档案中的**薄弱点**，优先排序 |
| 学习档案 | 目标、薄弱点、偏好、里程碑的读写 | 记忆写入 PowerContext，**跨会话、跨重启持久** |
| 打卡闭环 | 掌握 / 又忘了 | 打卡「又忘了」自动把该知识点写入薄弱点记忆 |
| 自动周报 | 汇总本周打卡，对照目标与薄弱点 | 召回档案生成「进度 vs 目标」对比 |
| 健康检查 | `/healthz` 输出应用与 PowerContext 状态 | 连通性可核对 |

## 三、技术架构

```
浏览器 ── Flask (app/, 端口 5000) ── HTTP ── PowerContext Server (端口 8000, SQLite)
                │                                  │
                └─ 任务/打卡数据 (JSON)             └─ 学习档案 Memory（带版本、跨会话）
```

- **PowerContext 1.4.1**：核心记忆服务，采用「基础记忆」模式（显式保存与召回，无需模型 API），存储为 SQLite。
- **Flask 3.x**：轻量 Web 应用，Python 3.11+。
- 应用通过 PowerContext HTTP API 读写记忆：`POST /v1/scopes`、`POST /v1/memory/remember`、`POST /v1/memory/entries/list`、`POST /v1/context/prepare`。

## 四、运行说明

### 环境要求

- Python 3.11+（本项目在 3.12 验证）
- [uv](https://docs.astral.sh/uv/)（PowerContext 官方要求）
- Windows / macOS / Linux

### 安装依赖

```bash
# 1) 安装 uv（如已有可跳过）
pip install uv            # 或 curl -LsSf https://astral.sh/uv/install.sh | sh

# 2) 安装 PowerContext（含 Server 与 CLI）。
#    注意：Server 要求 SQLite >= 3.38（Windows 自带 Python 常为旧版）。
#    指定 --python 3.12 让 uv 使用自带的 Python 构建（内置 SQLite 3.4x）：
uv python install 3.12
uv tool install --force --python 3.12 "powercontext[cli,server]==1.4.1"

# 3) 安装本项目依赖
pip install -r requirements.txt
```

> 提示：可先检查 SQLite 版本 `python -c "import sqlite3; print(sqlite3.sqlite_version)"`，
> 若 >= 3.38 可省略 `uv python install` 与 `--python 3.12`。

### 启动

**一键启动（推荐）**

```bash
./start.sh        # Linux / macOS
start.bat         # Windows
```

脚本会依次：生成/校验 PowerContext 配置（SQLite + 基础记忆模式）→ 后台启动 PowerContext Server → 启动学记应用 → 打印访问地址。

**手动启动（分步）**

```bash
# 终端 1：PowerContext（模板模式 = SQLite + 基础记忆，无需模型 API）
mkdir -p powercontext-config && cd powercontext-config
echo Y | powercontext config init --template --language zh --output .env
powercontext server run --env-file .env                # 默认端口 8000

# 终端 2：学记应用
cd qoder
export POWERCONTEXT_URL=http://127.0.0.1:8000
python -m app.main                                     # 打开 http://127.0.0.1:5000
```

### 可选：导入示例数据

```bash
python scripts/seed.py     # 创建 5 个示例学习任务
```

## 五、验证样例（按步骤可复现）

**目标**：核对 PowerContext 记忆在项目中实际发挥作用（写 → 读 → 复用）。

**步骤 1：启动服务并验证连通**

```bash
./start.sh
curl http://127.0.0.1:5000/healthz
# 期望：{"app":"ok","powercontext":true}
```

**步骤 2：写入并召回学习档案（一条命令）**

```bash
python scripts/verify.py
```

期望输出包含：4 条记忆写入成功、召回时打印带 `artifact_id` 的记录、`PreparedContext` 按提示「今晚复习数据库索引」返回记忆选集、最后打印 `✅ 验证通过`。

**步骤 3：验证跨重启持久（记忆复用）**

1. 记下 `verify.py` 打印的 `scope_id` 或页面档案内容；
2. 停止两个服务（Ctrl+C），再执行 `./start.sh` 重启；
3. 打开 http://127.0.0.1:5000 ，档案区块仍然显示步骤 2 写入的目标/薄弱点/偏好；
4. 或执行 `curl -X POST http://127.0.0.1:8000/v1/memory/entries/list -H "Content-Type: application/json" -d '{"scope_id":"<上一步的ID>"}'` 直接核对 PowerContext 中的记忆。

**步骤 4：体验完整闭环**

1. 页面添加任务「B+ 树索引结构」→ 点「首次学习完成 ✓」；
2. 在「今日复习计划」点「又忘了 ✗」→ 档案薄弱点中自动出现该知识点（核对 PowerContext 记忆 +1）；
3. 打开「周报」页 → 自动生成对照目标与薄弱点的周报。

**指定技术作用记录**：步骤 2/3 的终端输出、步骤 3 的 curl 结果、步骤 4 的页面截图即为 PowerContext 读写记录，可直接作为提交材料。

## 六、Qoder 开发记录

本项目的主要开发工作由 Qoder 完成：

| 环节 | Qoder 完成的工作 |
| --- | --- |
| 需求拆解 | 基于赛题要求选定 PowerContext 为指定技术，设计「复习教练 + 记忆档案 + 周报」方案 |
| 编码 | 编写 `app/pc.py`（PowerContext HTTP 客户端）、`app/core.py`（遗忘曲线/周报）、`app/main.py`（路由）、全部模板与样式 |
| 调试 | 在沙箱内安装 PowerContext 1.4.1，实际启动服务，运行 `verify.py` 打通写→读→复用链路并修复接口字段差异 |
| 部署准备 | 编写一键启动脚本、运行说明、验证样例与项目网站源文件 |

Qoder 账号 UID：见提交表单（与 Qoder Sites 站点归属一致）。

## 七、目录结构

```
qoder/
├── README.md           # 本文件（运行说明 + 验证样例）
├── requirements.txt
├── start.sh / start.bat
├── app/
│   ├── main.py         # Flask 路由
│   ├── pc.py           # PowerContext 记忆客户端
│   ├── core.py         # 遗忘曲线、打卡、周报
│   ├── templates/      # 页面
│   └── static/         # 样式
├── scripts/
│   ├── seed.py         # 示例数据
│   └── verify.py       # 验证样例（一键核对 PowerContext 读写）
└── website/            # Qoder Sites 网站源文件
    └── index.html
```

## 八、许可与致谢

- 本项目代码：Apache-2.0
- PowerContext：OceanBase 团队开源（Apache-2.0），本项目仅通过其 HTTP API 接入，未修改其源码。
