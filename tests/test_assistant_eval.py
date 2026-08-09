import json
from pathlib import Path

from aihr.evals.assistant_quality import evaluate_assistant_response


def test_eval_dataset_has_representative_cases() -> None:
    cases = json.loads(
        Path("tests/evals/assistant_cases.json").read_text(encoding="utf-8")
    )

    assert len(cases) >= 10
    assert {case["expected_confidence"] for case in cases} == {"low", "medium", "high"}


def test_eval_rejects_causal_and_unguarded_low_confidence_answer() -> None:
    violations = evaluate_assistant_response(
        {"expected_confidence": "low", "grounded_values": ["12"]},
        {
            "conclusion": "AI 必然导致转化提高",
            "evidence": ["样本量 12"],
            "risks": [],
            "recommendations": [],
            "trust": {"confidence": "low", "causal_claim": True},
        },
    )

    assert "forbidden_phrase:必然导致" in violations
    assert "causal_claim_must_be_false" in violations
    assert "low_confidence_requires_exploratory_conclusion" in violations


def test_eval_accepts_grounded_observational_answer() -> None:
    violations = evaluate_assistant_response(
        {"expected_confidence": "high", "grounded_values": ["120"]},
        {
            "conclusion": "120 条样本显示观察性关联。",
            "evidence": ["样本量 120"],
            "risks": ["不支持因果结论。"],
            "recommendations": ["继续监控。"],
            "trust": {"confidence": "high", "causal_claim": False},
        },
    )

    assert violations == []
