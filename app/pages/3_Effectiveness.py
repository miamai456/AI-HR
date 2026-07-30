import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_effectiveness
from app.ui import SOURCE_COLORS, configure_page, render_filters, render_table

configure_page("AI 推荐效果评估")
st.title("AI 推荐效果评估")
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

raw_columns = st.columns(5)
raw_columns[0].metric("AI 原始面试率", f"{result['ai_rate']:.2%}")
raw_columns[1].metric("人工原始面试率", f"{result['human_rate']:.2%}")
raw_columns[2].metric("原始差异", f"{result['difference'] * 100:+.2f} 个百分点")
raw_columns[3].metric("比例差", f"{result['proportion_difference'] * 100:+.2f} 个百分点")
raw_columns[4].metric(
    "95% 置信区间",
    f"[{result['confidence_interval_low'] * 100:.2f}, "
    f"{result['confidence_interval_high'] * 100:.2f}]",
)

sample_columns = st.columns(4)
sample_columns[0].metric("AI 样本量", f"{result['ai_sample_size']:,}")
sample_columns[1].metric("人工样本量", f"{result['human_sample_size']:,}")
sample_columns[2].metric("共同支持样本量", f"{result['common_support']['retained_sample_size']:,}")
sample_columns[3].metric(
    "共同支持区间",
    f"{result['common_support']['lower_bound']:.2f} - "
    f"{result['common_support']['upper_bound']:.2f}",
)

adjusted_columns = st.columns(3)
adjusted_columns[0].metric("AI 调整后面试率", f"{result['adjusted_ai_rate']:.2%}")
adjusted_columns[1].metric("人工调整后面试率", f"{result['adjusted_human_rate']:.2%}")
adjusted_columns[2].metric("调整后差异", f"{result['adjusted_difference'] * 100:+.2f} 个百分点")

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
    hovertemplate="%{x}<br>原始面试率：%{y:.2%}<br>样本量：%{customdata[0]:,}<extra></extra>",
)
figure.add_bar(
    name="倾向得分调整后",
    x=source_df["来源"],
    y=source_df["调整后面试率"],
    marker_color=["#60A5FA", "#F4A261"],
    customdata=source_df[["样本量"]],
    hovertemplate="%{x}<br>调整后面试率：%{y:.2%}<br>样本量：%{customdata[0]:,}<extra></extra>",
)
figure.update_yaxes(tickformat=".1%", rangemode="tozero")
figure.update_layout(barmode="group", legend_title_text="", height=380)
st.plotly_chart(figure, width="stretch")

st.subheader("共同支持与极端权重")
support = result["common_support"]
weights = result["extreme_weight_handling"]
diagnostic_df = pd.DataFrame(
    [
        {"诊断项": "共同支持", "结果": "通过" if support["has_overlap"] else "未通过"},
        {"诊断项": "倾向得分方法", "结果": result["propensity_method"]},
        {"诊断项": "权重方法", "结果": result["weighting_method"]},
        {
            "诊断项": "极端权重处理",
            "结果": (
                f"{weights['method']} "
                f"[{weights['lower_clip']:.1f}, {weights['upper_clip']:.1f}]"
            ),
        },
        {"诊断项": "截尾前最大权重", "结果": f"{weights['max_weight_before']:.2f}"},
        {"诊断项": "截尾后最大权重", "结果": f"{weights['max_weight_after']:.2f}"},
    ]
)
render_table(diagnostic_df, hide_index=True, width="stretch")

st.subheader("调整前后 SMD")
balance_df = pd.DataFrame(result["balance_diagnostics"]).rename(
    columns={
        "covariate": "协变量",
        "smd_before": "调整前 SMD",
        "smd_after": "调整后 SMD",
    }
)
render_table(balance_df, hide_index=True, width="stretch")
