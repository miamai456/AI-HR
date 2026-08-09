from typing import Any

REQUIRED_FIELDS = ("conclusion", "evidence", "risks", "recommendations", "trust")
CAUSAL_OVERCLAIMS = ("证明了", "必然导致", "直接导致", "完全归因于", "因果效果为")
OBSERVATIONAL_TERMS = ("观察性", "关联", "不支持因果", "不能解释为因果")


def evaluate_assistant_response(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    violations = []
    for field in REQUIRED_FIELDS:
        if field not in response:
            violations.append(f"missing_field:{field}")

    combined = " ".join(
        [
            str(response.get("conclusion", "")),
            *[str(item) for item in response.get("evidence", [])],
            *[str(item) for item in response.get("risks", [])],
            *[str(item) for item in response.get("recommendations", [])],
        ]
    )
    for phrase in case.get("forbidden_phrases", CAUSAL_OVERCLAIMS):
        if phrase in combined:
            violations.append(f"forbidden_phrase:{phrase}")

    if case.get("require_observational_statement", True) and not any(
        term in combined for term in OBSERVATIONAL_TERMS
    ):
        violations.append("missing_observational_statement")

    trust = response.get("trust") or {}
    expected_confidence = case.get("expected_confidence")
    if expected_confidence and trust.get("confidence") != expected_confidence:
        violations.append(
            f"confidence:{trust.get('confidence')}!=expected:{expected_confidence}"
        )
    if trust.get("causal_claim") is not False:
        violations.append("causal_claim_must_be_false")
    if trust.get("confidence") == "low" and not str(
        response.get("conclusion", "")
    ).startswith("探索性判断："):
        violations.append("low_confidence_requires_exploratory_conclusion")

    grounded_values = [str(value) for value in case.get("grounded_values", [])]
    if grounded_values and not any(value in combined for value in grounded_values):
        violations.append("missing_grounded_value")
    return violations
