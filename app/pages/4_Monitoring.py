import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_monitoring_with_filters
from app.ui import SOURCE_COLORS, SOURCE_LABELS, configure_page, format_percent, render_filters

configure_page("效果监控")
st.title("效果监控")

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
    f"基准期：{result['baseline_start']} 至 {result['baseline_end']} · "
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
figure.update_layout(barmode="group", legend_title_text="", height=380)
figure.update_yaxes(tickformat=".1%", title="面试率")
st.plotly_chart(figure, width="stretch")

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
