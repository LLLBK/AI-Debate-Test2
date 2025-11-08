from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEEPSEEK_API_URL = os.getenv(
    "DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"
)
DEEPSEEK_REASONER_MODEL = os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner")
DEFAULT_TEMPERATURE = float(os.getenv("DEEPSEEK_JUDGE_TEMPERATURE", "0.15"))

JUDGE_OUTPUT_SCHEMA = (
    os.getenv(
        "JUDGE_OUTPUT_V1_SCHEMA",
        """
{
  "schema": "JudgeOutput",
  "version": "v1",
  "winner": "<affirmative|negative|tie>",
  "scores": {
    "affirmative": {
      "logic": "<0-10 number>",
      "responsiveness": "<0-10 number>",
      "clarity": "<0-10 number>",
      "evidence": "<0-10 number>",
      "rule_adherence": "<0-10 number>",
      "style": "<0-10 number>",
      "strategy": "<0-10 number>"
    },
    "negative": {
      "logic": "<0-10 number>",
      "responsiveness": "<0-10 number>",
      "clarity": "<0-10 number>",
      "evidence": "<0-10 number>",
      "rule_adherence": "<0-10 number>",
      "style": "<0-10 number>",
      "strategy": "<0-10 number>"
    }
  },
  "weighted_scores": {
    "affirmative": "<0-100 integer>",
    "negative": "<0-100 integer>",
    "margin": "<affirmative_total - negative_total integer>"
  },
  "summary": {
    "overall": "2-3 sentences explaining the decisive factors (no hidden-chain leakage).",
    "affirmative_highlights": [
      "Concise bullet on the affirmative's strengths"
    ],
    "negative_highlights": [
      "Concise bullet on the negative's strengths"
    ]
  },
  "violations": [
    {
      "side": "<affirmative|negative|both>",
      "category": "rule_adherence or other impacted dimension",
      "description": "Brief note on the infraction"
    }
  ]
}
        """,
    )
    .strip()
    .replace("\t", "    ")
)


class JudgeRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = Field(default_factory=dict)
    client: Dict[str, Any]
    tags: Optional[Dict[str, Any]] = None


class JudgeResponse(BaseModel):
    content: str = Field(..., description="JudgeOutput v1 JSON payload.")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PersonaConfig(BaseModel):
    persona_id: str
    display_name: str
    introduction: str
    weights: Sequence[Tuple[str, float]]
    temperature: Optional[float] = None
    system_notes: Optional[str] = None


def _format_context(context: Dict[str, Any]) -> str:
    if not context:
        return ""

    ordered = [
        "stage",
        "topic",
        "round",
        "turn",
        "speaker",
        "opponent",
        "highlights",
    ]
    lines: List[str] = []
    for key in ordered:
        value = context.get(key)
        if value is None:
            continue
        if key == "highlights" and isinstance(value, (list, tuple)):
            highlights = " | ".join(str(item) for item in value if item)
            if highlights:
                lines.append(f"{key}: {highlights}")
        else:
            lines.append(f"{key}: {value}")

    extra = {
        k: v
        for k, v in context.items()
        if k not in ordered and v is not None
    }
    for key, value in extra.items():
        lines.append(f"{key}: {value}")

    return "\n".join(lines)


def _build_system_prompt(config: PersonaConfig) -> str:
    weight_lines = "\n".join(
        f"- {metric} {weight:.2f}" for metric, weight in config.weights
    )
    notes = config.system_notes.strip() if config.system_notes else ""
    base_prompt = (
        f"{config.introduction.strip()}\n\n"
        "坚持“文本记录唯一可信来源”，只依据提供的内容评分。"
        " 可在内部进行充分推理，但严禁在输出中泄露推理过程或思维链。\n"
        "评价维度与权重（总和=1）：\n"
        f"{weight_lines}\n\n"
        "计分流程：\n"
        "1. 各分项以0-10分打分，可用小数表示半分。\n"
        "2. 依据权重计算加权平均，并×10 换算为0-100的总分，取整。\n"
        "3. 若双方总分差≤2且证据相互抵消，可判定为tie。\n\n"
        "如发现程序或赛制违规，请在violations中注明并在相关维度扣分。\n"
        "禁止输出除JSON以外的任何字符（包括前后缀说明、Markdown等）。\n"
        "Important: output must be a valid json object (json). No extra text.\n"
        "严格输出以下 JudgeOutput v1 JSON 结构，确保字段完整且取值合法：\n"
        f"{JUDGE_OUTPUT_SCHEMA}"
    )
    if notes:
        base_prompt = f"{base_prompt}\n\n补充注意事项：\n{notes}"
    return base_prompt


async def _call_deepseek(
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("Missing DEEPSEEK_API_KEY environment variable.")
        raise HTTPException(
            status_code=500, detail="DeepSeek API key is not configured."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": DEEPSEEK_REASONER_MODEL,
        "messages": messages,
        "temperature": temperature if temperature is not None else DEFAULT_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }

    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                DEEPSEEK_API_URL, headers=headers, json=payload
            )
        except httpx.HTTPError as exc:
            logger.exception("DeepSeek API request failed.")
            raise HTTPException(
                status_code=502, detail=f"DeepSeek API request failed: {exc}"
            ) from exc

    if response.status_code >= 400:
        detail = response.text
        logger.error(
            "DeepSeek API returned error %s: %s", response.status_code, detail
        )
        raise HTTPException(
            status_code=response.status_code,
            detail="DeepSeek API error: " + detail,
        )

    return response.json()


def _prepare_messages(system_prompt: str, request: JudgeRequest) -> List[Dict[str, str]]:
    context_block = _format_context(request.context)

    user_sections: List[str] = []
    if context_block:
        user_sections.append(f"比赛上下文:\n{context_block}")
    if request.prompt:
        user_sections.append(f"评审材料:\n{request.prompt}")
    user_sections.append("请基于以上内容完成评分并输出JudgeOutput v1。")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(user_sections)},
    ]


def _normalise_json_payload(raw_text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.exception("Judge model returned non-JSON content: %s", raw_text)
        raise HTTPException(
            status_code=502,
            detail=f"Judge response could not be parsed as JSON: {exc.msg}",
        ) from exc

    if not isinstance(parsed, dict):
        logger.error("Judge JSON payload is not an object: %s", parsed)
        raise HTTPException(
            status_code=502, detail="Judge response JSON must be an object."
        )
    return parsed


def build_judge_app(config: PersonaConfig) -> FastAPI:
    system_prompt = _build_system_prompt(config)
    app = FastAPI(
        title=f"Debate Judge · {config.display_name}",
        description=f"Persona: {config.display_name} powered by DeepSeek Reasoner.",
        version="1.0.0",
    )

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok", "persona_id": config.persona_id}

    @app.get("/meta")
    async def meta() -> Dict[str, Any]:
        return {
            "persona_id": config.persona_id,
            "display_name": config.display_name,
            "weights": list(config.weights),
            "model": DEEPSEEK_REASONER_MODEL,
            "temperature": config.temperature or DEFAULT_TEMPERATURE,
        }

    @app.post("/respond", response_model=JudgeResponse)
    async def judge_reply(request: JudgeRequest) -> JudgeResponse:
        messages = _prepare_messages(system_prompt, request)
        api_result = await _call_deepseek(messages, temperature=config.temperature)

        try:
            choice = api_result["choices"][0]
            message = choice["message"]
            content = message.get("content", "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            logger.exception("Unexpected DeepSeek API payload: %s", api_result)
            raise HTTPException(
                status_code=502,
                detail="DeepSeek API returned an unexpected payload.",
            ) from exc

        parsed = _normalise_json_payload(content)
        serialised = json.dumps(parsed, ensure_ascii=False)

        metadata = {
            "persona_id": config.persona_id,
            "persona_name": config.display_name,
            "weights": list(config.weights),
            "model": DEEPSEEK_REASONER_MODEL,
            "usage": api_result.get("usage"),
            "prompt_id": api_result.get("id"),
            "schema": parsed.get("schema"),
            "version": parsed.get("version"),
            "weighted_scores": parsed.get("weighted_scores"),
            "violations": parsed.get("violations"),
        }
        return JudgeResponse(content=serialised, metadata=metadata)

    return app


__all__ = [
    "JudgeRequest",
    "JudgeResponse",
    "PersonaConfig",
    "build_judge_app",
]
