from __future__ import annotations

import os
import random
import textwrap
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

PERSONA = os.getenv("MOCK_PERSONA", "generalist thinker")
ROLE = os.getenv("MOCK_ROLE", "debater")
TONE_CHOICES = {
    "debater": [
        "assertive yet approachable",
        "methodical and evidence-driven",
        "fiery and inspirational",
    ],
    "judge": [
        "impartial and concise",
        "empathetic but firm",
        "strategic and analytical",
    ],
}

app = FastAPI(
    title=f"Mock Participant ({PERSONA})",
    description="Lightweight mock endpoint for local testing.",
    version="0.1.0",
)


class LLMRequest(BaseModel):
    prompt: str
    context: Dict[str, Any]
    client: Dict[str, Any]
    tags: Optional[Dict[str, Any]] = None


class LLMResponse(BaseModel):
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


def _summarise_prompt(prompt: str, limit: int = 140) -> str:
    compact = " ".join(prompt.split())
    return compact[:limit]


def _build_debater_line(req: LLMRequest) -> str:
    stage = req.context.get("stage", "unspecified stage")
    topic = req.context.get("topic", "the motion at hand")
    tone = random.choice(TONE_CHOICES.get("debater", ["thoughtful"]))
    return textwrap.dedent(
        f"""
        ({PERSONA}, {tone}) Stage {stage}: Regarding {topic}, my stance is crystal clear—
        I'm combining logic, a dash of rhetoric, and references from the prompt: {_summarise_prompt(req.prompt)}.
        """
    ).strip()


def _build_judge_line(req: LLMRequest) -> str:
    tone = random.choice(TONE_CHOICES.get("judge", ["measured"]))
    if "Vote" in req.prompt:
        vote = random.choice(["affirmative", "negative"])
        rationale = (
            "Precision in cross-examination impressed me."
            if vote == "affirmative"
            else "The opposing side undermined the motion's feasibility."
        )
        return f"Vote: {vote}\nRationale: ({tone}) {rationale}"
    return f"({tone}) I abstain from voting due to insufficient instructions."


@app.post("/respond", response_model=LLMResponse)
async def respond(req: LLMRequest) -> LLMResponse:
    if ROLE.lower() == "judge":
        content = _build_judge_line(req)
    else:
        content = _build_debater_line(req)

    return LLMResponse(
        content=content,
        metadata={
            "persona": PERSONA,
            "role": ROLE,
            "prompt_excerpt": _summarise_prompt(req.prompt, limit=80),
        },
    )

