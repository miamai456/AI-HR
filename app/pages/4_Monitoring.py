import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_monitoring_with_filters
from app.ui import (
    SOURCE_COLORS,
    SOURCE_LABELS,
    configure_page,
    format_percent,
    render_filters,
    render_table,
)

configure_page("模型监控")
st.title("模型监控")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    result = get_monitoring_with_filters(
        build_query(date_range, source, job_category, region, model_version, recruiter_team)
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()

st.caption(
    f"基准期：{result['baseline_start']} 至 {result['baseline_end']} | "
    f"当前期：{result['current_start']} 至 {result['current_end']}"
)

rows = pd.DataFrame(result["rows"])
if rows.empty:
    st.info("当前筛选范围没有可监控的数据。")
    st.stop()

rows["source_label"] = rows["source"].map(SOURCE_LABELS)
figure = go.Figure()
figure.add_bar(
    name="基准期",
    x=rows["source_label"],
    y=rows["baseline_interview_rate"],
    marker_color="#64748B",
)
figure.add_bar(
    name="当前期",
    x=rows["source_label"],
    y=rows["current_interview_rate"],
    marker_color=[SOURCE_COLORS[source] for source in rows["source"]],
)
figure.update_layout(barmode="group", legend_title_text="", height=360)
figure.update_yaxes(tickformat=".1%", title="面试率")
st.plotly_chart(figure, width="stretch")

st.subheader("模型版本流量与效果趋势")
trend = pd.DataFrame(result["model_version_trends"])
if trend.empty:
    st.info("当前筛选范围没有模型版本趋势数据。")
else:
    traffic_fig = px.bar(
        trend,
        x="period",
        y="recommendations",
        color="model_version",
        labels={
            "period": "月份",
            "recommendations": "推荐量",
            "model_version": "模型版本",
        },
        hover_data=["job_category", "region", "traffic_share", "interview_rate"],
    )
    traffic_fig.update_layout(legend_title_text="", height=360)
    st.plotly_chart(traffic_fig, width="stretch")

    effect_fig = px.line(
        trend,
        x="period",
        y="interview_rate",
        color="model_version",
        markers=True,
        labels={
            "period": "月份",
            "interview_rate": "面试率",
            "model_version": "模型版本",
        },
        hover_data=["job_category", "region", "recommendations", "traffic_share"],
    )
    effect_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
    effect_fig.update_layout(legend_title_text="", height=360)
    st.plotly_chart(effect_fig, width="stretch")

st.subheader("漂移诊断")
drift = pd.DataFrame(result["drift_metrics"])
if drift.empty:
    st.info("当前筛选范围没有可计算的漂移指标。")
else:
    display_drift = drift.rename(
        columns={
            "metric_type": "指标类型",
            "feature_name": "特征",
            "baseline_value": "基准值",
            "current_value": "当前值",
            "drift_value": "漂移值",
            "threshold_medium": "中等阈值",
            "threshold_high": "高阈值",
            "severity": "严重程度",
            "baseline_sample_size": "基准样本量",
            "current_sample_size": "当前样本量",
        }
    )
    render_table(display_drift, hide_index=True, width="stretch")

st.subheader("告警与异常诊断")
conclusions = pd.DataFrame(result["diagnostic_conclusions"])
if conclusions.empty:
    st.info("当前筛选范围没有诊断结论。")
else:
    breakdown = pd.json_normalize(conclusions["breakdown"])
    conclusions = pd.concat([conclusions.drop(columns=["breakdown"]), breakdown], axis=1)
    display_conclusions = conclusions.rename(
        columns={
            "conclusion_type": "结论类型",
            "category": "问题分类",
            "severity": "严重程度",
            "message": "结论",
            "evidence_metric": "证据指标",
            "baseline_value": "基准值",
            "current_value": "当前值",
            "change_value": "变化值",
            "period_start": "开始日期",
            "period_end": "结束日期",
            "baseline_sample_size": "基准样本量",
            "current_sample_size": "当前样本量",
            "sample_size": "样本量",
            "job_category": "岗位",
            "region": "地区",
            "recruiter_team": "顾问团队",
            "model_version": "模型版本",
        }
    )
    render_table(display_conclusions, hide_index=True, width="stretch")

st.subheader("监控状态")
for row in result["rows"]:
    label = SOURCE_LABELS[row["source"]]
    change = format_percent(row["rate_change"])
    message = f"{label}：面试率变化 {change}"
    if row["severity"] == "high":
        st.error(message)
    elif row["severity"] == "medium":
        st.warning(message)
    else:
        st.success(message)
