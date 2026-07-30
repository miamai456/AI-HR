import pandas as pd
import plotly.express as px
import streamlit as st

from app.api_client import ApiError, build_query, get_overview
from app.ui import (
    SOURCE_COLORS,
    SOURCE_LABELS,
    configure_page,
    format_percent,
    render_filters,
    render_table,
)

configure_page("AIHR 总览")
st.title("AIHR 推荐效果总览")
st.caption("统一查看推荐量、AI 占比、联系率、面试、Offer、入职和监控告警。")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

query = build_query(date_range, source, job_category, region, model_version, recruiter_team)

try:
    result = get_overview(query)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

summary = result["summary"]
columns = st.columns(6)
columns[0].metric("推荐量", f"{summary['recommended']:,}")
columns[1].metric("AI 占比", format_percent(summary["ai_share"]))
columns[2].metric("联系率", format_percent(summary["contact_rate"]))
columns[3].metric("30 天合格面试率", format_percent(summary["qualified_interview_30d_rate"]))
columns[4].metric("Offer 率", format_percent(summary["offer_rate"]))
columns[5].metric("成熟队列入职率", format_percent(summary["mature_queue_hire_rate"]))

st.subheader("12 个月趋势")
trend = pd.DataFrame(result["trend"])
if trend.empty:
    st.info("当前筛选范围没有数据。")
else:
    trend["推荐来源"] = trend["source"].map(SOURCE_LABELS)
    figure = px.line(
        trend,
        x="period",
        y="interview_rate",
        color="推荐来源",
        markers=True,
        color_discrete_map={SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()},
        labels={"period": "月份", "interview_rate": "面试率", "推荐来源": "推荐来源"},
        hover_data={"recommended": ":,"},
    )
    figure.update_yaxes(tickformat=".1%", rangemode="tozero")
    figure.update_layout(
        legend_title_text="",
        hovermode="x unified",
        margin=dict(l=0, r=0, t=20, b=0),
    )
    st.plotly_chart(figure, width="stretch")

st.subheader("未解决告警")
alerts = pd.DataFrame(result["open_alerts"])
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

st.info("数据来源：synthetic_event_rollup。该版本用于验证指标、交互和系统架构，不代表真实企业招聘效果。")
