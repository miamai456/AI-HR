import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import (
    ApiError,
    build_query,
    get_data_quality,
    get_effectiveness,
    get_monitoring_with_filters,
    get_overview,
    get_prediction_insights,
)
from app.ui import (
    SEVERITY_LABELS,
    SOURCE_COLORS,
    SOURCE_LABELS,
    configure_page,
    format_percent,
    format_pp,
    render_ai_assistant,
    render_filters,
    render_insight_box,
    render_table,
)


def decision_label(value: float) -> str:
    if value >= 0.02:
        return "AI 推荐表现更优"
    if value <= -0.02:
        return "人工推荐表现更优"
    return "两类推荐表现接近"


def best_trend_segment(trend: pd.DataFrame) -> str:
    if trend.empty:
        return "当前范围没有趋势数据，无法判断最佳来源。"
    latest_period = trend["period"].max()
    latest = trend[trend["period"].eq(latest_period)].copy()
    latest["source_label"] = latest["source"].map(SOURCE_LABELS)
    row = latest.sort_values("interview_rate", ascending=False).iloc[0]
    return (
        f"{latest_period} 面试率最高的是 {row['source_label']}，"
        f"达到 {format_percent(row['interview_rate'])}。"
    )


def data_trust_label(failed_checks: int, warning_checks: int, high_drift_count: int) -> str:
    if failed_checks or high_drift_count:
        return "结论需谨慎"
    if warning_checks:
        return "基本可信，需关注预警"
    return "数据基础稳定"


configure_page("Executive Dashboard")
st.title("AIHR 招聘推荐分析驾驶舱")
st.caption(
    "面向面试官的 30 秒总览：先给结论，再展示证据，最后指出下一步业务动作。"
)

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

query = build_query(date_range, source, job_category, region, model_version, recruiter_team)

try:
    overview = get_overview(query)
    effectiveness = get_effectiveness(query)
    monitoring = get_monitoring_with_filters(query)
    quality = get_data_quality(query)
    prediction = get_prediction_insights(query)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

summary = overview["summary"]
trend = pd.DataFrame(overview["trend"])
alerts = pd.DataFrame(overview["open_alerts"])
monitoring_rows = pd.DataFrame(monitoring["rows"])
drift = pd.DataFrame(monitoring["drift_metrics"])
segments = pd.DataFrame(prediction["segment_performance"])
quality_summary = quality["summary"]

adjusted_difference = effectiveness["adjusted_difference"]
raw_difference = effectiveness["difference"]
decision_difference = adjusted_difference if adjusted_difference is not None else raw_difference
high_drift_count = int(drift["severity"].eq("high").sum()) if not drift.empty else 0
medium_drift_count = int(drift["severity"].eq("medium").sum()) if not drift.empty else 0

st.subheader("核心结论")
metric_columns = st.columns(5)
metric_columns[0].metric("推荐量", f"{summary['recommended']:,}")
metric_columns[1].metric("AI 占比", format_percent(summary["ai_share"]))
metric_columns[2].metric("面试率", format_percent(summary["interview_rate"]))
metric_columns[3].metric(
    "调整后 AI 差异",
    format_pp(decision_difference),
    decision_label(decision_difference),
)
metric_columns[4].metric(
    "结论可信度",
    data_trust_label(
        quality_summary["failed_checks"],
        quality_summary["warning_checks"],
        high_drift_count,
    ),
)

executive_insights = [
    f"{decision_label(decision_difference)}：调整后差异为 {format_pp(decision_difference)}，"
    "该结果用于关联分析，不直接宣称因果。",
    best_trend_segment(trend),
    (
        f"数据质量检查失败 {quality_summary['failed_checks']} 项、预警 "
        f"{quality_summary['warning_checks']} 项；模型高风险漂移 {high_drift_count} 项、"
        f"中等漂移 {medium_drift_count} 项。"
    ),
]
if not segments.empty:
    best_segment = segments.sort_values("lift_vs_average", ascending=False).iloc[0]
    executive_insights.append(
        f"当前最值得放大的分群是 {best_segment['segment_type']}={best_segment['segment_value']}，"
        f"相对平均面试率提升 {format_pp(best_segment['lift_vs_average'])}。"
    )
render_insight_box("自动分析结论", executive_insights)

left, right = st.columns([1.15, 1])
with left:
    st.subheader("12 个月面试率趋势")
    if trend.empty:
        st.info("当前筛选范围没有趋势数据。")
    else:
        trend["推荐来源"] = trend["source"].map(SOURCE_LABELS)
        trend_fig = px.line(
            trend,
            x="period",
            y="interview_rate",
            color="推荐来源",
            markers=True,
            color_discrete_map={
                SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()
            },
            labels={"period": "月份", "interview_rate": "面试率", "推荐来源": "推荐来源"},
            hover_data={"recommended": ":,"},
        )
        trend_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
        trend_fig.update_layout(
            legend_title_text="",
            hovermode="x unified",
            height=380,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(trend_fig, width="stretch")

with right:
    st.subheader("业务漏斗速览")
    funnel_values = [
        summary["recommended"],
        summary["contacted"],
        summary["replied"],
        summary["interviewed"],
        summary["offered"],
        summary["hired"],
    ]
    funnel_fig = go.Figure(
        go.Funnel(
            y=["推荐", "联系", "回复", "面试", "Offer", "入职"],
            x=funnel_values,
            textinfo="value+percent initial",
            marker={"color": "#2563EB"},
        )
    )
    funnel_fig.update_layout(height=380, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(funnel_fig, width="stretch")

st.subheader("机会与风险")
opportunity_left, risk_right = st.columns([1, 1])
with opportunity_left:
    if segments.empty:
        st.info("当前范围没有足够样本生成分群机会。")
    else:
        segment_display = segments.sort_values("lift_vs_average", ascending=False).head(6)
        segment_display = segment_display.rename(
            columns={
                "segment_type": "分群类型",
                "segment_value": "分群取值",
                "recommendations": "推荐数",
                "actual_conversion_rate": "实际面试率",
                "lift_vs_average": "相对平均提升",
            }
        )[["分群类型", "分群取值", "推荐数", "实际面试率", "相对平均提升"]]
        segment_display["实际面试率"] = segment_display["实际面试率"].map(format_percent)
        segment_display["相对平均提升"] = segment_display["相对平均提升"].map(format_pp)
        render_table(segment_display, hide_index=True, width="stretch")

with risk_right:
    if monitoring_rows.empty:
        st.info("当前范围没有监控状态。")
    else:
        status_display = monitoring_rows.copy()
        status_display["source"] = status_display["source"].map(SOURCE_LABELS)
        status_display["severity"] = status_display["severity"].map(SEVERITY_LABELS)
        status_display["baseline_interview_rate"] = status_display[
            "baseline_interview_rate"
        ].map(format_percent)
        status_display["current_interview_rate"] = status_display[
            "current_interview_rate"
        ].map(format_percent)
        status_display["rate_change"] = status_display["rate_change"].map(format_pp)
        render_table(
            status_display.rename(
                columns={
                    "source": "推荐来源",
                    "baseline_interview_rate": "基准期面试率",
                    "current_interview_rate": "当前期面试率",
                    "rate_change": "变化",
                    "severity": "风险等级",
                }
            ),
            hide_index=True,
            width="stretch",
        )

st.subheader("未解决告警")
if alerts.empty:
    st.success("当前筛选范围没有未解决告警。")
else:
    render_table(
        alerts.rename(
            columns={
                "alert_key": "告警键",
                "severity": "严重度",
                "metric_name": "指标",
                "evidence": "证据",
                "period_start": "开始日期",
                "period_end": "结束日期",
            }
        ),
        hide_index=True,
        width="stretch",
    )

st.info(
    "数据来源为合成招聘事件，用于展示分析框架、指标口径、建模解释和监控能力，"
    "不代表真实企业招聘效果。"
)

render_ai_assistant(
    "overview",
    "首页驾驶舱",
    {
        "overview": overview,
        "effectiveness": effectiveness,
        "monitoring": monitoring,
        "data_quality": quality,
        "prediction": prediction,
    },
    [
        "请总结首页最重要的业务结论。",
        "哪些风险会影响当前结论可信度？",
        "面试官第一次看这个项目时我该怎么讲？",
    ],
)
