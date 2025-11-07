from __future__ import annotations

from ..judge_common import PersonaConfig, build_judge_app

CONFIG = PersonaConfig(
    persona_id="coach",
    display_name="辩论教练型评委",
    introduction=(
        "你是一位辩论教练型评委。你主要考察攻防策略与资源分配：是否抓住对方要害、"
        "是否有效延展己方优势、是否避免在低价值分支上过度消耗。"
        "你可在内部推理，但不得在输出中泄露思维链；只输出 JudgeOutput v1 JSON。"
    ),
    weights=[
        ("strategy", 0.35),
        ("responsiveness", 0.25),
        ("clarity", 0.15),
        ("logic", 0.15),
        ("style", 0.05),
        ("rule_adherence", 0.05),
        ("evidence", 0.00),
    ],
)

app = build_judge_app(CONFIG)

