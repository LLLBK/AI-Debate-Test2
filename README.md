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
| `app/main.py` | FastAPI entry point exposing `/api/debate/start`, `/api/debate/save`, `/api/judges`, and serving the static UI. |
| `app/debate/orchestrator.py` | Stage-by-stage debate runner that calls each participant via `LLMClient`. |
| `app/debate/script_templates.py` | Prompt builders for openings, cross-examinations, free debate, closings, and judging. |
| `host_service/host_api.py` | DeepSeek-powered host reference implementation responding on `/host/respond`. |
| `host_service/debater_api.py` | Sample OpenAI-backed debater persona reachable at `/debater/respond`. |
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
2. Launch the debate orchestrator (serves REST APIs and the UI):
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
3. Start the host service (choose any reachable port):
   ```bash
   uvicorn host_service.host_api:app --reload --port 8010
   ```
4. Run the bundled judge personas (set `DEEPSEEK_API_KEY` first; each process hosts one persona):
   ```bash
   uvicorn host_service.judges.logic_professor:app --reload --port 8111
   uvicorn host_service.judges.arbiter:app --reload --port 8112
   uvicorn host_service.judges.empiricist:app --reload --port 8113
   uvicorn host_service.judges.coach:app --reload --port 8114
   uvicorn host_service.judges.rhetoric:app --reload --port 8115
   ```
5. (Optional) Spin up mock debaters and judges instead of real LLMs:
   ```bash
   MOCK_PERSONA="Optimistic Architect" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8101
   MOCK_PERSONA="Pragmatic Skeptic" MOCK_ROLE=debater uvicorn examples.mock_participant:app --port 8102
   MOCK_PERSONA="Judge Alpha" MOCK_ROLE=judge uvicorn examples.mock_participant:app --port 8111
   ```
6. Open `http://localhost:8000/ui/` to configure endpoints and drive the match.

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
- The UI served from `web/static/index.html` loads automatically from FastAPI at `/ui`.
- `app.js` fetches preset judges (`GET /api/judges`), manages dynamic form fields, fires `/api/debate/start`, and posts `/api/debate/save`.
- `styles.css` defines the timeline layout, judge grid, and toast notifications.
- Enter topic, two debater endpoints, five or more judge endpoints, and one host endpoint. Click “开始辩论” to launch or “保存本场辩论” after completion to write JSON to `saved_debates/`.
- Modify the UI by editing the static files and restarting the FastAPI server.

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
1. Use `host_service/debater_api.py` as the reference implementation. It shows how to read the debate context, build a message list, and call OpenAI chat models.
2. To create a new persona, copy the module, adjust `SYSTEM_PROMPT`, change provider-specific environment variables (`OPENAI_API_URL`, `OPENAI_MODEL`, etc.), and expose it with a FastAPI `@app.post("/<persona>/respond")` route.
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

## Saving Debate Results
- When you click “保存本场辩论” in the UI or call `/api/debate/save`, the backend writes a JSON snapshot under `saved_debates/<timestamp>_<slug>.json`.
- `SaveDebateRequest` in `app/debate/models.py` documents the payload if you want to script exports directly.

## Extending The Arena
- Add timers, speech length enforcement, or localisation by evolving `DebateOptions` in `app/debate/models.py`.
- Hook transcripts into observability pipelines by modifying `_write_debate` in `app/main.py`.
- Introduce new phases or scoring logic by editing `DebateOrchestrator` and `script_templates`.
- Swap out providers or add caching layers by amending `LLMClient` in `app/debate/llm_client.py`.
