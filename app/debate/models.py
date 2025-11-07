from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl


class DebateRole(str, Enum):
    AFFIRMATIVE = "affirmative"
    NEGATIVE = "negative"
    HOST = "host"
    JUDGE = "judge"


class ParticipantConfig(BaseModel):
    name: str = Field(..., description="Display name for the participant.")
    endpoint: HttpUrl = Field(..., description="HTTP endpoint accepting POST requests.")


class DebateOptions(BaseModel):
    max_cross_questions: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of questions allowed during each cross-examination block.",
    )
    max_freeform_rounds: int = Field(
        default=10,
        ge=1,
        le=12,
        description="Maximum number of free debate rounds (each has two turns).",
    )
    request_timeout_seconds: int = Field(
        default=45,
        ge=5,
        le=120,
        description="Timeout for each LLM API call.",
    )


class DebateRequest(BaseModel):
    topic: str
    debaters: List[ParticipantConfig] = Field(
        ...,
        min_items=2,
        max_items=2,
        description="Exactly two debaters that will be randomly assigned to sides.",
    )
    judges: List[ParticipantConfig] = Field(
        ...,
        min_items=5,
        max_items=12,
        description="At least five judges (up to 12) that will cast votes.",
    )
    host: ParticipantConfig
    options: DebateOptions = Field(default_factory=DebateOptions)
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional opaque payload echoed back in responses."
    )


class DebateTurn(BaseModel):
    stage: str
    speaker_role: DebateRole
    speaker_name: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HostInterlude(BaseModel):
    stage: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JudgeVote(BaseModel):
    judge_name: str
    vote: Literal["affirmative", "negative", "tie"]
    rationale: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DebateResponse(BaseModel):
    topic: str
    assignments: Dict[DebateRole, Union[str, List[str]]]
    transcript: List[DebateTurn]
    interludes: List[HostInterlude]
    judge_votes: List[JudgeVote]
    metadata: Optional[Dict[str, Any]] = None


class SaveDebateRequest(BaseModel):
    debate: DebateResponse
    filename: Optional[str] = Field(
        default=None, description="Optional filename (without extension) for saving."
    )


class SaveDebateResponse(BaseModel):
    path: str = Field(..., description="Relative path to the saved debate file.")
