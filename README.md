# AI Debate Arena

AI Debate Arena is a FastAPI-based platform for staging fully automated LLM-versus-LLM debates. Provide API endpoints for two debaters, five judges, and a playful host, then trigger a match that walks through every phase of the tournament schedule with detailed prompts and host commentary.

## Debate Format
1. Host introduction: announce the motion, participants, and house rules.
2. Opening statements: affirmative then negative deliver prepared speeches.
3. Cross-examination round 1: affirmative questions the negative (up to `max_cross_questions` turns).
4. Cross-examination round 2: roles swap and the negative questions the affirmative.
5. Free debate: alternating rebuttals for as many as `max_freeform_rounds` exchanges.
6. Closing statements: negative summarizes first, affirmative closes the debate.
7. Judge deliberation: each judge returns a structured ballot and rationale.
8. Host wrap-up: celebrate the winners, acknowledge runners-up, and finish the show.

Host interludes separate every stage with highlights pulled from the transcript, and affirmative/negative roles are randomly assigned before kickoff.

## Component Map
| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI entry point exposing `/api/personas/*`, `/api/debate/*`, `/api/judges`, and serving the static UI. |
| `app/debate/orchestrator.py` | Stage-by-stage debate runner that calls each participant via `LLMClient`. |
| `app/debate/script_templates.py` | Prompt builders for openings, cross-examinations, free debate, closings, and judging. |
| `app/personas/models.py` | Typed schemas for persona storage, runtime payloads, and endpoint summaries. |
| `app/personas/storage.py` | Thread-safe JSON persistence for saved personas (hosts, debaters, judges). |
| `app/personas/runtime.py` | Generic proxy that calls whatever LLM API/Key you configure per persona. |
| `host_service/host_api.py` | DeepSeek-powered host reference implementation responding on `/host/respond`. |
| `host_service/debater_api.py` | Sample DeepSeek-backed debater persona reachable at `/debater/respond`. |
| `host_service/judges/` | Five opinionated DeepSeek judge personas sharing helpers from `judge_common.py`. |
| `examples/mock_participant.py` | Minimal mock server that can play any role for local testing. |
| `web/static/index.html` | Control-room UI shell loaded at `http://localhost:8000/ui/`. |
| `web/static/app.js` | Browser logic for configuring endpoints, launching debates, rendering the timeline, and saving results. |
| `web/static/styles.css` | UI styling and layout. |
| `saved_debates/` | Auto-created directory that stores JSON exports when you click “保存本场辩论”. |

## Quick Start
1. Install dependencies (Python 3.10+ recommended):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Launch the debate orchestrator **from the project root** (the `app` package must be on `PYTHONPATH`). Either `cd` into the repository or pass `--app-dir`:
   ```bash
   cd /path/to/AI\ Debate\ Test2
   python3 -m uvicorn app.main:app --reload --port 8000
   ```
   > Tip: Running `uvicorn` without `python3 -m` also works as long as the current working directory is this repository.
3. (Optional) Start the standalone host service if you want to reuse the DeepSeek demo host exactly as shipped:
   ```bash
   uvicorn host_service.host_api:app --reload --port 8010
   ```
4. The five reference judges are auto-hosted inside `app.main` under `/api/presets/judges/*`, so no extra terminals are required—just export `DEEPSEEK_API_KEY` before launching the main server.
5. (Optional) Spin up mock debaters and judges instead of real LLMs:
   ```bash
   MOCK_PERSONA="Optimistic Architect" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8101
   MOCK_PERSONA="Pragmatic Skeptic" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8102
   MOCK_PERSONA="Judge Alpha" MOCK_ROLE=judge uvicorn examples.mock_participant:app --port 8111
   ```
6. Open `http://localhost:8000/ui/` to use the persona trainers and drive the match.

### Why the server must run
The UI reads and writes persona data via `/api/personas/*`, fetches judge presets, starts debates, and saves transcripts. Without the FastAPI server running, tabs such as “训练主持人/辩手/裁判” cannot persist settings and the debate form cannot call `/api/debate/start`.

## Persona Workbench & Auto-Hosted Endpoints
The UI now presents three trainer tabs (host, debater, judge) plus the debate console:

1. **Create or select personas.** Every trainer lets you pick an existing persona or enter a new name/prompt/LLM configuration. When you click “保存并生成 API”, the backend stores the persona under `personas/registry.json` (local only, git-ignored).
2. **Bring your own LLM credentials.** Supply any chat-completions compatible API URL and key (OpenAI, DeepSeek, Azure OpenAI, local gateways, etc.). The backend proxy (`/api/personas/<type>/<id>/respond`) forwards requests directly, so real GPT‑4/5 calls work exactly as configured—no mock.
3. **One-click endpoint filling.** Each trainer displays the generated endpoint (e.g., `http://localhost:8000/api/personas/judge/<uuid>/respond`). Use “填入辩论表单” to auto-populate the debate form.
4. **System prompt behaviour.** The “提示词” text area is stored verbatim and becomes the `system` message when the persona calls your chosen model. Extra context (stage, topic, highlights, etc.) is injected as the `user` message.
5. **JSON mode compatibility.** Enabling “仅输出 JSON” (`force_json`) injects a helper hint for every prompt and requests OpenAI-style `response_format` **only** for providers that support it. DeepSeek endpoints ignore the HTTP `response_format` flag (they return plain text), so keep `force_json` on only if your prompt instructs the model to emit JSON by itself.

Persona APIs are exposed via FastAPI:
- `GET /api/personas` returns summaries for all hosts/debaters/judges.
- `POST /api/personas/{type}` creates a persona, `PUT` updates it, `DELETE` removes it.
- `POST /api/personas/{type}/{id}/respond` proxies the actual LLM call using the saved configuration. These URLs are what the debate orchestrator uses, so no additional services are required unless you prefer external endpoints.

## Run A Debate Programmatically
Once all participant services respond, you can start a debate by calling the orchestrator:
```bash
curl -X POST http://localhost:8000/api/debate/start \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Should cities mandate AI tutors in public schools?",
    "debaters": [
      {"name": "Team Aurora", "endpoint": "http://localhost:8101/respond"},
      {"name": "Team Meridian", "endpoint": "http://localhost:8102/respond"}
    ],
    "judges": [
      {"name": "Judge Alpha", "endpoint": "http://localhost:8111/respond"},
      {"name": "Judge Beta", "endpoint": "http://localhost:8112/respond"},
      {"name": "Judge Gamma", "endpoint": "http://localhost:8113/respond"},
      {"name": "Judge Delta", "endpoint": "http://localhost:8114/respond"},
      {"name": "Judge Epsilon", "endpoint": "http://localhost:8115/respond"}
    ],
    "host": {"name": "Mrs. Stellar", "endpoint": "http://localhost:8010/host/respond"},
    "options": {
      "max_cross_questions": 5,
      "max_freeform_rounds": 10,
      "request_timeout_seconds": 45
    }
  }'
```

The JSON response bundles the full transcript (`transcript`), host interludes (`interludes`), stage assignments (`assignments`), and judge verdicts (`judge_votes`).

## Using The Control Room UI
- The UI has four tabs: **训练主持人、训练辩手、训练裁判、运行辩论赛**. The first three manage personas and credentials; the last tab drives debates.
- `app.js` handles tab switching, persona CRUD via `/api/personas`, judge presets via `/api/judges`, debate launches (`/api/debate/start`), and saving (`/api/debate/save`).
- “生成的 API Endpoint” banners show the exact URL the orchestrator will call. Use the copy/apply buttons to avoid manual typing.
- Enter the topic plus one host, two debaters, and ≥5 judges (endpoints can be either auto-hosted personas or any external services). Click “开始辩论” to run or “保存本场辩论” afterward to archive JSON under `saved_debates/`.
- Static assets live under `web/static/`; edit them and refresh the browser (no extra build step).

## Configuring Participant APIs
All roles speak the same basic contract: a `POST` endpoint that accepts
```json
{
  "prompt": "...",
  "context": {...},
  "client": {"name": "Display name"},
  "tags": {... optional ...}
}
```
and returns
```json
{
  "content": "LLM reply string",
  "metadata": {... optional diagnostics ...}
}
```

### Debaters
1. Use `host_service/debater_api.py` as the reference implementation. It shows how to read the debate context, build a message list, and call DeepSeek chat models.
2. To create a new persona, copy the module, adjust `SYSTEM_PROMPT`, change provider-specific environment variables (`DEEPSEEK_API_URL`, `DEEPSEEK_MODEL`, etc.), and expose it with a FastAPI `@app.post("/<persona>/respond")` route.
3. Deploy each debater service behind its own port or host. Register the endpoint URL in the UI or in the `/api/debate/start` payload.

### Host
1. `host_service/host_api.py` demonstrates the host workflow using DeepSeek Chat. The orchestrator calls whatever URL you provide as the host endpoint.
2. Adapt the host by altering the long-format `SYSTEM_PROMPT`, tweaking temperature defaults via `DEEPSEEK_TEMPERATURE`, or switching to another model provider.
3. Ensure the route returns concise stage introductions because the UI prints host interludes verbatim.

### Judges
1. Judge personas live in `host_service/judges/` and all import tooling from `judge_common.py`, which builds the scoring schema and handles DeepSeek Reasoner calls.
2. To author a new judge, create a module with a `PersonaConfig` describing weights, introduction text, and optional system notes, then instantiate `build_app(config)` from `judge_common`.
3. Each judge must return valid `JudgeOutput v1` JSON in the `content` field; the orchestrator parses and aggregates the results automatically.

### Mock Services
`examples/mock_participant.py` accepts environment variables `MOCK_ROLE` (`debater`, `judge`, or `host`) and `MOCK_PERSONA` to simulate responses. Use it when experimenting without live LLM credentials.

## Live Timeline Streaming
- `POST /api/debate/stream` now streams newline-delimited `data: {...}` events (Server-Sent Events compatible). Each event includes a `type` field (`host_interlude`, `debate_turn`, `judge_vote`, `complete`, `error`) plus the relevant payload.
- A new `assignments` event is emitted before the first speech so the UI (or your own client) can display which persona drew the affirmative/negative roles in real time.
- The browser UI consumes this stream to render host banter, speeches, and judge ballots in real time, so you can watch the debate unfold instead of waiting for the final `DebateResponse`.
- You can still call `/api/debate/start` for the legacy “run to completion” behaviour if you prefer batch processing or scripting.

## Saving Debate Results
- When you click “保存本场辩论” in the UI or call `/api/debate/save`, the backend writes a JSON snapshot under `saved_debates/<timestamp>_<slug>.json`.
- `SaveDebateRequest` in `app/debate/models.py` documents the payload if you want to script exports directly.

## Extending The Arena
- Add timers, speech length enforcement, or localisation by evolving `DebateOptions` in `app/debate/models.py`.
- Hook transcripts into observability pipelines by modifying `_write_debate` in `app/main.py`.
- Introduce new phases or scoring logic by editing `DebateOrchestrator` and `script_templates`.
- Swap out providers or add caching layers by amending `LLMClient` in `app/debate/llm_client.py`.
