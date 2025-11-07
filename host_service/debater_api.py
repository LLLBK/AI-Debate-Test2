from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Debater LLM",
    description="Logic-focused debater persona powered by OpenAI gpt-5-mini.",
    version="1.0.0",
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个重视逻辑的辩手，你正在参加一场辩论赛。"""

OPENAI_API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


class DebaterRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = Field(default_factory=dict)
    client: Dict[str, Any]
    tags: Optional[Dict[str, Any]] = None


class DebaterResponse(BaseModel):
    content: str = Field(..., description="The debater's reply.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _format_context(context: Dict[str, Any]) -> str:
    if not context:
        return ""

    ordered_keys = ["stage", "topic", "role", "side", "round", "turn", "opponent"]
    lines: List[str] = []

    for key in ordered_keys:
        if key in context and context[key] is not None:
            lines.append(f"{key}: {context[key]}")

    extra = {k: v for k, v in context.items() if k not in ordered_keys}
    for key, value in extra.items():
        if value is not None:
            lines.append(f"{key}: {value}")

    return "\n".join(lines)


async def _call_openai(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("Missing OPENAI_API_KEY environment variable.")
        raise HTTPException(status_code=500, detail="OpenAI API key is not configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
    }

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(OPENAI_API_URL, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            logger.exception("OpenAI API request failed.")
            raise HTTPException(status_code=502, detail=f"OpenAI API request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text
        logger.error("OpenAI API returned error %s: %s", response.status_code, detail)
        raise HTTPException(status_code=response.status_code, detail="OpenAI API error: " + detail)

    return response.json()


@app.post("/debater/respond", response_model=DebaterResponse)
async def debater_reply(request: DebaterRequest) -> DebaterResponse:
    context_block = _format_context(request.context)

    sections: List[str] = []
    if context_block:
        sections.append(context_block)
    sections.append(request.prompt)

    user_message = "\n\n".join(section for section in sections if section)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message or "依据赛制进行辩论发言。"},
    ]

    api_result = await _call_openai(messages)

    try:
        choice = api_result["choices"][0]
        content = choice["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        logger.exception("Unexpected OpenAI API payload: %s", api_result)
        raise HTTPException(status_code=502, detail="OpenAI API returned an unexpected payload.") from exc

    metadata = {
        "model": OPENAI_MODEL,
        "usage": api_result.get("usage"),
        "prompt_id": api_result.get("id"),
        "stage": request.context.get("stage"),
        "role": request.context.get("role"),
    }
    return DebaterResponse(content=content, metadata=metadata)
