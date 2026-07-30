import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_prediction_insights
from app.ui import configure_page, format_percent, render_filters, render_table

MODEL_LABELS = {
    "logistic_regression_conversion": "逻辑回归转化预测",
    "isolation_forest": "孤立森林",
}
TARGET_LABELS = {"interviewed": "是否进入面试"}
DIRECTION_LABELS = {"positive": "正向影响", "negative": "负向影响"}
SEGMENT_TYPE_LABELS = {
    "source": "推荐来源",
    "job_category": "岗位",
    "region": "地区",
    "model_version": "模型版本",
    "recruiter_team": "顾问团队",
}
FEATURE_LABELS = {
    "recommendation_score": "推荐分数",
    "experience_years": "经验年限",
    "source_ai": "推荐来源：AI",
    "source_human": "推荐来源：人工",
    "education_level_bachelor": "学历：本科",
    "education_level_master": "学历：硕士",
    "education_level_phd": "学历：博士",
    "education_level_本科": "学历：本科",
    "education_level_硕士": "学历：硕士",
    "education_level_博士": "学历：博士",
    "job_category_技术": "岗位：技术",
    "job_category_运营": "岗位：运营",
    "job_category_销售": "岗位：销售",
    "region_华东": "地区：华东",
    "region_华北": "地区：华北",
    "region_华南": "地区：华南",
    "seniority_level_junior": "资深度：初级",
    "seniority_level_mid": "资深度：中级",
    "seniority_level_senior": "资深度：高级",
    "model_version_ai_ranker_2026_q1": "模型版本：AI 排序 2026 Q1",
    "model_version_ai_ranker_2026_q2": "模型版本：AI 排序 2026 Q2",
    "model_version_human_rule": "模型版本：人工规则",
    "recruiter_team_华东招聘组": "顾问团队：华东招聘组",
    "recruiter_team_华北招聘组": "顾问团队：华北招聘组",
    "recruiter_team_华南招聘组": "顾问团队：华南招聘组",
}
EVIDENCE_LABELS = {
    "High isolation score combined with prediction/outcome mismatch.": (
        "特征组合异常，且预测结果与实际结果存在明显不一致。"
    )
}
VALUE_LABELS = {
    "ai": "AI 推荐",
    "human": "人工推荐",
    "human_rule": "人工规则",
    "ai_ranker_2026_q1": "AI 排序 2026 Q1",
    "ai_ranker_2026_q2": "AI 排序 2026 Q2",
    "junior": "初级",
    "mid": "中级",
    "senior": "高级",
}


def feature_label(value: str) -> str:
    return FEATURE_LABELS.get(value, value.replace("_", "："))


def value_label(value: object) -> object:
    if not isinstance(value, str):
        return value
    return VALUE_LABELS.get(value, value)


def method_note_label(value: str) -> str:
    replacements = {
        "Logistic regression estimates the probability that a recommendation reaches interview.": (
            "逻辑回归用于估计一条推荐进入面试阶段的概率。"
        ),
        (
            "Feature contributions use model coefficients multiplied by observed feature values; "
            "they are directional signals, not causal effects."
        ): (
            "特征贡献由模型系数和特征值计算得到，用于解释方向性影响，不代表因果关系。"
        ),
        (
            "Isolation Forest flags unusual recommendations by feature profile and "
            "prediction/outcome mismatch."
        ): (
            "孤立森林用于识别特征组合异常、且预测结果与实际结果不一致的推荐样本。"
        ),
        (
            "This MVP avoids extra heavy dependencies; XGBoost/LightGBM and SHAP can "
            "replace the prediction and explanation layers later."
        ): (
            "当前版本避免引入较重依赖；后续可以升级为 XGBoost、LightGBM 和 SHAP。"
        ),
    }
    return replacements.get(value, value)


configure_page("机器学习洞察")
st.title("机器学习洞察")
st.caption("集中查看推荐成功概率、关键影响因素、异常推荐和分群转化表现。")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    result = get_prediction_insights(
        build_query(date_range, source, job_category, region, model_version, recruiter_team)
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()

summary = result["model_summary"]
metric_columns = st.columns(6)
metric_columns[0].metric("预测模型", MODEL_LABELS.get(summary["model_name"], summary["model_name"]))
metric_columns[1].metric("预测目标", TARGET_LABELS.get(summary["target"], summary["target"]))
metric_columns[2].metric("训练样本", f"{summary['sample_size']:,}")
metric_columns[3].metric("目标转化率", format_percent(summary["positive_rate"]))
metric_columns[4].metric("区分能力", f"{summary['auc']:.3f}")
metric_columns[5].metric("准确率", format_percent(summary["accuracy"]))
st.caption(f"异常检测模型：{MODEL_LABELS.get(summary['anomaly_model'], summary['anomaly_model'])}")

bands = pd.DataFrame(result["probability_bands"])
features = pd.DataFrame(result["top_features"])
segments = pd.DataFrame(result["segment_performance"])
anomalies = pd.DataFrame(result["anomaly_findings"])

left, right = st.columns([1.2, 1])
with left:
    st.subheader("推荐成功概率分层")
    if bands.empty:
        st.info("当前筛选范围没有足够样本生成概率分层。")
    else:
        band_fig = go.Figure()
        band_fig.add_bar(
            name="预测转化率",
            x=bands["band"],
            y=bands["predicted_conversion_rate"],
            marker_color="#2563EB",
        )
        band_fig.add_scatter(
            name="实际转化率",
            x=bands["band"],
            y=bands["actual_conversion_rate"],
            mode="lines+markers",
            line={"color": "#E76F51", "width": 3},
        )
        band_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
        band_fig.update_layout(
            legend_title_text="",
            height=360,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(band_fig, width="stretch")

with right:
    st.subheader("关键影响因素")
    if features.empty:
        st.info("当前筛选范围没有足够样本训练解释模型。")
    else:
        feature_plot = features.sort_values("importance", ascending=True).tail(10).copy()
        feature_plot["特征"] = feature_plot["feature"].map(feature_label)
        feature_plot["影响方向"] = feature_plot["direction"].map(DIRECTION_LABELS)
        feature_fig = px.bar(
            feature_plot,
            x="importance",
            y="特征",
            color="影响方向",
            orientation="h",
            color_discrete_map={"正向影响": "#2563EB", "负向影响": "#E76F51"},
            labels={"importance": "重要性", "影响方向": "影响方向"},
        )
        feature_fig.update_layout(
            legend_title_text="",
            height=360,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(feature_fig, width="stretch")

st.subheader("分群转化表现")
if segments.empty:
    st.info("当前筛选范围没有足够样本生成分群表现。")
else:
    segment_plot = segments.copy()
    segment_plot["分群类型"] = segment_plot["segment_type"].map(SEGMENT_TYPE_LABELS)
    segment_plot["分群取值"] = segment_plot["segment_value"].map(value_label)
    segment_fig = px.scatter(
        segment_plot,
        x="predicted_conversion_rate",
        y="actual_conversion_rate",
        size="recommendations",
        color="分群类型",
        hover_name="分群取值",
        hover_data={
            "lift_vs_average": ":.2%",
            "recommendations": ":,",
            "predicted_conversion_rate": ":.2%",
            "actual_conversion_rate": ":.2%",
        },
        labels={
            "predicted_conversion_rate": "预测转化率",
            "actual_conversion_rate": "实际转化率",
            "recommendations": "样本量",
            "lift_vs_average": "相对平均提升",
        },
    )
    segment_fig.add_shape(
        type="line",
        x0=0,
        y0=0,
        x1=1,
        y1=1,
        line={"dash": "dash", "color": "#94A3B8"},
    )
    segment_fig.update_xaxes(tickformat=".1%", range=[0, 1])
    segment_fig.update_yaxes(tickformat=".1%", range=[0, 1])
    segment_fig.update_layout(
        height=420,
        legend_title_text="",
        margin=dict(l=0, r=0, t=20, b=0),
    )
    st.plotly_chart(segment_fig, width="stretch")

st.subheader("异常推荐样本")
if anomalies.empty:
    st.success("当前筛选范围没有发现明显异常推荐样本。")
else:
    anomalies = anomalies.copy()
    anomalies["evidence"] = anomalies["evidence"].map(
        lambda value: EVIDENCE_LABELS.get(value, value)
    )
    anomalies["source"] = anomalies["source"].map(value_label)
    anomalies["model_version"] = anomalies["model_version"].map(value_label)
    anomalies["actual_outcome"] = anomalies["actual_outcome"].map(
        {1: "已面试", 0: "未面试"}
    )
    anomaly_display = anomalies.rename(
        columns={
            "recommendation_id": "推荐 ID",
            "anomaly_score": "异常分数",
            "predicted_conversion_probability": "预测转化概率",
            "actual_outcome": "实际是否面试",
            "source": "推荐来源",
            "job_category": "岗位",
            "region": "地区",
            "model_version": "模型版本",
            "recruiter_team": "顾问团队",
            "evidence": "证据",
        }
    )
    render_table(anomaly_display, hide_index=True, width="stretch")

with st.expander("方法说明"):
    st.markdown("\n".join(f"- {method_note_label(note)}" for note in result["method_notes"]))
