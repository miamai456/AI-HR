import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_effectiveness
from app.ui import (
    SOURCE_COLORS,
    configure_page,
    format_percent,
    format_pp,
    render_ai_assistant,
    render_filters,
    render_insight_box,
    render_table,
)


def safe_percent(value: float | None) -> str:
    return "样本不足" if value is None else format_percent(value)


def safe_pp(value: float | None) -> str:
    return "样本不足" if value is None else format_pp(value)


configure_page("AI 推荐效果评估")
st.title("AI 推荐效果评估")
st.caption("用原始差异、倾向得分加权和协变量平衡诊断评估 AI 推荐与人工推荐的关联差异。")
st.warning("当前结果来自观察性数据和倾向得分调整，只能解释为关联分析，不得解释为因果效果。")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    params = build_query(date_range, source, job_category, region, model_version, recruiter_team)
    result = get_effectiveness(params)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

support = result["common_support"]
weights = result["extreme_weight_handling"]
adjusted_difference = result["adjusted_difference"]
support_retention = (
    support["retained_sample_size"] / support["original_sample_size"]
    if support["original_sample_size"]
    else 0
)

metric_columns = st.columns(5)
metric_columns[0].metric("AI 原始面试率", format_percent(result["ai_rate"]))
metric_columns[1].metric("人工原始面试率", format_percent(result["human_rate"]))
metric_columns[2].metric("原始差异", format_pp(result["difference"]))
metric_columns[3].metric("调整后差异", safe_pp(adjusted_difference))
metric_columns[4].metric("共同支持样本保留", format_percent(support_retention))

insights = [
    f"原始面试率差异为 {format_pp(result['difference'])}，"
    f"95% 置信区间为 [{format_pp(result['confidence_interval_low'])}, "
    f"{format_pp(result['confidence_interval_high'])}]。",
    f"倾向得分调整后差异为 {safe_pp(adjusted_difference)}，"
    f"共同支持保留 {support['retained_sample_size']:,} / "
    f"{support['original_sample_size']:,} 条样本。",
    f"权重使用 {result['weighting_method']}，极端权重截尾区间为 "
    f"[{weights['lower_clip']:.1f}, {weights['upper_clip']:.1f}]。",
]
render_insight_box("效果评估结论", insights)

source_df = pd.DataFrame(
    {
        "来源": ["AI 推荐", "人工推荐"],
        "原始面试率": [result["ai_rate"], result["human_rate"]],
        "调整后面试率": [result["adjusted_ai_rate"], result["adjusted_human_rate"]],
        "样本量": [result["ai_sample_size"], result["human_sample_size"]],
    }
)
figure = go.Figure()
figure.add_bar(
    name="原始",
    x=source_df["来源"],
    y=source_df["原始面试率"],
    marker_color=[SOURCE_COLORS["ai"], SOURCE_COLORS["human"]],
    customdata=source_df[["样本量"]],
    hovertemplate="%{x}<br>原始面试率: %{y:.2%}<br>样本量: %{customdata[0]:,}<extra></extra>",
)
figure.add_bar(
    name="倾向得分调整后",
    x=source_df["来源"],
    y=source_df["调整后面试率"],
    marker_color=["#60A5FA", "#F4A261"],
    customdata=source_df[["样本量"]],
    hovertemplate="%{x}<br>调整后面试率: %{y:.2%}<br>样本量: %{customdata[0]:,}<extra></extra>",
)
figure.update_yaxes(tickformat=".1%", rangemode="tozero")
figure.update_layout(barmode="group", legend_title_text="", height=390)
st.plotly_chart(figure, width="stretch")

tab_support, tab_balance, tab_method = st.tabs(["共同支持", "协变量平衡", "方法诊断"])

with tab_support:
    support_df = pd.DataFrame(
        [
            {"诊断项": "共同支持", "结果": "通过" if support["has_overlap"] else "未通过"},
            {"诊断项": "倾向得分方法", "结果": result["propensity_method"]},
            {"诊断项": "权重方法", "结果": result["weighting_method"]},
            {
                "诊断项": "共同支持区间",
                "结果": f"{support['lower_bound']:.2f} - {support['upper_bound']:.2f}",
            },
            {
                "诊断项": "保留样本",
                "结果": (
                    f"{support['retained_sample_size']:,} / "
                    f"{support['original_sample_size']:,}"
                ),
            },
            {"诊断项": "截尾前最大权重", "结果": f"{weights['max_weight_before']:.2f}"},
            {"诊断项": "截尾后最大权重", "结果": f"{weights['max_weight_after']:.2f}"},
        ]
    )
    render_table(support_df, hide_index=True, width="stretch")

with tab_balance:
    balance_df = pd.DataFrame(result["balance_diagnostics"])
    if balance_df.empty:
        st.info("当前范围没有协变量平衡诊断。")
    else:
        balance_long = balance_df.melt(
            id_vars="covariate",
            value_vars=["smd_before", "smd_after"],
            var_name="阶段",
            value_name="SMD",
        )
        balance_long["阶段"] = balance_long["阶段"].map(
            {"smd_before": "调整前", "smd_after": "调整后"}
        )
        smd_fig = px.bar(
            balance_long,
            x="SMD",
            y="covariate",
            color="阶段",
            barmode="group",
            orientation="h",
            labels={"covariate": "协变量"},
            color_discrete_map={"调整前": "#94A3B8", "调整后": "#2563EB"},
        )
        smd_fig.add_vline(x=0.1, line_dash="dash", line_color="#E76F51")
        smd_fig.add_vline(x=-0.1, line_dash="dash", line_color="#E76F51")
        smd_fig.update_layout(height=520, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(smd_fig, width="stretch")

        display_balance = balance_df.rename(
            columns={
                "covariate": "协变量",
                "smd_before": "调整前 SMD",
                "smd_after": "调整后 SMD",
            }
        )
        render_table(display_balance, hide_index=True, width="stretch")

with tab_method:
    st.markdown(
        f"""
        - 分析指标：`{result['metric']}`
        - 分析类型：`{result['analysis_type']}`
        - 是否做因果声明：`{result['causal_claim']}`
        - 限制说明：{result['limitation_note']}
        """
    )

render_ai_assistant(
    "effectiveness",
    "效果评估",
    {
        "page": "效果评估",
        "insights": insights,
        "metrics": {
            "ai_rate": result["ai_rate"],
            "human_rate": result["human_rate"],
            "raw_difference": result["difference"],
            "adjusted_difference": adjusted_difference,
            "support_retention": support_retention,
        },
        "data": {
            "effectiveness": result,
            "balance_diagnostics": result["balance_diagnostics"],
        },
        "warnings": ["这是观察性数据，只能解释为关联分析，不得直接解释为因果效果。"],
    },
    [
        "调整前后差异说明了什么？",
        "为什么这里不能直接说 AI 导致效果提升？",
        "SMD 和共同支持应该怎么向面试官解释？",
    ],
)
