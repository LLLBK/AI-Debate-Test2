from __future__ import annotations

import hashlib
import json
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from host_service.judges import (
    arbiter as preset_arbiter,
    coach as preset_coach,
    empiricist as preset_empiricist,
    logic_professor as preset_logic_professor,
    rhetoric as preset_rhetoric,
)

from .debate.models import (
    DebateRequest,
    DebateResponse,
    SaveDebateRequest,
    SaveDebateResponse,
)
from .debate.orchestrator import DebateOrchestrator
from .personas.models import (
    PersonaCatalog,
    PersonaDetail,
    PersonaInvocationRequest,
    PersonaSummary,
    PersonaType,
    PersonaUpsertRequest,
)
from .personas.runtime import run_persona
from .personas.storage import PersonaStorage

app = FastAPI(
    title="AI Debate Arena",
    description="Coordinate multi-agent LLM debates with host interludes and judge voting.",
    version="0.1.0",
)

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "web" / "static"
SAVED_DIR = BASE_DIR / "saved_debates"
PERSONA_DIR = BASE_DIR / "personas"
PERSONA_STORE = PersonaStorage(PERSONA_DIR / "registry.json")
PUBLIC_BASE_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8000")

PRESET_JUDGE_APPS = {
    "logic_professor": preset_logic_professor.app,
    "arbiter": preset_arbiter.app,
    "empiricist": preset_empiricist.app,
    "coach": preset_coach.app,
    "rhetoric": preset_rhetoric.app,
}


def _preset_judge_endpoint(slug: str) -> str:
    origin = PUBLIC_BASE_URL.rstrip("/")
    return f"{origin}/api/presets/judges/{slug}/respond"


JUDGE_PRESETS = [
    {
        "name": "逻辑学教授型评委",
        "persona": "logic_professor",
        "description": "注重论证结构有效性的严谨裁判。",
        "endpoint": _preset_judge_endpoint("logic_professor"),
    },
    {
        "name": "法官仲裁型评委",
        "persona": "arbiter",
        "description": "强调举证责任与程序规范的 record-only 评委。",
        "endpoint": _preset_judge_endpoint("arbiter"),
    },
    {
        "name": "数据实证派评委",
        "persona": "empiricist",
        "description": "偏好数据与研究支持，严防相关因果混淆。",
        "endpoint": _preset_judge_endpoint("empiricist"),
    },
    {
        "name": "辩论教练型评委",
        "persona": "coach",
        "description": "聚焦攻防策略与资源分配效率。",
        "endpoint": _preset_judge_endpoint("coach"),
    },
    {
        "name": "修辞传播型评委",
        "persona": "rhetoric",
        "description": "关注修辞、叙事结构与可传播度。",
        "endpoint": _preset_judge_endpoint("rhetoric"),
    },
]

SAVED_DIR.mkdir(parents=True, exist_ok=True)
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")

for slug, judge_app in PRESET_JUDGE_APPS.items():
    app.mount(f"/api/presets/judges/{slug}", judge_app)


def _persona_endpoint(persona_type: PersonaType, persona_id: str) -> str:
    origin = PUBLIC_BASE_URL.rstrip("/")
    return f"{origin}/api/personas/{persona_type.value}/{persona_id}/respond"


def _persona_summary(persona) -> PersonaSummary:
    return PersonaSummary(
        id=persona.id,
        persona_type=persona.persona_type,
        name=persona.name,
        endpoint=_persona_endpoint(persona.persona_type, persona.id),
        model=persona.llm.model,
        temperature=persona.llm.temperature,
    )


def _persona_detail(persona) -> PersonaDetail:
    data = persona.model_dump()
    data["endpoint"] = _persona_endpoint(persona.persona_type, persona.id)
    return PersonaDetail(**data)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ready", "message": "AI Debate Arena is online."}


@app.get("/api/judges")
async def list_judge_presets() -> list[dict[str, str]]:
    return JUDGE_PRESETS


@app.get("/api/personas", response_model=PersonaCatalog)
async def list_personas() -> PersonaCatalog:
    hosts = [_persona_summary(item) for item in PERSONA_STORE.list(PersonaType.HOST)]
    debaters = [_persona_summary(item) for item in PERSONA_STORE.list(PersonaType.DEBATER)]
    judges = [_persona_summary(item) for item in PERSONA_STORE.list(PersonaType.JUDGE)]
    return PersonaCatalog(hosts=hosts, debaters=debaters, judges=judges)


@app.post("/api/personas/{persona_type}", response_model=PersonaDetail, status_code=201)
async def create_persona(persona_type: PersonaType, payload: PersonaUpsertRequest) -> PersonaDetail:
    persona = PERSONA_STORE.upsert(persona_type, payload)
    return _persona_detail(persona)


@app.put("/api/personas/{persona_type}/{persona_id}", response_model=PersonaDetail)
async def update_persona(
    persona_type: PersonaType,
    persona_id: str,
    payload: PersonaUpsertRequest,
) -> PersonaDetail:
    try:
        persona = PERSONA_STORE.upsert(persona_type, payload, persona_id=persona_id)
    except KeyError as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=404, detail="Persona not found.") from exc
    return _persona_detail(persona)


@app.get("/api/personas/{persona_type}/{persona_id}", response_model=PersonaDetail)
async def fetch_persona(persona_type: PersonaType, persona_id: str) -> PersonaDetail:
    try:
        persona = PERSONA_STORE.get(persona_type, persona_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Persona not found.") from exc
    return _persona_detail(persona)


@app.delete("/api/personas/{persona_type}/{persona_id}", status_code=204, response_class=Response)
async def delete_persona(persona_type: PersonaType, persona_id: str) -> Response:
    try:
        PERSONA_STORE.delete(persona_type, persona_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Persona not found.") from exc
    return Response(status_code=204)


@app.post("/api/personas/{persona_type}/{persona_id}/respond")
async def persona_runtime(
    persona_type: PersonaType,
    persona_id: str,
    payload: PersonaInvocationRequest,
) -> dict[str, object]:
    try:
        persona = PERSONA_STORE.get(persona_type, persona_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Persona not found.") from exc

    content, metadata = await run_persona(persona, payload.prompt, payload.context)
    metadata["client_name"] = payload.client.get("name") if payload.client else None
    return {"content": content, "metadata": metadata}


@app.post("/api/debate/start", response_model=DebateResponse)
async def start_debate(request: DebateRequest) -> DebateResponse:
    try:
        orchestrator = DebateOrchestrator(request)
        return await orchestrator.run()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/debate/stream")
async def stream_debate(request: DebateRequest) -> StreamingResponse:
    queue: asyncio.Queue[Optional[dict[str, object]]] = asyncio.Queue()

    async def event_callback(event_type: str, payload: dict[str, object]) -> None:
        await queue.put({"type": event_type, "payload": payload})

    orchestrator = DebateOrchestrator(request, event_callback=event_callback)

    async def run_debate() -> None:
        try:
            await orchestrator.run()
        except Exception as exc:  # noqa: BLE001
            message = str(exc).strip()
            if not message:
                message = repr(exc)
            await queue.put({"type": "error", "payload": {"message": message}})
        finally:
            await queue.put(None)

    asyncio.create_task(run_debate())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                break
            encoded = jsonable_encoder(item)
            yield f"data: {json.dumps(encoded, ensure_ascii=False)}\n\n"

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


def _slugify(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in value.lower())
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "debate"


def _build_filename(user_filename: Optional[str], topic: str) -> str:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    base = user_filename or _slugify(topic)[:48]
    base = _slugify(base)[:48]
    if not base:
        digest = hashlib.sha1(topic.encode("utf-8")).hexdigest()[:8]
        base = f"debate-{digest}"
    return f"{timestamp}_{base}.json"


def _write_debate(payload: SaveDebateRequest) -> Path:
    data = jsonable_encoder(payload.debate)
    data["saved_at_utc"] = datetime.utcnow().isoformat() + "Z"
    filename = _build_filename(payload.filename, payload.debate.topic)
    path = SAVED_DIR / filename
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return path


@app.post("/api/debate/save", response_model=SaveDebateResponse)
async def save_debate(payload: SaveDebateRequest) -> SaveDebateResponse:
    try:
        path = _write_debate(payload)
        try:
            relative_path = path.relative_to(BASE_DIR)
        except ValueError:
            relative_path = path
        return SaveDebateResponse(path=str(relative_path))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
