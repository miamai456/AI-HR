import pandas as pd
import plotly.express as px
import streamlit as st

from app.api_client import ApiError, build_query, get_overview
from app.ui import SOURCE_COLORS, SOURCE_LABELS, configure_page, render_filters

configure_page("12 个月趋势")
st.title("12 个月推荐转化趋势")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    payload = get_overview(
        build_query(date_range, source, job_category, region, model_version, recruiter_team)
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()

trend = pd.DataFrame(payload["trend"])
if trend.empty:
    st.info("当前筛选范围没有可展示的数据。")
    st.stop()

trend["推荐来源"] = trend["source"].map(SOURCE_LABELS)
figure = px.line(
    trend,
    x="period",
    y="interview_rate",
    color="source",
    markers=True,
    color_discrete_map=SOURCE_COLORS,
    labels={
        "period": "月份",
        "interview_rate": "面试率",
        "source": "推荐来源",
    },
    hover_data={"recommended": ":,", "推荐来源": True, "source": False},
)
figure.update_yaxes(tickformat=".1%", rangemode="tozero")
figure.update_layout(legend_title_text="", hovermode="x unified", height=420)
st.plotly_chart(figure, width="stretch")
