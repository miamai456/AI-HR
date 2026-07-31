import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_overview
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

configure_page("12 个月趋势")
st.title("12 个月推荐转化趋势")
st.caption("观察推荐量、面试率和入职率的时间变化，判断效果改善是否稳定。")

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
trend = trend.sort_values(["source", "period"]).copy()
trend["面试率环比"] = trend.groupby("source")["interview_rate"].diff()
trend["入职率环比"] = trend.groupby("source")["hire_rate"].diff()
trend["3期滚动面试率"] = trend.groupby("source")["interview_rate"].transform(
    lambda values: values.rolling(3, min_periods=1).mean()
)

latest_period = trend["period"].max()
latest = trend[trend["period"].eq(latest_period)]
insights = []
if not latest.empty:
    best = latest.sort_values("interview_rate", ascending=False).iloc[0]
    insights.append(
        f"最近一期 {latest_period} 面试率最高的是 {best['推荐来源']}，"
        f"为 {format_percent(best['interview_rate'])}。"
    )
    if latest["source"].nunique() == 2:
        pivot = latest.set_index("source")
        diff = pivot.loc["ai", "interview_rate"] - pivot.loc["human", "interview_rate"]
        insights.append(f"最近一期 AI 与人工面试率差异为 {format_pp(diff)}。")

largest_change = trend.dropna(subset=["面试率环比"])
if not largest_change.empty:
    largest_change_index = largest_change["面试率环比"].abs().sort_values(ascending=False).index
    row = largest_change.reindex(largest_change_index).iloc[0]
    insights.append(
        f"波动最大的月份是 {row['period']} 的 {row['推荐来源']}，"
        f"面试率环比变化 {format_pp(row['面试率环比'])}。"
    )
render_insight_box("趋势分析结论", insights)

tab_rate, tab_volume, tab_table = st.tabs(["转化趋势", "推荐量与成熟度", "趋势明细"])

with tab_rate:
    rate_fig = px.line(
        trend,
        x="period",
        y="interview_rate",
        color="推荐来源",
        markers=True,
        color_discrete_map={SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()},
        labels={"period": "月份", "interview_rate": "面试率", "推荐来源": "推荐来源"},
        hover_data={"recommended": ":,", "hire_rate": ":.2%"},
    )
    for source_key, source_label in SOURCE_LABELS.items():
        source_trend = trend[trend["source"].eq(source_key)]
        rate_fig.add_trace(
            go.Scatter(
                x=source_trend["period"],
                y=source_trend["3期滚动面试率"],
                mode="lines",
                name=f"{source_label} 3期滚动",
                line={"dash": "dash", "color": SOURCE_COLORS[source_key]},
                hovertemplate="%{x}<br>3期滚动面试率: %{y:.2%}<extra></extra>",
            )
        )
    rate_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
    rate_fig.update_layout(legend_title_text="", hovermode="x unified", height=460)
    st.plotly_chart(rate_fig, width="stretch")

with tab_volume:
    left, right = st.columns([1, 1])
    with left:
        volume_fig = px.bar(
            trend,
            x="period",
            y="recommended",
            color="推荐来源",
            color_discrete_map={
                SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()
            },
            labels={"period": "月份", "recommended": "推荐量", "推荐来源": "推荐来源"},
        )
        volume_fig.update_layout(height=390, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(volume_fig, width="stretch")
    with right:
        hire_fig = px.line(
            trend,
            x="period",
            y="hire_rate",
            color="推荐来源",
            markers=True,
            color_discrete_map={
                SOURCE_LABELS[key]: value for key, value in SOURCE_COLORS.items()
            },
            labels={"period": "月份", "hire_rate": "入职率", "推荐来源": "推荐来源"},
            hover_data={"recommended": ":,"},
        )
        hire_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
        hire_fig.update_layout(height=390, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(hire_fig, width="stretch")

with tab_table:
    trend_display = trend[
        ["period", "推荐来源", "recommended", "interview_rate", "hire_rate", "面试率环比"]
    ].rename(
        columns={
            "period": "月份",
            "recommended": "推荐量",
            "interview_rate": "面试率",
            "hire_rate": "入职率",
        }
    )
    trend_display["面试率"] = trend_display["面试率"].map(format_percent)
    trend_display["入职率"] = trend_display["入职率"].map(format_percent)
    trend_display["面试率环比"] = trend_display["面试率环比"].map(
        lambda value: "" if pd.isna(value) else format_pp(value)
    )
    render_table(trend_display, hide_index=True, width="stretch")

render_ai_assistant(
    "trend",
    "趋势分析",
    {
        "page": "趋势分析",
        "insights": insights,
        "data": {
            "latest_period": latest_period,
            "trend": trend.to_dict(orient="records"),
        },
    },
    [
        "当前趋势是否稳定？",
        "最近一期 AI 和人工有什么差异？",
        "这页适合怎么向面试官解释？",
    ],
)
