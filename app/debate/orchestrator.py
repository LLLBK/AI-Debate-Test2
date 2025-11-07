from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Union

from . import script_templates
from .llm_client import LLMClient
from .models import (
    DebateOptions,
    DebateRequest,
    DebateResponse,
    DebateRole,
    DebateTurn,
    HostInterlude,
    JudgeVote,
    ParticipantConfig,
)


@dataclass
class SideAssignment:
    role: DebateRole
    config: ParticipantConfig
    client: LLMClient


class DebateOrchestrator:
    def __init__(self, request: DebateRequest) -> None:
        self.request = request
        options = request.options

        shuffled = request.debaters[:]
        random.shuffle(shuffled)
        self.affirmative = SideAssignment(
            role=DebateRole.AFFIRMATIVE,
            config=shuffled[0],
            client=self._build_client(shuffled[0], options),
        )
        self.negative = SideAssignment(
            role=DebateRole.NEGATIVE,
            config=shuffled[1],
            client=self._build_client(shuffled[1], options),
        )

        self.judges = [
            SideAssignment(
                role=DebateRole.JUDGE,
                config=judge,
                client=self._build_client(judge, options),
            )
            for judge in request.judges
        ]

        self.host_client = self._build_client(request.host, options)
        self.options = options
        self.transcript: List[DebateTurn] = []
        self.interludes: List[HostInterlude] = []
        self.judge_votes: List[JudgeVote] = []

    async def run(self) -> DebateResponse:
        await self._host_interlude(
            stage="introduction",
            instruction="Welcome the audience, announce the motion, and tease the upcoming debate.",
            highlights=[
                f"Motion: {self.request.topic}",
                f"Participants: {self.affirmative.config.name} vs {self.negative.config.name}",
            ],
        )

        await self._handle_opening_statements()

        await self._host_interlude(
            stage="pre_cross_examination",
            instruction="React to the opening statements with a witty remark, foreshadow cross-examination.",
            highlights=[
                self._last_turn_summary(self.affirmative.config.name),
                self._last_turn_summary(self.negative.config.name),
            ],
        )

        await self._handle_cross_examination(attacker=self.affirmative, defender=self.negative, label="affirmative_cross")

        await self._host_interlude(
            stage="mid_cross_examination",
            instruction="Comment on the questioning so far and set up the perspective shift.",
            highlights=self._recent_turns_summary(limit=4),
        )

        await self._handle_cross_examination(attacker=self.negative, defender=self.affirmative, label="negative_cross")

        await self._host_interlude(
            stage="pre_free_debate",
            instruction="Encourage energetic exchanges and make a playful observation about the debate heat.",
            highlights=self._recent_turns_summary(limit=4),
        )

        await self._handle_free_debate()

        await self._host_interlude(
            stage="pre_closing",
            instruction="Cue the closing statements with humor and hint at the stakes.",
            highlights=self._recent_turns_summary(limit=4),
        )

        await self._handle_closing_statements()

        await self._host_interlude(
            stage="pre_judging",
            instruction="Address the judges, joke about the tough decision, and transition to deliberation.",
            highlights=self._recent_turns_summary(limit=6),
        )

        await self._handle_judges()

        await self._host_interlude(
            stage="wrap_up",
            instruction="Celebrate the debate, announce the winner, and leave the audience smiling.",
            highlights=self._winner_highlights(),
        )

        assignments: Dict[DebateRole, Union[str, List[str]]] = {
            DebateRole.AFFIRMATIVE: self.affirmative.config.name,
            DebateRole.NEGATIVE: self.negative.config.name,
            DebateRole.HOST: self.request.host.name,
        }
        assignments[DebateRole.JUDGE] = [judge.config.name for judge in self.judges]

        return DebateResponse(
            topic=self.request.topic,
            assignments=assignments,
            transcript=self.transcript,
            interludes=self.interludes,
            judge_votes=self.judge_votes,
            metadata=self.request.metadata,
        )

    async def _handle_opening_statements(self) -> None:
        await self._debaters_statement(
            stage="opening_affirmative",
            side=self.affirmative,
            prompt_builder=script_templates.opening_statement_prompt,
            briefing=[
                "Establish why the motion should be accepted.",
                "Highlight core benefits early.",
            ],
        )

        await self._debaters_statement(
            stage="opening_negative",
            side=self.negative,
            prompt_builder=script_templates.opening_statement_prompt,
            briefing=[
                "Expose vulnerabilities in the motion.",
                "Question feasibility and unintended consequences.",
            ],
        )

    async def _handle_cross_examination(
        self,
        attacker: SideAssignment,
        defender: SideAssignment,
        label: str,
    ) -> None:
        asked: List[str] = []
        answers: List[str] = []
        opponent_highlights = self._collect_highlights(defender.config.name)
        for turn_index in range(self.options.max_cross_questions):
            question_prompt = script_templates.cross_question_prompt(
                side=attacker.role.value,
                topic=self.request.topic,
                previous_questions=asked,
                opponent_highlights=opponent_highlights,
            )
            question, question_meta = await attacker.client.complete(
                question_prompt,
                context={
                    "stage": f"{label}_question",
                    "turn": turn_index + 1,
                    "topic": self.request.topic,
                },
            )
            asked.append(question)
            self.transcript.append(
                DebateTurn(
                    stage=f"{label}_q{turn_index + 1}",
                    speaker_role=attacker.role,
                    speaker_name=attacker.config.name,
                    content=question,
                    metadata=question_meta,
                )
            )

            answer_prompt = script_templates.cross_answer_prompt(
                side=defender.role.value,
                topic=self.request.topic,
                question=question,
                prior_answers=answers,
            )
            answer, answer_meta = await defender.client.complete(
                answer_prompt,
                context={
                    "stage": f"{label}_answer",
                    "turn": turn_index + 1,
                    "topic": self.request.topic,
                },
            )
            answers.append(answer)
            self.transcript.append(
                DebateTurn(
                    stage=f"{label}_a{turn_index + 1}",
                    speaker_role=defender.role,
                    speaker_name=defender.config.name,
                    content=answer,
                    metadata=answer_meta,
                )
            )

    async def _handle_free_debate(self) -> None:
        last_point = self._last_turn_content()
        for round_number in range(1, self.options.max_freeform_rounds + 1):
            affirmative_prompt = script_templates.free_debate_prompt(
                side=self.affirmative.role.value,
                topic=self.request.topic,
                last_opponent_point=last_point,
                round_number=round_number,
            )
            affirmative_reply, aff_meta = await self.affirmative.client.complete(
                affirmative_prompt,
                context={
                    "stage": "free_debate",
                    "round": round_number,
                    "role": self.affirmative.role.value,
                },
            )
            self.transcript.append(
                DebateTurn(
                    stage=f"free_debate_round{round_number}_affirmative",
                    speaker_role=self.affirmative.role,
                    speaker_name=self.affirmative.config.name,
                    content=affirmative_reply,
                    metadata=aff_meta,
                )
            )

            last_point = affirmative_reply

            negative_prompt = script_templates.free_debate_prompt(
                side=self.negative.role.value,
                topic=self.request.topic,
                last_opponent_point=last_point,
                round_number=round_number,
            )
            negative_reply, neg_meta = await self.negative.client.complete(
                negative_prompt,
                context={
                    "stage": "free_debate",
                    "round": round_number,
                    "role": self.negative.role.value,
                },
            )
            self.transcript.append(
                DebateTurn(
                    stage=f"free_debate_round{round_number}_negative",
                    speaker_role=self.negative.role,
                    speaker_name=self.negative.config.name,
                    content=negative_reply,
                    metadata=neg_meta,
                )
            )

            last_point = negative_reply

    async def _handle_closing_statements(self) -> None:
        negative_prompt = script_templates.closing_statement_prompt(
            side=self.negative.role.value,
            topic=self.request.topic,
            key_moments=self._collect_highlights(self.negative.config.name),
        )
        negative_reply, neg_meta = await self.negative.client.complete(
            negative_prompt,
            context={"stage": "closing_negative", "topic": self.request.topic},
        )
        self.transcript.append(
            DebateTurn(
                stage="closing_negative",
                speaker_role=self.negative.role,
                speaker_name=self.negative.config.name,
                content=negative_reply,
                metadata=neg_meta,
            )
        )

        affirmative_prompt = script_templates.closing_statement_prompt(
            side=self.affirmative.role.value,
            topic=self.request.topic,
            key_moments=self._collect_highlights(self.affirmative.config.name),
        )
        affirmative_reply, aff_meta = await self.affirmative.client.complete(
            affirmative_prompt,
            context={"stage": "closing_affirmative", "topic": self.request.topic},
        )
        self.transcript.append(
            DebateTurn(
                stage="closing_affirmative",
                speaker_role=self.affirmative.role,
                speaker_name=self.affirmative.config.name,
                content=affirmative_reply,
                metadata=aff_meta,
            )
        )

    async def _handle_judges(self) -> None:
        transcript_summary = "\n".join(self._recent_turns_summary(limit=12))
        tasks = []
        for judge in self.judges:
            prompt = script_templates.judge_prompt(
                topic=self.request.topic,
                transcript_summary=transcript_summary,
                required_vote="affirmative_or_negative",
            )
            tasks.append(
                judge.client.complete(
                    prompt,
                    context={"stage": "judging", "topic": self.request.topic},
                )
            )

        judge_outputs = await asyncio.gather(*tasks)
        for judge, (content, metadata) in zip(self.judges, judge_outputs):
            vote_line, rationale_line, extra_meta = self._parse_judge_response(content)
            combined_meta = {**metadata}
            combined_meta.update(extra_meta)
            self.judge_votes.append(
                JudgeVote(
                    judge_name=judge.config.name,
                    vote=vote_line,
                    rationale=rationale_line,
                    metadata=combined_meta,
                )
            )

    async def _debaters_statement(
        self,
        stage: str,
        side: SideAssignment,
        prompt_builder,
        briefing: List[str],
    ) -> None:
        prompt = prompt_builder(
            side=side.role.value,
            topic=self.request.topic,
            briefing=briefing,
        )
        reply, metadata = await side.client.complete(
            prompt,
            context={"stage": stage, "topic": self.request.topic},
        )
        self.transcript.append(
            DebateTurn(
                stage=stage,
                speaker_role=side.role,
                speaker_name=side.config.name,
                content=reply,
                metadata=metadata,
            )
        )

    async def _host_interlude(
        self,
        stage: str,
        instruction: str,
        highlights: List[str],
    ) -> None:
        prompt = self._build_host_prompt(stage, instruction, highlights)
        content, metadata = await self.host_client.complete(
            prompt,
            context={
                "stage": stage,
                "topic": self.request.topic,
                "highlights": highlights,
            },
        )
        self.interludes.append(
            HostInterlude(stage=stage, content=content, metadata=metadata)
        )

    def _build_host_prompt(
        self,
        stage: str,
        instruction: str,
        highlights: List[str],
    ) -> str:
        highlight_text = "\n".join(f"- {item}" for item in highlights if item)
        return (
            f"You are the charismatic debate host. Stage: {stage}.\n"
            f"Objective: {instruction}\n"
            f"Keep it under 80 words, inject light humor without derailing the competition.\n"
            f"Highlights to reference:\n{highlight_text}\n"
            "Return a single paragraph."
        )

    def _collect_highlights(self, speaker_name: str, limit: int = 4) -> List[str]:
        highlights = [
            turn.content
            for turn in reversed(self.transcript)
            if turn.speaker_name == speaker_name
        ]
        return highlights[:limit]

    def _last_turn_summary(self, speaker_name: str) -> str:
        for turn in reversed(self.transcript):
            if turn.speaker_name == speaker_name:
                snippet = turn.content
                return f"{speaker_name} just said: {snippet[:120]}"
        return f"{speaker_name} is preparing to speak."

    def _recent_turns_summary(self, limit: int = 6) -> List[str]:
        recent = []
        for turn in reversed(self.transcript):
            label = f"{turn.speaker_name}: {turn.content}"
            recent.append(label[:160])
            if len(recent) >= limit:
                break
        return list(reversed(recent))

    def _last_turn_content(self) -> str:
        if not self.transcript:
            return ""
        return self.transcript[-1].content

    def _parse_judge_response(self, content: str) -> Tuple[str, str, Dict[str, Any]]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            vote, rationale = self._parse_legacy_judge_response(content)
            return vote, rationale, {"format": "legacy_text", "raw_output": content}

        if not isinstance(data, dict):
            vote, rationale = self._parse_legacy_judge_response(content)
            return vote, rationale, {"format": "non_object_json", "raw_output": data}

        winner = str(data.get("winner", "")).lower()
        if winner not in {"affirmative", "negative", "tie"}:
            vote, rationale = self._parse_legacy_judge_response(content)
            return vote, rationale, {"format": "invalid_winner", "raw_output": data}

        summary = ""
        summary_block = data.get("summary")
        if isinstance(summary_block, dict):
            summary = summary_block.get("overall") or ""
        elif isinstance(summary_block, str):
            summary = summary_block

        if not summary:
            summary = "Judge did not provide summary."

        return winner, summary, {
            "format": "judge_output_v1",
            "raw_output": data,
        }

    def _parse_legacy_judge_response(self, content: str) -> Tuple[str, str]:
        lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
        if not lines:
            return "affirmative", "No rationale provided."

        vote_line = lines[0].lower()
        vote = "affirmative"
        if "negative" in vote_line:
            vote = "negative"

        rationale = lines[1] if len(lines) > 1 else "Judge did not elaborate."
        return vote, rationale

    def _winner_highlights(self) -> List[str]:
        affirmative_votes = sum(
            1 for vote in self.judge_votes if vote.vote == "affirmative"
        )
        negative_votes = sum(
            1 for vote in self.judge_votes if vote.vote == "negative"
        )
        tie_votes = sum(1 for vote in self.judge_votes if vote.vote == "tie")

        if affirmative_votes == negative_votes:
            winner_line = "Judges split evenly. Consider calling it a tie or seeking a rematch."
        elif affirmative_votes > negative_votes:
            winner_line = (
                f"Affirmative leads the ballot {affirmative_votes}-{negative_votes}."
            )
        else:
            winner_line = (
                f"Negative leads the ballot {negative_votes}-{affirmative_votes}."
            )

        scoreboard = f"Final tally — Affirmative: {affirmative_votes}, Negative: {negative_votes}"
        if tie_votes:
            scoreboard += f", Ties: {tie_votes}"

        return [winner_line, scoreboard]

    def _build_client(self, config: ParticipantConfig, options: DebateOptions) -> LLMClient:
        return LLMClient(
            name=config.name,
            endpoint=str(config.endpoint),
            timeout=options.request_timeout_seconds,
        )
