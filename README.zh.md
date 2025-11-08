# AI Debate Arena

AI Debate Arena 是一套基于 FastAPI 的自动化辩论编排系统。为两个辩手、五名评委以及一位主持人分别提供可访问的 API 端点，即可按照完整赛制运行一场 LLM 对抗赛，并附带主持人串场、评委打分及赛果保存等能力。

## 辩论赛制
1. 主持人开场：介绍辩题、参赛方及规则。
2. 开篇陈词：正方先发言，反方随后回应。
3. 交叉质询（上半场）：正方向反方提问，问题数不超过 `max_cross_questions`。
4. 交叉质询（下半场）：反方向正方提问，轮换角色。
5. 自由辩论：双方轮流短句交流，最多 `max_freeform_rounds` 个回合。
6. 总结陈词：反方先总结，正方最后收尾。
7. 评委评议：每位评委给出投票结果及理由。
8. 主持人收官：公布胜者、感谢参赛者并结束比赛。

系统会在各环节之间插入主持人串场，并在赛前随机分配正反方身份。

## 目录导览
| 路径 | 作用 |
| --- | --- |
| `app/main.py` | FastAPI 入口，提供 `/api/personas/*`、`/api/debate/*`、`/api/judges` 以及静态 UI 服务。 |
| `app/debate/orchestrator.py` | 控制辩论流程的核心类，依次调用各角色的 LLM API。 |
| `app/debate/script_templates.py` | 不同赛段的提示语模板生成器。 |
| `app/personas/models.py` | Persona 存储、运行时调用及摘要信息的 Schema。 |
| `app/personas/storage.py` | Persona JSON 存储与线程安全读写封装。 |
| `app/personas/runtime.py` | 根据保存的 LLM 连接信息代理请求，直接调用你配置的 API。 |
| `host_service/host_api.py` | DeepSeek 版主持人示例，暴露 `/host/respond`。 |
| `host_service/debater_api.py` | DeepSeek 版辩手示例，暴露 `/debater/respond`。 |
| `host_service/judges/` | 五名 DeepSeek 评委 persona，通用逻辑在 `judge_common.py` 中。 |
| `examples/mock_participant.py` | 可充当任意角色的模拟服务，适合本地调试。 |
| `web/static/index.html` | 控制面板 UI，访问 `http://localhost:8000/ui/` 时加载。 |
| `web/static/app.js` | 浏览器逻辑，负责配置端点、触发辩论、渲染时间轴及保存结果。 |
| `web/static/styles.css` | UI 样式与布局。 |
| `saved_debates/` | 点击“保存本场辩论”后生成的 JSON 文件目录。 |

## 快速上手
1. 安装依赖（推荐 Python 3.10+）：
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. 启动编排服务（需在项目根目录执行，确保 `app` 模块可被导入）：
   ```bash
   cd /path/to/AI\ Debate\ Test2
   python3 -m uvicorn app.main:app --reload --port 8000
   ```
   > 也可以直接运行 `uvicorn app.main:app ...`，但必须在仓库根目录执行或手动设置 `PYTHONPATH`。
3. （可选）启动示例主持人服务（端口可自定），若你希望直接复用 DeepSeek Demo 主持人：
   ```bash
   uvicorn host_service.host_api:app --reload --port 8010
   ```
4. 五名参考评委现已内嵌在 `app.main` 中（访问路径 `/api/presets/judges/*`），无需额外终端，只需在启动主服务前设置好 `DEEPSEEK_API_KEY`。
5. （可选）使用模拟参赛者快速演练：
   ```bash
   MOCK_PERSONA="乐观架构师" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8101
   MOCK_PERSONA="务实怀疑派" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8102
   MOCK_PERSONA="评委 Alpha" MOCK_ROLE=judge uvicorn examples.mock_participant:app --port 8111
   ```
6. 打开 `http://localhost:8000/ui/`，使用训练面板填写 persona 并运行整场辩论。

### 为什么必须启动 FastAPI？
前端所有操作（新建/修改 persona、获取评委预设、启动或保存辩论）都依赖 `FastAPI` 提供的 `/api/personas/*`、`/api/debate/*` 等接口。如果服务器未运行，训练主持人/辩手/评委面板无法写入配置，辩论控制台也无法调用后台逻辑。

## Persona 训练工作台与自动托管端点
UI 现在包含四个独立页面：**训练主持人、训练辩手、训练裁判、运行辩论赛**。

1. **保存后自动生成 Endpoint**：在任意训练面板填写名称、提示词、LLM API URL/模型/Key 等信息，点击“保存并生成 API”即可把配置写入本地 `personas/registry.json`（该目录被 `.gitignore` 忽略，API Key 不会进入版本库），并生成一个 `/api/personas/<类型>/<id>/respond` 端点。
2. **真实 API 透传**：无论是 OpenAI、DeepSeek 还是自建网关，只要使用兼容的 Chat Completions 接口，平台都会携带你输入的 API URL 与 Key 直接请求真实模型，因此可以真正连接 GPT‑4/5 等模型，不是示例假数据。
3. **提示词即 System Instruction**：训练面板中的“提示词”会被保存，并在 `POST /respond` 时作为 `system` 消息发送；辩论上下文（stage/topic 等）会作为 `user` 消息附加。
4. **一键填入辩论表单**：每个面板都提供“填入辩论表单”按钮，可自动回填主持人、正反方或评委卡片，省去复制粘贴。
5. **JSON 输出兼容性**：勾选“仅输出 JSON”（`force_json`）会为提示语附加一段 JSON 说明，并仅在上游模型支持时发送 OpenAI 式的 `response_format`。DeepSeek 接口目前忽略该字段（依旧返回普通文本），因此若使用 DeepSeek，请确保提示词本身约束模型输出 JSON。

可用的 Persona API：
- `GET /api/personas`：获取所有 persona 摘要。
- `POST /api/personas/{type}`、`PUT /api/personas/{type}/{id}`、`DELETE /api/personas/{type}/{id}`：管理 persona。
- `POST /api/personas/{type}/{id}/respond`：执行实际 LLM 调用，返回的就是辩论编排所需的 `content` 与 `metadata`。

## API 调用示例
当两位辩手、五名评委以及主持人的服务均已就绪，可直接发起请求：
```bash
curl -X POST http://localhost:8000/api/debate/start \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "城市是否应该在公立学校强制使用 AI 家教？",
    "debaters": [
      {"name": "曙光队", "endpoint": "http://localhost:8101/respond"},
      {"name": "地平线队", "endpoint": "http://localhost:8102/respond"}
    ],
    "judges": [
      {"name": "评委 Alpha", "endpoint": "http://localhost:8111/respond"},
      {"name": "评委 Beta", "endpoint": "http://localhost:8112/respond"},
      {"name": "评委 Gamma", "endpoint": "http://localhost:8113/respond"},
      {"name": "评委 Delta", "endpoint": "http://localhost:8114/respond"},
      {"name": "评委 Epsilon", "endpoint": "http://localhost:8115/respond"}
    ],
    "host": {"name": "主持人 Stellar", "endpoint": "http://localhost:8010/host/respond"},
    "options": {
      "max_cross_questions": 5,
      "max_freeform_rounds": 10,
      "request_timeout_seconds": 45
    }
  }'
```

响应字段包括 `assignments`（随机分配的角色）、`transcript`（完整发言记录）、`interludes`（主持人串场）以及 `judge_votes`（评委裁决）。

## 控制台 UI 使用说明
- `/ui` 页面由四个 Tab 组成，前三个用于训练/管理 persona，最后一个用于填写辩题并启动比赛。
- `app.js` 负责 Tab 切换、调用 `/api/personas` 进行增删改查、获取 `/api/judges` 预设、发起 `/api/debate/start` 以及保存 `/api/debate/save`。
- “生成的 API Endpoint” 会实时展示实际 URL，并提供复制 / 自动填充按钮。
- 辩论页面需要一个主持人、两位辩手以及至少五位评委的端点，可混用自动托管 persona 或外部服务。点击“开始辩论”运行，赛后用“保存本场辩论”写入 `saved_debates/`。
- 静态文件位于 `web/static/`，修改后刷新浏览器即可，无需额外构建。

## 配置各角色的 API
所有角色均需提供 `POST` 接口，数据格式如下：
```json
{
  "prompt": "...",
  "context": {...},
  "client": {"name": "展示名称"},
  "tags": {... 可选 ...}
}
```
返回内容必须包含：
```json
{
  "content": "LLM 输出字符串",
  "metadata": {... 可选诊断信息 ...}
}
```

### 辩手
1. 参考 `host_service/debater_api.py`，了解如何读取上下文、组装对话消息并调用 DeepSeek Chat Completion。
2. 若要新增 persona，可复制该文件，修改 `SYSTEM_PROMPT`、第三方模型配置（如 `DEEPSEEK_API_URL`、`DEEPSEEK_MODEL`），再以 FastAPI 路由 `@app.post("/<persona>/respond")` 暴露服务。
3. 将每位辩手部署到独立端口或服务节点，并在 UI 或 `/api/debate/start` 请求体中登记其 URL。

### 主持人
1. `host_service/host_api.py` 展示了基于 DeepSeek Chat 的主持逻辑，平台会调用你在比赛配置中填写的主持人端点。
2. 可通过调整长文本 `SYSTEM_PROMPT`、`DEEPSEEK_TEMPERATURE` 等环境变量或替换模型供应商来定制主持风格。
3. 请保持输出精炼，因为主持人串场会直接显示在时间轴中。

### 评委
1. 所有评委 persona 位于 `host_service/judges/`，通用逻辑集中在 `judge_common.py`，内含评分维度和 DeepSeek Reasoner 调用。
2. 新建评委时，可编写一个模块定义 `PersonaConfig`（含权重、介绍、补充说明），然后调用 `judge_common.build_app(config)` 生成 FastAPI 应用。
3. 评委必须返回符合 `JudgeOutput v1` 结构的 JSON 字符串，平台会自动解析并汇总评分。

### 模拟服务
`examples/mock_participant.py` 支持通过设置环境变量 `MOCK_ROLE`（`debater` / `judge` / `host`）和 `MOCK_PERSONA` 来模拟不同角色，方便在无真实 LLM 凭证时进行流程测试。

## 实时赛况流
- `POST /api/debate/stream` 会以 SSE 兼容的 `data: {...}` 流式返回事件，`type` 可能是 `host_interlude`、`debate_turn`、`judge_vote`、`complete` 或 `error`，`payload` 就是对应数据。
- 现在会在首个发言前额外推送 `assignments` 事件，让 UI 或自定义客户端即时了解到正反两方的随机分配结果。
- Web UI 已改为订阅该流，主持人串场、正反双方发言、评委投票会实时渲染，再也不用等整场结束才看到结果。
- 如需一次性拿到完整结果（例如脚本批量运行），仍可调用传统的 `/api/debate/start`。

## 保存赛果
- 点击 UI 中的“保存本场辩论”按钮或直接调用 `/api/debate/save`，后台会将完整结果写入 `saved_debates/<时间戳>_<slug>.json`。
- 相关数据结构定义在 `app/debate/models.py` 的 `SaveDebateRequest` 中，可用于编写脚本批量归档。

## 扩展思路
- 在 `app/debate/models.py` 的 `DebateOptions` 中加入计时器、发言长度限制或多语种支持。
- 修改 `app/main.py` 的 `_write_debate`，将赛果转存到数据库或消息队列。
- 调整 `app/debate/orchestrator.py` 与 `script_templates`，扩展额外赛段或重写提示词。
- 在 `app/debate/llm_client.py` 中加入缓存、重试、速率限制等企业级控制逻辑。
