from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="Debate Host LLM",
    description="LLM-powered host persona orchestrating debate stages with Deepseek Chat.",
    version="1.0.0",
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个辩论比赛的主持人。这场辩论赛的赛程如下：主持人宣布辩题后，两个LLM随机分到正方和反方。
首先由双方各自发言陈词。
然后进入质询环节，质询者一次只能提一个问题，被质询者不可反问，只能简洁明确地回答，质询者最多可以质询五次。首先由正方质询反方，再由反方质询正方。
然后进入自由辩论环节，正反方辩手轮流进行简短的发言，可以质疑，也可以回应，也可以陈词，自由辩论提倡积极交锋。一方发言完毕，另一方必须紧接着发言，不可停顿，这称为一个回合。自由辩论限制10个回合以内。由正方先开始。
然后，双方辩手作结辩陈词。由反方先开始。
然后，由五个评委投票出胜者，五个评委均需给出投票理由。
在每个环节中间，主持人都要进行简单且幽默的串场，串场内容需要与刚刚的环节中的内容有关。
你要确保比赛按照上述赛制顺利进行，在比赛开始时要宣读比赛规则和辩题，在比赛进行中要提醒进行到下一环节，在每个环节中间还要进行简单幽默的串场，比赛结束后要提醒评委开始投票和评价，最后还要做结语，恭喜获胜者、鼓励失败者、感谢评委和双方辩手。
保持主持风格专业、热情、幽默，发言要紧凑清晰，必要时总结上一环节亮点并引导下一环节。"""

DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEFAULT_TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.6"))


class HostRequest(BaseModel):
    prompt: str
    context: Dict[str, Any]
    client: Dict[str, Any]
    tags: Optional[Dict[str, Any]] = None


class HostResponse(BaseModel):
    content: str = Field(..., description="The host's scripted line.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _format_context_block(context: Dict[str, Any]) -> str:
    stage = context.get("stage")
    topic = context.get("topic")
    highlights = context.get("highlights") or []
    judges = context.get("judges")
    round_info = context.get("round_info") or context.get("progress")

    lines: List[str] = []
    if stage:
        lines.append(f"当前赛程环节: {stage}")
    if topic:
        lines.append(f"辩题: {topic}")
    if round_info:
        lines.append(f"赛程进度: {round_info}")
    if highlights:
        cleaned = [h for h in highlights if h]
        if cleaned:
            lines.append("上一环节亮点: " + " | ".join(cleaned[:5]))
    if judges:
        lines.append(f"评委信息: {judges}")

    extra_keys = {k: v for k, v in context.items() if k not in {"stage", "topic", "highlights", "judges", "round_info", "progress"}}
    for key, value in extra_keys.items():
        lines.append(f"{key}: {value}")

    return "\n".join(lines)


async def _call_deepseek(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("Missing DEEPSEEK_API_KEY environment variable.")
        raise HTTPException(status_code=500, detail="Deepseek API key is not configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": DEFAULT_TEMPERATURE,
    }

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            logger.exception("Deepseek API request failed.")
            raise HTTPException(status_code=502, detail=f"Deepseek API request failed: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text
        logger.error("Deepseek API returned error %s: %s", response.status_code, detail)
        raise HTTPException(status_code=response.status_code, detail="Deepseek API error: " + detail)

    return response.json()


@app.post("/host/respond", response_model=HostResponse)
async def host_reply(request: HostRequest) -> HostResponse:
    context_block = _format_context_block(request.context)
    user_sections = []
    if context_block:
        user_sections.append(context_block)
    if request.prompt:
        user_sections.append(f"执行以下主持指令:\n{request.prompt}")
    user_message = "\n\n".join(user_sections) if user_sections else "依据规则进行主持发言。"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    api_result = await _call_deepseek(messages)

    try:
        choice = api_result["choices"][0]
        content = choice["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        logger.exception("Unexpected Deepseek API payload: %s", api_result)
        raise HTTPException(status_code=502, detail="Deepseek API returned an unexpected payload.") from exc

    metadata = {
        "stage": request.context.get("stage"),
        "host_persona": "deepseek_chat_moderator",
        "model": DEEPSEEK_MODEL,
        "usage": api_result.get("usage"),
        "prompt_id": api_result.get("id"),
    }
    return HostResponse(content=content, metadata=metadata)
