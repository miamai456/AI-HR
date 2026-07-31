import os
from typing import Any

import requests

SYSTEM_PROMPT = """
你是 AIHR 项目的数据分析助手。你只能基于用户提供的 JSON 分析上下文回答。
回答必须面向招聘业务、数据分析师面试场景和初次接触看板的用户。

规则：
1. 区分事实、推断和建议。
2. 不得把观察性差异表述为因果效果。
3. 如果数据质量失败、模型漂移严重或样本不足，必须先说明结论限制。
4. 不编造上下文中不存在的指标、时间、岗位、团队或模型版本。
5. 回答要先给结论，再给证据，最后给下一步动作。
""".strip()


def assistant_configured() -> bool:
    return bool(
        os.getenv("AIHR_ASSISTANT_API_KEY")
        and os.getenv("AIHR_ASSISTANT_BASE_URL")
        and os.getenv("AIHR_ASSISTANT_MODEL")
    )


def assistant_config_summary() -> dict[str, str]:
    return {
        "provider": os.getenv("AIHR_ASSISTANT_PROVIDER", "openai-compatible"),
        "base_url": os.getenv("AIHR_ASSISTANT_BASE_URL", ""),
        "model": os.getenv("AIHR_ASSISTANT_MODEL", ""),
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
        "对面试官讲解时，先讲业务结论，再讲证据图表，最后讲限制和下一步动作。",
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


def call_llm(context: dict[str, Any], messages: list[dict[str, str]]) -> str:
    base_url = os.environ["AIHR_ASSISTANT_BASE_URL"].rstrip("/")
    api_key = os.environ["AIHR_ASSISTANT_API_KEY"]
    model = os.environ["AIHR_ASSISTANT_MODEL"]
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": f"当前分析上下文 JSON：{context}",
            },
            *messages,
        ],
    }
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def answer_question(context: dict[str, Any], messages: list[dict[str, str]]) -> str:
    latest_question = messages[-1]["content"] if messages else "请总结当前分析结论。"
    if not assistant_configured():
        return local_analysis(context, latest_question)
    try:
        return call_llm(context, messages)
    except requests.RequestException as exc:
        return (
            "大模型接口暂时不可用，已切换到本地规则分析。\n\n"
            f"接口错误：{exc}\n\n"
            f"{local_analysis(context, latest_question)}"
        )
