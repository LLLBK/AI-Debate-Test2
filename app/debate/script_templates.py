from __future__ import annotations

from textwrap import dedent
from typing import List


def opening_statement_prompt(side: str, topic: str, briefing: List[str]) -> str:
    hints = "\n".join(f"- {item}" for item in briefing)
    base = f"""You are the {side} debater in a formal debate. The topic is: "{topic}".
Deliver a compelling opening statement that sets the tone for your side.
Stay under 500 words, keep a decisive tone, and end with a memorable slogan."""
    if briefing:
        base += "\nReference these pre-match notes:\n" + hints
    return dedent(base).strip()


def cross_question_prompt(
    side: str,
    topic: str,
    previous_questions: List[str],
    opponent_highlights: List[str],
) -> str:
    asked = "\n".join(f"- {item}" for item in previous_questions)
    highlights = "\n".join(f"- {item}" for item in opponent_highlights)
    prompt = f"""You represent the {side} side on the topic "{topic}".
Pose a single, sharp cross-examination question to expose weaknesses in the opponent's stance.
The question must be concise (max 60 words) and cannot contain multiple questions.
"""
    if previous_questions:
        prompt += "Questions already asked:\n" + asked + "\n"
    if opponent_highlights:
        prompt += "Opponent talking points worth pressing:\n" + highlights + "\n"
    prompt += "Return only the question."
    return dedent(prompt).strip()


def cross_answer_prompt(
    side: str,
    topic: str,
    question: str,
    prior_answers: List[str],
) -> str:
    prior = "\n".join(f"- {item}" for item in prior_answers)
    prompt = f"""You are the {side} debater. Topic: "{topic}".
Answer the opponent's question below clearly and briefly. Do not ask questions.
Question: "{question}"
"""
    if prior_answers:
        prompt += "Earlier answers you gave for cross-examination:\n" + prior + "\n"
    prompt += "Limit the answer to 120 words and keep a confident tone."
    return dedent(prompt).strip()


def free_debate_prompt(
    side: str,
    topic: str,
    last_opponent_point: str,
    round_number: int,
) -> str:
    prompt = f"""Free debate round {round_number} on "{topic}".
You speak for the {side} side. Respond directly to the opponent's latest point:
"{last_opponent_point}"
Deliver a tight rebuttal or advancement in fewer than 150 words, end with a forward-looking line."""
    return dedent(prompt).strip()


def closing_statement_prompt(side: str, topic: str, key_moments: List[str]) -> str:
    moments = "\n".join(f"- {item}" for item in key_moments)
    prompt = f"""Time for the closing statement for the {side} side on the motion "{topic}".
Summarize your strongest arguments, reclaim momentum, and finish with a decisive closer.
Stay below 400 words."""
    if key_moments:
        prompt += "\nMoments to incorporate or reinforce:\n" + moments
    return dedent(prompt).strip()


def judge_prompt(topic: str, transcript_summary: str, required_vote: str) -> str:
    prompt = f"""Debate motion: "{topic}".
You are reviewing the transcript highlights below to make a final judgment.
Summarise the decisive factors, apply the scoring criteria from your persona instructions,
and return a single JudgeOutput v1 JSON object.

Transcript highlights:
{transcript_summary}
"""
    return dedent(prompt).strip()
