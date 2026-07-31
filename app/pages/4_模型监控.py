import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_monitoring_with_filters
from app.ui import (
    SEVERITY_COLORS,
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

configure_page("模型监控")
st.title("模型监控")
st.caption("从效果变化、模型版本流量、漂移指标和告警结论判断推荐系统是否稳定。")

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

trend = pd.DataFrame(result["model_version_trends"])
drift = pd.DataFrame(result["drift_metrics"])
conclusions = pd.DataFrame(result["diagnostic_conclusions"])

high_count = int(drift["severity"].eq("high").sum()) if not drift.empty else 0
medium_count = int(drift["severity"].eq("medium").sum()) if not drift.empty else 0
worst_row = rows.reindex(rows["rate_change"].abs().sort_values(ascending=False).index).iloc[0]

metric_columns = st.columns(4)
metric_columns[0].metric("高风险漂移", f"{high_count:,}")
metric_columns[1].metric("中等漂移", f"{medium_count:,}")
metric_columns[2].metric(
    "最大面试率变化",
    format_pp(worst_row["rate_change"]),
    SOURCE_LABELS[worst_row["source"]],
)
metric_columns[3].metric("诊断结论", f"{len(conclusions):,}")

insights = [
    f"{SOURCE_LABELS[worst_row['source']]} 当前期面试率变化最大，"
    f"从 {format_percent(worst_row['baseline_interview_rate'])} 变为 "
    f"{format_percent(worst_row['current_interview_rate'])}，变化 "
    f"{format_pp(worst_row['rate_change'])}。",
    f"漂移诊断发现高风险 {high_count} 项、中等风险 {medium_count} 项；"
    "高风险漂移会降低分群结论和模型阈值建议的可信度。",
]
if not conclusions.empty:
    top_conclusion = conclusions.iloc[0]
    insights.append(f"首要诊断结论：{top_conclusion['message']}")
render_insight_box("监控分析结论", insights)

rows["source_label"] = rows["source"].map(SOURCE_LABELS)
overview_fig = go.Figure()
overview_fig.add_bar(
    name="基准期",
    x=rows["source_label"],
    y=rows["baseline_interview_rate"],
    marker_color="#64748B",
)
overview_fig.add_bar(
    name="当前期",
    x=rows["source_label"],
    y=rows["current_interview_rate"],
    marker_color=[SOURCE_COLORS[source_name] for source_name in rows["source"]],
)
overview_fig.update_layout(barmode="group", legend_title_text="", height=360)
overview_fig.update_yaxes(tickformat=".1%", title="面试率")
st.plotly_chart(overview_fig, width="stretch")

tab_version, tab_drift, tab_alert = st.tabs(["模型版本趋势", "漂移诊断", "告警结论"])

with tab_version:
    if trend.empty:
        st.info("当前筛选范围没有模型版本趋势数据。")
    else:
        left, right = st.columns([1, 1])
        with left:
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
            traffic_fig.update_layout(
                legend_title_text="",
                height=390,
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(traffic_fig, width="stretch")

        with right:
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
            effect_fig.update_layout(
                legend_title_text="",
                height=390,
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(effect_fig, width="stretch")

with tab_drift:
    if drift.empty:
        st.info("当前筛选范围没有可计算的漂移指标。")
    else:
        drift["严重度"] = drift["severity"].map(SEVERITY_LABELS)
        drift_fig = px.bar(
            drift.sort_values("drift_value"),
            x="drift_value",
            y="feature_name",
            color="severity",
            orientation="h",
            color_discrete_map=SEVERITY_COLORS,
            labels={"drift_value": "漂移值", "feature_name": "特征", "severity": "严重度"},
            hover_data=[
                "metric_type",
                "baseline_value",
                "current_value",
                "threshold_medium",
                "threshold_high",
            ],
        )
        drift_fig.update_layout(
            height=430,
            legend_title_text="",
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(drift_fig, width="stretch")

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

with tab_alert:
    if conclusions.empty:
        st.success("当前筛选范围没有诊断结论。")
    else:
        breakdown = pd.json_normalize(conclusions["breakdown"])
        conclusions = pd.concat([conclusions.drop(columns=["breakdown"]), breakdown], axis=1)
        conclusions["severity"] = conclusions["severity"].map(SEVERITY_LABELS)
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

st.subheader("推荐来源监控状态")
for row in result["rows"]:
    label = SOURCE_LABELS[row["source"]]
    message = f"{label}: 面试率变化 {format_pp(row['rate_change'])}"
    if row["severity"] == "high":
        st.error(message)
    elif row["severity"] == "medium":
        st.warning(message)
    else:
        st.success(message)

render_ai_assistant(
    "monitoring",
    "模型监控",
    {
        "page": "模型监控",
        "insights": insights,
        "metrics": {
            "high_drift_count": high_count,
            "medium_drift_count": medium_count,
            "largest_rate_change": worst_row["rate_change"],
        },
        "data": {
            "monitoring": result,
            "drift_metrics": result["drift_metrics"],
            "diagnostic_conclusions": result["diagnostic_conclusions"],
        },
    },
    [
        "当前模型监控是否稳定？",
        "哪些漂移或告警最需要优先处理？",
        "这些监控指标会怎样影响业务结论？",
    ],
)
