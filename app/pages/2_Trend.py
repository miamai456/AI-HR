import pandas as pd
import plotly.express as px
import streamlit as st

from app.api_client import ApiError, build_query, get_overview
from app.ui import SOURCE_COLORS, SOURCE_LABELS, configure_page, render_filters

configure_page("漏斗趋势")
st.title("招聘转化趋势")

date_range, source, job_category, region = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    payload = get_overview(build_query(date_range, source, job_category, region))
except ApiError as exc:
    st.error(str(exc))
    st.stop()

trend = pd.DataFrame(payload["trend"])
if trend.empty:
    st.info("当前筛选范围没有可展示的数据。")
    st.stop()

trend["推荐来源"] = trend["source"].map(SOURCE_LABELS)
trend["metric_date"] = pd.to_datetime(trend["metric_date"])
figure = px.line(
    trend,
    x="metric_date",
    y="interview_rate",
    color="source",
    color_discrete_map=SOURCE_COLORS,
    labels={
        "metric_date": "推荐日期",
        "interview_rate": "累计面试率",
        "source": "推荐来源",
    },
    hover_data={"recommended": ":,", "推荐来源": True, "source": False},
)
figure.update_yaxes(tickformat=".1%", rangemode="tozero")
figure.update_layout(legend_title_text="", hovermode="x unified", height=420)
st.plotly_chart(figure, width="stretch")
