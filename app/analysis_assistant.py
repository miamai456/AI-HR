import os
from typing import Any

import streamlit as st

from aihr.services.assistant_trust import build_assistant_trust
from app.api_client import ApiError, analyze_assistant, get_assistant_status

SYSTEM_PROMPT = """
你是 AIHR 项目的数据分析助手。你只能基于用户提供的 JSON 分析上下文回答。
回答必须面向招聘业务、客户决策场景和初次接触看板的用户。

规则：
1. 区分事实、推断和建议。
2. 不得把观察性差异表述为因果效果。
3. 如果数据质量失败、模型漂移严重或样本不足，必须先说明结论限制。
4. 不编造上下文中不存在的指标、时间、岗位、团队或模型版本。
5. 回答要先给结论，再给证据，最后给下一步动作。
""".strip()

TRUST_BLOCK_START = "[[AIHR_TRUST_START]]"
TRUST_BLOCK_END = "[[AIHR_TRUST_END]]"
CONFIDENCE_LABELS = {"high": "高", "medium": "中", "low": "低"}
QUALITY_LABELS = {
    "pass": "可信",
    "warn": "需关注",
    "fail": "不可信",
    "unknown": "未知",
}
FILTER_LABELS = {
    "source": "推荐来源",
    "job_category": "岗位",
    "region": "地区",
    "model_version": "模型版本",
    "recruiter_team": "顾问团队",
}
FILTER_VALUE_LABELS = {"ai": "AI 推荐", "human": "人工推荐"}
ANALYSIS_TYPE_LABELS = {
    "observational_association": "观察性关联分析",
    "observational_adjusted_association": "调整后的观察性关联分析",
}
SOURCE_LABELS = {
    "DeepSeek": "DeepSeek",
    "Local rules": "本地规则",
    "Local rules fallback": "本地规则（DeepSeek 回退）",
}


def assistant_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        secret_value = st.secrets.get(name, default)
    except Exception:
        return default
    return str(secret_value) if secret_value else default


def assistant_configured() -> bool:
    try:
        return bool(get_assistant_status().get("configured"))
    except ApiError:
        return False


def assistant_config_summary() -> dict[str, str]:
    try:
        status = get_assistant_status()
        return {
            "provider": status.get("provider", "deepseek"),
            "base_url": "https://api.deepseek.com",
            "model": status.get("model", "deepseek-chat"),
        }
    except ApiError:
        pass
    return {
        "provider": assistant_setting("AIHR_ASSISTANT_PROVIDER", "deepseek"),
        "base_url": assistant_setting(
            "AIHR_ASSISTANT_BASE_URL", "https://api.deepseek.com"
        ),
        "model": assistant_setting("AIHR_ASSISTANT_MODEL", "deepseek-chat"),
    }


def percent(value: float | None) -> str:
    if value is None:
        return "样本不足"
    return f"{value:.1%}"


def pp(value: float | None) -> str:
    if value is None:
        return "样本不足"
    return f"{value * 100:+.1f} 个百分点"


def _overview_facts(context: dict[str, Any]) -> list[str]:
    overview = context.get("overview")
    if not overview:
        return []
    summary = overview["summary"]
    return [
        f"推荐量 {summary['recommended']:,}，AI 占比 {percent(summary['ai_share'])}，"
        f"整体面试率 {percent(summary['interview_rate'])}，"
        f"入职率 {percent(summary['hire_rate'])}。"
    ]


def _effectiveness_facts(context: dict[str, Any]) -> list[str]:
    effectiveness = context.get("effectiveness")
    if not effectiveness:
        return []
    adjusted_difference = effectiveness.get("adjusted_difference")
    difference = (
        adjusted_difference
        if adjusted_difference is not None
        else effectiveness.get("difference")
    )
    return [
        f"AI 原始面试率 {percent(effectiveness.get('ai_rate'))}，"
        f"人工原始面试率 {percent(effectiveness.get('human_rate'))}，"
        f"调整后差异 {pp(difference)}。",
        "该结果来自观察性数据，只能解释为关联分析，不能直接解释为因果效果。",
    ]


def _funnel_facts(context: dict[str, Any]) -> list[str]:
    rows = context.get("funnel_rows") or []
    facts = []
    for row in rows:
        source = "AI 推荐" if row["source"] == "ai" else "人工推荐"
        interview_rate = row["interviewed"] / row["recommended"] if row["recommended"] else 0
        hire_rate = row["hired"] / row["recommended"] if row["recommended"] else 0
        facts.append(
            f"{source} 推荐量 {row['recommended']:,}，面试率 {percent(interview_rate)}，"
            f"入职率 {percent(hire_rate)}。"
        )
    return facts


def _trend_facts(context: dict[str, Any]) -> list[str]:
    trend = context.get("trend") or []
    if not trend:
        return []
    latest_period = max(row["period"] for row in trend)
    latest_rows = [row for row in trend if row["period"] == latest_period]
    best = max(latest_rows, key=lambda row: row["interview_rate"])
    source = "AI 推荐" if best["source"] == "ai" else "人工推荐"
    return [
        f"最近一期 {latest_period} 面试率最高的是 {source}，"
        f"达到 {percent(best['interview_rate'])}。"
    ]


def _monitoring_facts(context: dict[str, Any]) -> list[str]:
    monitoring = context.get("monitoring")
    if not monitoring:
        return []
    drift = monitoring.get("drift_metrics", [])
    high_drift_count = sum(1 for row in drift if row.get("severity") == "high")
    medium_drift_count = sum(1 for row in drift if row.get("severity") == "medium")
    return [
        f"模型漂移诊断中，高风险 {high_drift_count} 项，中等风险 {medium_drift_count} 项。"
    ]


def _quality_facts(context: dict[str, Any]) -> list[str]:
    data_quality = context.get("data_quality")
    if not data_quality:
        return []
    summary = data_quality["summary"]
    return [
        f"数据质量检查 {summary['total_checks']} 项，失败 {summary['failed_checks']} 项，"
        f"预警 {summary['warning_checks']} 项。"
    ]


def _prediction_facts(context: dict[str, Any]) -> list[str]:
    prediction = context.get("prediction")
    if not prediction:
        return []
    summary = prediction["model_summary"]
    facts = [
        f"预测模型 AUC {summary['auc']:.3f}，Accuracy {percent(summary['accuracy'])}，"
        f"训练样本 {summary['sample_size']:,}。"
    ]
    segments = prediction.get("segment_performance", [])
    if segments:
        best = max(segments, key=lambda row: row["lift_vs_average"])
        facts.append(
            f"当前机会分群是 {best['segment_type']}={best['segment_value']}，"
            f"相对平均面试率提升 {pp(best['lift_vs_average'])}。"
        )
    anomalies = prediction.get("anomaly_findings", [])
    if anomalies:
        facts.append(f"异常检测发现 {len(anomalies)} 条需要复核的推荐样本。")
    return facts


def prepare_analysis_context(
    context: dict[str, Any],
    analysis_scope: dict[str, Any],
) -> dict[str, Any]:
    prepared = dict(context)
    prepared["analysis_scope"] = analysis_scope
    nested_data = prepared.get("data") or {}
    for name in ("effectiveness", "monitoring", "data_quality", "prediction"):
        if name not in prepared and name in nested_data:
            prepared[name] = nested_data[name]
    return prepared


def local_analysis(context: dict[str, Any], question: str) -> str:
    page_name = context.get("page_name", "当前页面")
    facts = [
        *_overview_facts(context),
        *_funnel_facts(context),
        *_trend_facts(context),
        *_effectiveness_facts(context),
        *_monitoring_facts(context),
        *_quality_facts(context),
        *_prediction_facts(context),
    ]
    if not facts:
        facts = ["当前上下文没有足够结构化数据，请先确认页面数据是否加载成功。"]

    recommendations = [
        "先判断数据是否可信，再解释效果差异。",
        "面向业务使用者解释时，先讲业务结论，再讲证据图表，最后讲限制和下一步动作。",
    ]
    if "异常" in question or "风险" in question:
        recommendations.append("优先排查数据质量失败项、高风险漂移和异常推荐样本。")
    if "怎么看" in question or "新手" in question or "初次" in question:
        recommendations.append("初次看板阅读顺序建议：首页、漏斗、趋势、效果评估、监控、机器学习洞察。")

    return "\n".join(
        [
            f"结论：这是对“{page_name}”的辅助解读。",
            "",
            "事实：",
            *[f"- {fact}" for fact in facts],
            "",
            "推断：",
            "- 当前看板可以用于说明 AI 推荐效果、业务瓶颈、模型稳定性或数据可信度。",
            "- 若样本不足、质量检查失败或漂移严重，相关结论需要降级为探索性判断。",
            "",
            "建议：",
            *[f"- {item}" for item in recommendations],
        ]
    )


def _format_structured_answer(
    data: dict[str, Any],
    *,
    source: str = "DeepSeek",
) -> str:
    trust = data.get("trust") or {}
    filters = ", ".join(
        f"{FILTER_LABELS.get(key, key)}={FILTER_VALUE_LABELS.get(value, value)}"
        for key, value in (trust.get("filters") or {}).items()
    ) or "全部"
    trust_lines = []
    if trust:
        period = (
            f"{trust.get('period_start') or 'unknown'} to "
            f"{trust.get('period_end') or 'unknown'}"
        )
        confidence = CONFIDENCE_LABELS.get(trust.get("confidence"), "未知")
        quality = QUALITY_LABELS.get(trust.get("data_quality_status"), "未知")
        analysis_type = ANALYSIS_TYPE_LABELS.get(
            trust.get("analysis_type"), trust.get("analysis_type", "未知")
        )
        trust_lines = [
            TRUST_BLOCK_START,
            (
                f"置信度：{confidence}｜样本量：{trust.get('sample_size', 0):,}｜"
                f"数据质量：{quality}"
            ),
            f"- 分析来源：{SOURCE_LABELS.get(source, source)}（{data.get('model', '已配置模型')}）",
            f"- 时间范围：{period.replace(' to ', ' 至 ')}",
            f"- 当前筛选：{filters}",
            f"- 数据更新时间：{trust.get('data_updated_at') or '未知'}",
            f"- 置信提示：{trust.get('confidence_note', '')}",
            f"- 分析类型：{analysis_type}",
            "- 因果声明：不支持因果结论，仅描述观察性关联。",
            TRUST_BLOCK_END,
            "",
        ]
    sections = [
        ("结论", data.get("conclusion", "")),
        ("证据", data.get("evidence", [])),
        ("风险", data.get("risks", [])),
        ("建议", data.get("recommendations", [])),
    ]
    output = trust_lines
    for title, value in sections:
        if isinstance(value, list):
            output.extend([f"**{title}**", *[f"- {item}" for item in value], ""])
        else:
            output.extend([f"**{title}**", str(value), ""])
    return "\n".join(output).strip()


def split_assistant_answer(content: str) -> tuple[str, str, str]:
    if TRUST_BLOCK_START not in content or TRUST_BLOCK_END not in content:
        return "", "", content
    trust_block, body = content.split(TRUST_BLOCK_END, 1)
    trust_block = trust_block.split(TRUST_BLOCK_START, 1)[1].strip()
    lines = trust_block.splitlines()
    summary = lines[0] if lines else ""
    details = "\n".join(lines[1:]).strip()
    return summary, details, body.strip()


def answer_question(
    context: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    force_refresh: bool = False,
) -> str:
    latest_question = messages[-1]["content"] if messages else "请总结当前分析结论。"
    if not assistant_configured():
        return _format_structured_answer(
            {
                "conclusion": local_analysis(context, latest_question),
                "evidence": [],
                "risks": ["外部模型不可用，当前回答由本地规则生成。"],
                "recommendations": [],
                "model": "local-rules",
                "trust": build_assistant_trust(context),
            },
            source="Local rules",
        )
    try:
        return _format_structured_answer(
            analyze_assistant(context, messages, force_refresh=force_refresh)
        )
    except ApiError as exc:
        return _format_structured_answer(
            {
                "conclusion": local_analysis(context, latest_question),
                "evidence": [],
                "risks": [f"DeepSeek 暂时不可用：{exc}"],
                "recommendations": [],
                "model": "local-rules-fallback",
                "trust": build_assistant_trust(context),
            },
            source="Local rules fallback",
        )
