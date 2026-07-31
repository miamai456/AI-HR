from itertools import pairwise

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_funnel
from app.ui import (
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

STAGES = ["recommended", "contacted", "replied", "interviewed", "offered", "hired"]
STAGE_LABELS = {
    "recommended": "推荐",
    "contacted": "联系",
    "replied": "回复",
    "interviewed": "面试",
    "offered": "Offer",
    "hired": "入职",
}
STEP_LABELS = {
    "recommended_to_contacted": "推荐到联系",
    "contacted_to_replied": "联系到回复",
    "replied_to_interviewed": "回复到面试",
    "interviewed_to_offered": "面试到 Offer",
    "offered_to_hired": "Offer 到入职",
}


def step_rates(rows: list[dict]) -> pd.DataFrame:
    records = []
    for row in rows:
        for previous_stage, current_stage in pairwise(STAGES):
            previous_value = row[previous_stage]
            current_value = row[current_stage]
            rate = current_value / previous_value if previous_value else 0
            dropoff = 1 - rate if previous_value else 0
            step_key = f"{previous_stage}_to_{current_stage}"
            records.append(
                {
                    "source": row["source"],
                    "推荐来源": SOURCE_LABELS[row["source"]],
                    "环节": STEP_LABELS[step_key],
                    "阶段转化率": rate,
                    "阶段损耗率": dropoff,
                    "流入人数": previous_value,
                    "流出人数": current_value,
                }
            )
    return pd.DataFrame(records)


configure_page("招聘漏斗")
st.title("招聘漏斗")
st.caption("比较 AI 与人工推荐在各阶段的数量损耗，定位最值得优化的招聘环节。")

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

rates = step_rates(rows)
funnel_fig = go.Figure()
for row in rows:
    funnel_fig.add_trace(
        go.Funnel(
            name=SOURCE_LABELS[row["source"]],
            y=[STAGE_LABELS[stage] for stage in STAGES],
            x=[row[stage] for stage in STAGES],
            textinfo="value+percent initial",
            marker={"color": SOURCE_COLORS[row["source"]]},
        )
    )
funnel_fig.update_layout(margin=dict(l=0, r=0, t=20, b=0), legend_title_text="")
st.plotly_chart(funnel_fig, width="stretch")

insights = []
if not rates.empty:
    worst = rates.sort_values("阶段损耗率", ascending=False).iloc[0]
    insights.append(
        f"最大损耗发生在 {worst['推荐来源']} 的“{worst['环节']}”，"
        f"阶段损耗率为 {format_percent(worst['阶段损耗率'])}。"
    )
    pivot = rates.pivot_table(index="环节", columns="source", values="阶段转化率")
    if {"ai", "human"}.issubset(pivot.columns):
        pivot["ai_minus_human"] = pivot["ai"] - pivot["human"]
        best_ai_step = pivot.sort_values("ai_minus_human", ascending=False).iloc[0]
        insights.append(
            f"AI 相对人工优势最大的环节是“{best_ai_step.name}”，"
            f"差异为 {format_pp(best_ai_step['ai_minus_human'])}。"
        )
render_insight_box("漏斗分析结论", insights)

left, right = st.columns([1, 1])
with left:
    st.subheader("阶段转化率")
    conversion_fig = px.bar(
        rates,
        x="环节",
        y="阶段转化率",
        color="推荐来源",
        barmode="group",
        color_discrete_map={SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()},
        hover_data={"流入人数": ":,", "流出人数": ":,"},
    )
    conversion_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
    conversion_fig.update_layout(height=390, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(conversion_fig, width="stretch")

with right:
    st.subheader("阶段损耗率")
    dropoff_fig = px.bar(
        rates,
        x="环节",
        y="阶段损耗率",
        color="推荐来源",
        barmode="group",
        color_discrete_map={SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()},
        hover_data={"流入人数": ":,", "流出人数": ":,"},
    )
    dropoff_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
    dropoff_fig.update_layout(height=390, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(dropoff_fig, width="stretch")

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
render_table(table, width="stretch", hide_index=True)

render_ai_assistant(
    "funnel",
    "招聘漏斗",
    {
        "page": "招聘漏斗",
        "insights": insights,
        "data": {
            "funnel_rows": rows,
            "step_rates": rates.to_dict(orient="records"),
        },
    },
    [
        "这个漏斗最明显的损耗在哪里？",
        "AI 和人工推荐在哪个环节差距最大？",
        "如果我是面试官，这页应该怎么讲？",
    ],
)
