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
| `app/main.py` | FastAPI 入口，提供 `/api/debate/start`、`/api/debate/save`、`/api/judges` 以及静态 UI 服务。 |
| `app/debate/orchestrator.py` | 控制辩论流程的核心类，依次调用各角色的 LLM API。 |
| `app/debate/script_templates.py` | 不同赛段的提示语模板生成器。 |
| `host_service/host_api.py` | DeepSeek 版主持人示例，暴露 `/host/respond`。 |
| `host_service/debater_api.py` | OpenAI 版辩手示例，暴露 `/debater/respond`。 |
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
2. 启动编排服务（同时提供 REST API 与前端静态资源）：
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
3. 启动主持人服务（端口可自定）：
   ```bash
   uvicorn host_service.host_api:app --reload --port 8010
   ```
4. 启动内置评委 persona（需先设置 `DEEPSEEK_API_KEY`，每个评委独立进程）：
   ```bash
   uvicorn host_service.judges.logic_professor:app --reload --port 8111
   uvicorn host_service.judges.arbiter:app --reload --port 8112
   uvicorn host_service.judges.empiricist:app --reload --port 8113
   uvicorn host_service.judges.coach:app --reload --port 8114
   uvicorn host_service.judges.rhetoric:app --reload --port 8115
   ```
5. （可选）使用模拟参赛者快速演练：
   ```bash
   MOCK_PERSONA="乐观架构师" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8101
   MOCK_PERSONA="务实怀疑派" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8102
   MOCK_PERSONA="评委 Alpha" MOCK_ROLE=judge uvicorn examples.mock_participant:app --port 8111
   ```
6. 打开 `http://localhost:8000/ui/`，填写端点后即可控制整场辩论。

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
- 前端资源存放于 `web/static/index.html`，由 FastAPI 以 `/ui` 静态路径提供。
- `app.js` 会拉取 `/api/judges` 预设、动态增删评委卡片，并在表单提交时调用 `/api/debate/start`，保存按钮对应 `/api/debate/save`。
- `styles.css` 控制时间轴、评委表格及提示气泡的样式。
- 在界面中填写辩题、两位辩手端点、五位或更多评委端点以及主持人端点，点击“开始辩论”即可开赛；赛后点击“保存本场辩论”会将 JSON 写入 `saved_debates/`。
- 若需自定义前端交互或样式，可修改上述静态文件并重启 FastAPI 服务。

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
1. 参考 `host_service/debater_api.py`，了解如何读取上下文、组装对话消息并调用 OpenAI Chat Completion。
2. 若要新增 persona，可复制该文件，修改 `SYSTEM_PROMPT`、第三方模型配置（如 `OPENAI_API_URL`、`OPENAI_MODEL`），再以 FastAPI 路由 `@app.post("/<persona>/respond")` 暴露服务。
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

## 保存赛果
- 点击 UI 中的“保存本场辩论”按钮或直接调用 `/api/debate/save`，后台会将完整结果写入 `saved_debates/<时间戳>_<slug>.json`。
- 相关数据结构定义在 `app/debate/models.py` 的 `SaveDebateRequest` 中，可用于编写脚本批量归档。

## 扩展思路
- 在 `app/debate/models.py` 的 `DebateOptions` 中加入计时器、发言长度限制或多语种支持。
- 修改 `app/main.py` 的 `_write_debate`，将赛果转存到数据库或消息队列。
- 调整 `app/debate/orchestrator.py` 与 `script_templates`，扩展额外赛段或重写提示词。
- 在 `app/debate/llm_client.py` 中加入缓存、重试、速率限制等企业级控制逻辑。
