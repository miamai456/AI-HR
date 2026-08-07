from datetime import datetime
from typing import Any

from aihr.services.assistant import AssistantAnswer

MIN_STABLE_SAMPLE_SIZE = 30
MIN_HIGH_CONFIDENCE_SAMPLE_SIZE = 100


def _latest_data_update(context: dict[str, Any]) -> str | None:
    layers = (context.get("data_quality") or {}).get("layers", [])
    timestamps = [layer.get("last_updated_at") for layer in layers if layer.get("last_updated_at")]
    if not timestamps:
        return None
    parsed = []
    for value in timestamps:
        try:
            parsed.append(datetime.fromisoformat(value))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return None
    return max(parsed).isoformat()


def build_assistant_trust(context: dict[str, Any]) -> dict[str, Any]:
    overview = context.get("overview") or {}
    prediction = context.get("prediction") or {}
    effectiveness = context.get("effectiveness") or {}
    quality = context.get("data_quality") or {}
    quality_summary = quality.get("summary") or {}
    scope = context.get("analysis_scope") or {}
    quality_checks = quality.get("checks") or []
    fallback_period = quality_checks[0] if quality_checks else {}

    sample_size = int(
        (overview.get("summary") or {}).get("recommended")
        or (prediction.get("model_summary") or {}).get("sample_size")
        or (
            int(effectiveness.get("ai_sample_size") or 0)
            + int(effectiveness.get("human_sample_size") or 0)
        )
    )
    failed_checks = int(quality_summary.get("failed_checks") or 0)
    warning_checks = int(quality_summary.get("warning_checks") or 0)
    if not quality:
        quality_status = "unknown"
    else:
        quality_status = "fail" if failed_checks else "warn" if warning_checks else "pass"

    if sample_size < MIN_STABLE_SAMPLE_SIZE or quality_status in {"fail", "unknown"}:
        confidence = "low"
        confidence_note = (
            "样本量不足、数据质量检查失败或质量信息缺失，仅允许探索性判断。"
        )
    elif sample_size < MIN_HIGH_CONFIDENCE_SAMPLE_SIZE or quality_status == "warn":
        confidence = "medium"
        confidence_note = "样本量或数据质量存在限制，结论需要谨慎使用。"
    else:
        confidence = "high"
        confidence_note = "样本量和数据质量支持较稳定的观察性结论。"

    return {
        "sample_size": sample_size,
        "period_start": scope.get("start_date") or fallback_period.get("period_start"),
        "period_end": scope.get("end_date") or fallback_period.get("period_end"),
        "data_updated_at": _latest_data_update(context),
        "data_quality_status": quality_status,
        "confidence": confidence,
        "confidence_note": confidence_note,
        "analysis_type": effectiveness.get(
            "analysis_type", "observational_association"
        ),
        "causal_claim": False,
        "filters": scope.get("filters") or {},
    }


def apply_trust_guard(answer: AssistantAnswer, trust: dict[str, Any]) -> AssistantAnswer:
    if trust["confidence"] != "low":
        return answer
    risk = "样本量或数据质量不足，不能生成强结论。"
    return AssistantAnswer(
        conclusion=f"探索性判断：{answer.conclusion}",
        evidence=answer.evidence,
        risks=[risk, *[item for item in answer.risks if item != risk]],
        recommendations=answer.recommendations,
        total_tokens=answer.total_tokens,
    )
