import pandas as pd
import plotly.express as px
import streamlit as st

from app.api_client import ApiError, build_query, get_overview
from app.ui import SOURCE_COLORS, SOURCE_LABELS, configure_page, format_percent, render_filters

configure_page("招聘推荐效果总览")
st.title("AI 招聘推荐效果总览")
st.caption("从推荐曝光到入职的核心表现，支持按业务维度筛选。")

date_range, source, job_category, region = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    result = get_overview(build_query(date_range, source, job_category, region))
except ApiError as exc:
    st.error(str(exc))
    st.stop()

summary = result["summary"]
columns = st.columns(5)
columns[0].metric("推荐量", f"{summary['recommended']:,}")
columns[1].metric("联系率", format_percent(summary["contact_rate"]))
columns[2].metric("累计面试率", format_percent(summary["interview_rate"]))
columns[3].metric("累计 Offer 率", format_percent(summary["offer_rate"]))
columns[4].metric("累计入职率", format_percent(summary["hire_rate"]))

st.subheader("推荐效果趋势")
trend = pd.DataFrame(result["trend"])
if trend.empty:
    st.info("当前筛选范围没有数据。")
else:
    trend["source_label"] = trend["source"].map(SOURCE_LABELS)
    trend["metric_date"] = pd.to_datetime(trend["metric_date"])
    fig = px.line(
        trend,
        x="metric_date",
        y="interview_rate",
        color="source_label",
        color_discrete_map={SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()},
        labels={"metric_date": "推荐日期", "interview_rate": "累计面试率", "source_label": "来源"},
    )
    fig.update_yaxes(tickformat=".1%")
    fig.update_layout(legend_title_text="", hovermode="x unified", margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig, width="stretch")

st.info("数据来源：synthetic。该版本用于验证指标、交互和系统架构，不代表真实企业招聘效果。")
