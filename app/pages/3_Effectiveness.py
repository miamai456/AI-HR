import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_effectiveness
from app.ui import SOURCE_COLORS, configure_page, render_filters

configure_page("AI 推荐效果评估")
st.title("AI 推荐效果评估")
st.warning("当前为未调整的观察性差异，不能直接解释为 AI 推荐造成的因果效果。")

date_range, _, job_category, region = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    params = build_query(date_range, "全部", job_category, region)
    result = get_effectiveness(params)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

columns = st.columns(4)
columns[0].metric("AI 累计面试率", f"{result['ai_rate']:.2%}")
columns[1].metric("人工累计面试率", f"{result['human_rate']:.2%}")
columns[2].metric("原始差异", f"{result['difference'] * 100:+.2f} 个百分点")
columns[3].metric(
    "95% 置信区间",
    f"[{result['confidence_interval_low'] * 100:.2f}, "
    f"{result['confidence_interval_high'] * 100:.2f}]",
)

source_df = pd.DataFrame(
    {
        "来源": ["AI 推荐", "人工推荐"],
        "面试率": [result["ai_rate"], result["human_rate"]],
        "样本量": [result["ai_sample_size"], result["human_sample_size"]],
    }
)
figure = go.Figure(
    go.Bar(
        x=source_df["来源"],
        y=source_df["面试率"],
        marker_color=[SOURCE_COLORS["ai"], SOURCE_COLORS["human"]],
        customdata=source_df[["样本量"]],
        hovertemplate=("%{x}<br>累计面试率：%{y:.2%}<br>样本量：%{customdata[0]:,}<extra></extra>"),
    )
)
figure.update_yaxes(tickformat=".1%", rangemode="tozero")
figure.update_layout(showlegend=False, height=380)
st.plotly_chart(figure, width="stretch")

st.subheader("分析进度")
st.dataframe(
    pd.DataFrame(
        [
            {"分析层级": "原始转化率比较", "状态": "已完成", "输出": "比例差与 95% 置信区间"},
            {"分析层级": "样本平衡性", "状态": "待接入明细数据", "输出": "SMD 与共同支持区域"},
            {"分析层级": "调整后效果", "状态": "待接入明细数据", "输出": "倾向得分加权估计"},
        ]
    ),
    hide_index=True,
    width="stretch",
)
