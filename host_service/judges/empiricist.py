from __future__ import annotations

from ..judge_common import PersonaConfig, build_judge_app

CONFIG = PersonaConfig(
    persona_id="empiricist",
    display_name="数据实证派评委",
    introduction=(
        "你是一位数据实证派评委。你优先看重数据与研究支持，区分相关与因果；"
        "奖励可检验的操作性主张；对模糊、不可验证的论断扣分。你可以在内部推理，"
        "但输出不得泄露思维链；仅输出 JudgeOutput v1 JSON。"
    ),
    weights=[
        ("evidence", 0.40),
        ("logic", 0.25),
        ("responsiveness", 0.15),
        ("clarity", 0.10),
        ("rule_adherence", 0.05),
        ("style", 0.05),
        ("strategy", 0.00),
    ],
)

app = build_judge_app(CONFIG)

