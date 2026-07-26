import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_funnel
from app.ui import SOURCE_COLORS, SOURCE_LABELS, configure_page, render_filters

configure_page("招聘漏斗")
st.title("招聘漏斗")
st.caption("同时比较 AI 与人工推荐在各阶段的数量损耗。")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    rows = get_funnel(
        build_query(date_range, source, job_category, region, model_version, recruiter_team)
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()

if not rows:
    st.info("当前筛选范围没有数据。")
    st.stop()

stages = ["recommended", "contacted", "replied", "interviewed", "offered", "hired"]
stage_labels = ["推荐", "联系", "回复", "面试", "Offer", "入职"]
fig = go.Figure()
for row in rows:
    fig.add_trace(
        go.Funnel(
            name=SOURCE_LABELS[row["source"]],
            y=stage_labels,
            x=[row[stage] for stage in stages],
            textinfo="value+percent initial",
            marker={"color": SOURCE_COLORS[row["source"]]},
        )
    )
fig.update_layout(margin=dict(l=0, r=0, t=20, b=0), legend_title_text="")
st.plotly_chart(fig, width="stretch")

table = pd.DataFrame(rows).rename(
    columns={
        "source": "推荐来源",
        "recommended": "推荐",
        "contacted": "联系",
        "replied": "回复",
        "interviewed": "面试",
        "offered": "Offer",
        "hired": "入职",
    }
)
table["推荐来源"] = table["推荐来源"].map(SOURCE_LABELS)
st.dataframe(table, width="stretch", hide_index=True)
