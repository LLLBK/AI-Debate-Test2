from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.staticfiles import StaticFiles

from .debate.models import (
    DebateRequest,
    DebateResponse,
    SaveDebateRequest,
    SaveDebateResponse,
)
from .debate.orchestrator import DebateOrchestrator

app = FastAPI(
    title="AI Debate Arena",
    description="Coordinate multi-agent LLM debates with host interludes and judge voting.",
    version="0.1.0",
)

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "web" / "static"
SAVED_DIR = BASE_DIR / "saved_debates"

DEFAULT_JUDGE_HOST = os.getenv("JUDGE_BASE_URL", "http://localhost")
JUDGE_PRESETS = [
    {
        "name": "逻辑学教授型评委",
        "persona": "logic_professor",
        "description": "注重论证结构有效性的严谨裁判。",
        "endpoint": f"{DEFAULT_JUDGE_HOST}:8111/respond",
    },
    {
        "name": "法官仲裁型评委",
        "persona": "arbiter",
        "description": "强调举证责任与程序规范的 record-only 评委。",
        "endpoint": f"{DEFAULT_JUDGE_HOST}:8112/respond",
    },
    {
        "name": "数据实证派评委",
        "persona": "empiricist",
        "description": "偏好数据与研究支持，严防相关因果混淆。",
        "endpoint": f"{DEFAULT_JUDGE_HOST}:8113/respond",
    },
    {
        "name": "辩论教练型评委",
        "persona": "coach",
        "description": "聚焦攻防策略与资源分配效率。",
        "endpoint": f"{DEFAULT_JUDGE_HOST}:8114/respond",
    },
    {
        "name": "修辞传播型评委",
        "persona": "rhetoric",
        "description": "关注修辞、叙事结构与可传播度。",
        "endpoint": f"{DEFAULT_JUDGE_HOST}:8115/respond",
    },
]

SAVED_DIR.mkdir(parents=True, exist_ok=True)
if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(STATIC_DIR), html=True), name="ui")


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ready", "message": "AI Debate Arena is online."}


@app.get("/api/judges")
async def list_judge_presets() -> list[dict[str, str]]:
    return JUDGE_PRESETS


@app.post("/api/debate/start", response_model=DebateResponse)
async def start_debate(request: DebateRequest) -> DebateResponse:
    try:
        orchestrator = DebateOrchestrator(request)
        return await orchestrator.run()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
