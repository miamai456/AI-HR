import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.api_client import ApiError, build_query, get_prediction_insights
from app.ui import (
    configure_page,
    format_percent,
    render_ai_assistant,
    render_filters,
    render_table,
)

MODEL_LABELS = {
    "logistic_regression_conversion": "Logistic Regression 转化预测",
    "isolation_forest": "Isolation Forest 异常检测",
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
    "source_ai": "推荐来源: AI",
    "source_human": "推荐来源: 人工",
    "education_level_bachelor": "学历: 本科",
    "education_level_master": "学历: 硕士",
    "education_level_phd": "学历: 博士",
    "education_level_本科": "学历: 本科",
    "education_level_硕士": "学历: 硕士",
    "education_level_博士": "学历: 博士",
    "job_category_技术": "岗位: 技术",
    "job_category_运营": "岗位: 运营",
    "job_category_销售": "岗位: 销售",
    "region_华东": "地区: 华东",
    "region_华北": "地区: 华北",
    "region_华南": "地区: 华南",
    "seniority_level_junior": "资深度: 初级",
    "seniority_level_mid": "资深度: 中级",
    "seniority_level_senior": "资深度: 高级",
    "model_version_ai_ranker_2026_q1": "模型版本: AI 排序 2026 Q1",
    "model_version_ai_ranker_2026_q2": "模型版本: AI 排序 2026 Q2",
    "model_version_human_rule": "模型版本: 人工规则",
    "recruiter_team_华东招聘组": "顾问团队: 华东招聘组",
    "recruiter_team_华北招聘组": "顾问团队: 华北招聘组",
    "recruiter_team_华南招聘组": "顾问团队: 华南招聘组",
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
METHOD_NOTE_LABELS = {
    "Logistic regression estimates the probability that a recommendation reaches interview.": (
        "Logistic Regression 用于估计每条推荐进入面试阶段的概率。"
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
        "Isolation Forest 用于识别特征组合异常、且预测与实际结果不一致的推荐样本。"
    ),
    (
        "This MVP avoids extra heavy dependencies; XGBoost/LightGBM and SHAP can "
        "replace the prediction and explanation layers later."
    ): (
        "当前版本避免引入重依赖；后续可以升级为 XGBoost、LightGBM 和 SHAP 解释层。"
    ),
}


def feature_label(value: str) -> str:
    return FEATURE_LABELS.get(value, value.replace("_", ": "))


def value_label(value: object) -> object:
    if not isinstance(value, str):
        return value
    return VALUE_LABELS.get(value, value)


def method_note_label(value: str) -> str:
    return METHOD_NOTE_LABELS.get(value, value)


def quality_label(auc: float) -> str:
    if auc >= 0.8:
        return "强"
    if auc >= 0.7:
        return "可用"
    if auc >= 0.6:
        return "需观察"
    return "弱"


def calibration_label(mean_gap: float) -> str:
    if mean_gap <= 0.03:
        return "校准稳定"
    if mean_gap <= 0.08:
        return "存在偏差"
    return "偏差较大"


def render_insight_tiles(summary: dict, bands: pd.DataFrame, segments: pd.DataFrame) -> None:
    mean_gap = 0.0
    top_band_lift = 0.0
    segment_spread = 0.0
    if not bands.empty:
        mean_gap = float(bands["calibration_gap_abs"].mean())
        top_band_lift = float(bands["lift_vs_average"].max())
    if not segments.empty:
        segment_spread = float(
            segments["actual_conversion_rate"].max()
            - segments["actual_conversion_rate"].min()
        )

    st.markdown(
        f"""
        <div class="aihr-insight-grid">
            <div class="aihr-insight">
                <span>模型是否能排序候选人</span>
                <strong>{quality_label(summary["auc"])}</strong>
                <small>AUC {summary["auc"]:.3f}，用于判断高概率推荐是否更容易进入面试。</small>
            </div>
            <div class="aihr-insight">
                <span>预测概率是否贴近实际</span>
                <strong>{calibration_label(mean_gap)}</strong>
                <small>平均校准差 {mean_gap:.1%}，越低说明预测概率越可信。</small>
            </div>
            <div class="aihr-insight">
                <span>高分推荐带来的提升</span>
                <strong>{top_band_lift:+.1%}</strong>
                <small>最高概率层相对整体平均面试率的提升。</small>
            </div>
            <div class="aihr-insight">
                <span>分群之间是否有明显差异</span>
                <strong>{segment_spread:.1%}</strong>
                <small>分群最高与最低实际面试率的差距，用于定位机会和风险。</small>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def prepare_bands(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    result = dataframe.copy()
    result["expected_interviews"] = (
        result["recommendations"] * result["predicted_conversion_rate"]
    )
    result["actual_interviews"] = (
        result["recommendations"] * result["actual_conversion_rate"]
    )
    result["calibration_gap"] = (
        result["actual_conversion_rate"] - result["predicted_conversion_rate"]
    )
    result["calibration_gap_abs"] = result["calibration_gap"].abs()
    return result


def prepare_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    result = dataframe.copy()
    result["特征"] = result["feature"].map(feature_label)
    result["影响方向"] = result["direction"].map(DIRECTION_LABELS)
    result["signed_importance"] = result["importance"].where(
        result["direction"].eq("positive"),
        -result["importance"],
    )
    return result


def prepare_segments(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    result = dataframe.copy()
    result["分群类型"] = result["segment_type"].map(SEGMENT_TYPE_LABELS)
    result["分群取值"] = result["segment_value"].map(value_label)
    result["机会方向"] = result["lift_vs_average"].map(
        lambda value: "高于平均" if value >= 0 else "低于平均"
    )
    result["calibration_gap"] = (
        result["actual_conversion_rate"] - result["predicted_conversion_rate"]
    )
    return result


def prepare_threshold_simulation(bands: pd.DataFrame) -> pd.DataFrame:
    if bands.empty:
        return pd.DataFrame()
    result = bands.copy()
    result["lower_bound"] = result["band"].str.extract(r"^(\d+)").astype(float) / 100
    result = result.sort_values("lower_bound", ascending=False).copy()
    result["cumulative_recommendations"] = result["recommendations"].cumsum()
    result["cumulative_actual_interviews"] = result["actual_interviews"].cumsum()
    result["cumulative_expected_interviews"] = result["expected_interviews"].cumsum()
    result["cumulative_actual_rate"] = (
        result["cumulative_actual_interviews"] / result["cumulative_recommendations"]
    )
    result["cumulative_expected_rate"] = (
        result["cumulative_expected_interviews"] / result["cumulative_recommendations"]
    )
    result["阈值策略"] = result["lower_bound"].map(lambda value: f"优先处理 >= {value:.0%}")
    return result


configure_page("机器学习洞察")
st.markdown(
    """
    <style>
    .aihr-insight-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.8rem;
        margin: 0.75rem 0 1rem;
    }
    .aihr-insight {
        border: 1px solid #E5E7EB;
        border-radius: 6px;
        padding: 0.85rem 0.95rem;
        background: #FFFFFF;
    }
    .aihr-insight span {
        display: block;
        color: #475569;
        font-size: 0.84rem;
        line-height: 1.25;
    }
    .aihr-insight strong {
        display: block;
        color: #0F172A;
        font-size: 1.35rem;
        line-height: 1.35;
        margin-top: 0.25rem;
    }
    .aihr-insight small {
        display: block;
        color: #64748B;
        line-height: 1.45;
        margin-top: 0.2rem;
    }
    @media (max-width: 900px) {
        .aihr-insight-grid {grid-template-columns: repeat(2, minmax(0, 1fr));}
    }
    @media (max-width: 560px) {
        .aihr-insight-grid {grid-template-columns: 1fr;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("机器学习洞察")
st.caption(
    "把推荐效果拆成模型判别力、概率校准、关键驱动因素、分群机会和异常样本，让招聘推荐数据形成一条可解释的分析链路。"
)

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
bands = prepare_bands(pd.DataFrame(result["probability_bands"]))
features = prepare_features(pd.DataFrame(result["top_features"]))
segments = prepare_segments(pd.DataFrame(result["segment_performance"]))
anomalies = pd.DataFrame(result["anomaly_findings"])
thresholds = prepare_threshold_simulation(bands)

metric_columns = st.columns(6)
metric_columns[0].metric("预测模型", MODEL_LABELS.get(summary["model_name"], summary["model_name"]))
metric_columns[1].metric("预测目标", TARGET_LABELS.get(summary["target"], summary["target"]))
metric_columns[2].metric("训练样本", f"{summary['sample_size']:,}")
metric_columns[3].metric("面试转化率", format_percent(summary["positive_rate"]))
metric_columns[4].metric("AUC 判别力", f"{summary['auc']:.3f}", quality_label(summary["auc"]))
metric_columns[5].metric("Accuracy", format_percent(summary["accuracy"]))
st.caption(f"异常检测模型: {MODEL_LABELS.get(summary['anomaly_model'], summary['anomaly_model'])}")

render_insight_tiles(summary, bands, segments)

if bands.empty and features.empty and segments.empty and anomalies.empty:
    st.info("当前筛选范围没有足够样本生成机器学习洞察。")
    with st.expander("方法说明"):
        st.markdown("\n".join(f"- {method_note_label(note)}" for note in result["method_notes"]))
    st.stop()

overview_tab, segment_tab, anomaly_tab = st.tabs(
    ["模型表现", "分群与特征", "异常复核"]
)

with overview_tab:
    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("预测概率分层与实际面试率")
        if bands.empty:
            st.info("当前筛选范围没有足够样本生成概率分层。")
        else:
            band_fig = go.Figure()
            band_fig.add_bar(
                name="预测面试率",
                x=bands["band"],
                y=bands["predicted_conversion_rate"],
                marker_color="#2563EB",
                customdata=bands[["recommendations"]],
                hovertemplate=(
                    "%{x}<br>预测面试率: %{y:.2%}"
                    "<br>推荐数: %{customdata[0]:,}<extra></extra>"
                ),
            )
            band_fig.add_scatter(
                name="实际面试率",
                x=bands["band"],
                y=bands["actual_conversion_rate"],
                mode="lines+markers",
                line={"color": "#E76F51", "width": 3},
                hovertemplate="%{x}<br>实际面试率: %{y:.2%}<extra></extra>",
            )
            band_fig.update_yaxes(tickformat=".1%", rangemode="tozero")
            band_fig.update_layout(
                legend_title_text="",
                height=380,
                hovermode="x unified",
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(band_fig, width="stretch")

    with right:
        st.subheader("校准差与层级提升")
        if bands.empty:
            st.info("当前筛选范围没有可展示的校准结果。")
        else:
            lift_fig = px.bar(
                bands,
                x="lift_vs_average",
                y="band",
                orientation="h",
                color="calibration_gap",
                color_continuous_scale=["#E76F51", "#F8FAFC", "#2563EB"],
                labels={
                    "lift_vs_average": "相对平均面试率提升",
                    "band": "预测概率层",
                    "calibration_gap": "实际-预测",
                },
                hover_data={
                    "recommendations": ":,",
                    "predicted_conversion_rate": ":.2%",
                    "actual_conversion_rate": ":.2%",
                    "calibration_gap": ":.2%",
                },
            )
            lift_fig.add_vline(x=0, line_dash="dash", line_color="#94A3B8")
            lift_fig.update_xaxes(tickformat="+.1%")
            lift_fig.update_layout(
                height=380,
                coloraxis_colorbar_title="校准差",
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(lift_fig, width="stretch")

    st.subheader("预测面试量与实际面试量")
    if not bands.empty:
        volume_fig = go.Figure()
        volume_fig.add_bar(
            name="预测面试量",
            x=bands["band"],
            y=bands["expected_interviews"],
            marker_color="#60A5FA",
        )
        volume_fig.add_bar(
            name="实际面试量",
            x=bands["band"],
            y=bands["actual_interviews"],
            marker_color="#2A9D8F",
        )
        volume_fig.update_layout(
            barmode="group",
            legend_title_text="",
            height=340,
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(volume_fig, width="stretch")

    st.subheader("推荐阈值模拟")
    if thresholds.empty:
        st.info("当前筛选范围没有可模拟的概率阈值。")
    else:
        threshold_fig = go.Figure()
        threshold_fig.add_bar(
            name="累计推荐量",
            x=thresholds["阈值策略"],
            y=thresholds["cumulative_recommendations"],
            marker_color="#94A3B8",
            yaxis="y",
        )
        threshold_fig.add_scatter(
            name="累计实际面试率",
            x=thresholds["阈值策略"],
            y=thresholds["cumulative_actual_rate"],
            mode="lines+markers",
            line={"color": "#2563EB", "width": 3},
            yaxis="y2",
        )
        threshold_fig.update_layout(
            height=360,
            legend_title_text="",
            margin=dict(l=0, r=0, t=20, b=0),
            yaxis={"title": "累计推荐量"},
            yaxis2={
                "title": "累计实际面试率",
                "overlaying": "y",
                "side": "right",
                "tickformat": ".1%",
            },
        )
        st.plotly_chart(threshold_fig, width="stretch")

        threshold_display = thresholds[
            [
                "阈值策略",
                "cumulative_recommendations",
                "cumulative_expected_rate",
                "cumulative_actual_rate",
            ]
        ].rename(
            columns={
                "cumulative_recommendations": "累计推荐量",
                "cumulative_expected_rate": "累计预测面试率",
                "cumulative_actual_rate": "累计实际面试率",
            }
        )
        threshold_display["累计预测面试率"] = threshold_display["累计预测面试率"].map(
            lambda value: f"{value:.1%}"
        )
        threshold_display["累计实际面试率"] = threshold_display["累计实际面试率"].map(
            lambda value: f"{value:.1%}"
        )
        render_table(threshold_display, hide_index=True, width="stretch")

with segment_tab:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("关键影响因素")
        if features.empty:
            st.info("当前筛选范围没有足够样本训练解释模型。")
        else:
            feature_plot = features.sort_values("signed_importance", ascending=True).tail(12)
            feature_fig = px.bar(
                feature_plot,
                x="signed_importance",
                y="特征",
                color="影响方向",
                orientation="h",
                color_discrete_map={"正向影响": "#2563EB", "负向影响": "#E76F51"},
                labels={"signed_importance": "方向化重要性", "影响方向": "影响方向"},
                hover_data={"importance": ":.4f", "average_contribution": ":.4f"},
            )
            feature_fig.add_vline(x=0, line_dash="dash", line_color="#94A3B8")
            feature_fig.update_layout(
                legend_title_text="",
                height=430,
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(feature_fig, width="stretch")

    with right:
        st.subheader("分群预测-实际对照")
        if segments.empty:
            st.info("当前筛选范围没有足够样本生成分群表现。")
        else:
            segment_fig = px.scatter(
                segments,
                x="predicted_conversion_rate",
                y="actual_conversion_rate",
                size="recommendations",
                color="机会方向",
                hover_name="分群取值",
                symbol="分群类型",
                color_discrete_map={"高于平均": "#2563EB", "低于平均": "#E76F51"},
                hover_data={
                    "分群类型": True,
                    "lift_vs_average": ":.2%",
                    "recommendations": ":,",
                    "predicted_conversion_rate": ":.2%",
                    "actual_conversion_rate": ":.2%",
                    "calibration_gap": ":.2%",
                },
                labels={
                    "predicted_conversion_rate": "预测面试率",
                    "actual_conversion_rate": "实际面试率",
                    "recommendations": "样本量",
                    "lift_vs_average": "相对平均提升",
                    "calibration_gap": "实际-预测",
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
                height=430,
                legend_title_text="",
                margin=dict(l=0, r=0, t=20, b=0),
            )
            st.plotly_chart(segment_fig, width="stretch")

    st.subheader("分群机会清单")
    if not segments.empty:
        segment_display = segments.sort_values("lift_vs_average", ascending=False).rename(
            columns={
                "分群类型": "分群类型",
                "分群取值": "分群取值",
                "recommendations": "推荐数",
                "predicted_conversion_rate": "预测面试率",
                "actual_conversion_rate": "实际面试率",
                "lift_vs_average": "相对平均提升",
                "calibration_gap": "实际-预测",
            }
        )[
            [
                "分群类型",
                "分群取值",
                "推荐数",
                "预测面试率",
                "实际面试率",
                "相对平均提升",
                "实际-预测",
            ]
        ]
        for column in ["预测面试率", "实际面试率", "相对平均提升", "实际-预测"]:
            segment_display[column] = segment_display[column].map(lambda value: f"{value:+.1%}")
        render_table(segment_display, hide_index=True, width="stretch")

with anomaly_tab:
    st.subheader("异常样本复核矩阵")
    if anomalies.empty:
        st.success("当前筛选范围没有发现明显异常推荐样本。")
    else:
        anomalies = anomalies.copy()
        anomalies["evidence"] = anomalies["evidence"].map(
            lambda value: EVIDENCE_LABELS.get(value, value)
        )
        anomalies["source"] = anomalies["source"].map(value_label)
        anomalies["model_version"] = anomalies["model_version"].map(value_label)
        anomalies["actual_outcome_label"] = anomalies["actual_outcome"].map(
            {1: "已面试", 0: "未面试"}
        )
        risk_fig = px.scatter(
            anomalies,
            x="predicted_conversion_probability",
            y="anomaly_score",
            color="actual_outcome_label",
            symbol="source",
            hover_name="recommendation_id",
            hover_data={
                "job_category": True,
                "region": True,
                "model_version": True,
                "recruiter_team": True,
                "evidence": True,
                "predicted_conversion_probability": ":.2%",
                "anomaly_score": ":.4f",
            },
            color_discrete_map={"已面试": "#2563EB", "未面试": "#E76F51"},
            labels={
                "predicted_conversion_probability": "预测面试概率",
                "anomaly_score": "异常分数",
                "actual_outcome_label": "实际结果",
                "source": "推荐来源",
            },
        )
        risk_fig.update_xaxes(tickformat=".1%", range=[0, 1])
        risk_fig.update_layout(
            height=420,
            legend_title_text="",
            margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(risk_fig, width="stretch")

        anomaly_display = anomalies.rename(
            columns={
                "recommendation_id": "推荐 ID",
                "anomaly_score": "异常分数",
                "predicted_conversion_probability": "预测面试概率",
                "actual_outcome_label": "实际是否面试",
                "source": "推荐来源",
                "job_category": "岗位",
                "region": "地区",
                "model_version": "模型版本",
                "recruiter_team": "顾问团队",
                "evidence": "证据",
            }
        )[
            [
                "推荐 ID",
                "异常分数",
                "预测面试概率",
                "实际是否面试",
                "推荐来源",
                "岗位",
                "地区",
                "模型版本",
                "顾问团队",
                "证据",
            ]
        ]
        anomaly_display["预测面试概率"] = anomaly_display["预测面试概率"].map(
            lambda value: f"{value:.1%}"
        )
        render_table(anomaly_display, hide_index=True, width="stretch")

with st.expander("方法说明"):
    st.markdown("\n".join(f"- {method_note_label(note)}" for note in result["method_notes"]))

render_ai_assistant(
    "prediction",
    "机器学习洞察",
    {
        "page": "机器学习洞察",
        "metrics": summary,
        "data": {
            "prediction": result,
            "probability_bands": result["probability_bands"],
            "top_features": result["top_features"],
            "segment_performance": result["segment_performance"],
            "anomaly_findings": result["anomaly_findings"],
            "threshold_simulation": thresholds.to_dict(orient="records"),
        },
        "warnings": [
            "特征贡献是方向性解释，不代表因果关系。",
            "异常检测用于提示复核，不代表样本一定错误。",
        ],
    },
    [
        "模型预测结果是否可信？",
        "哪些特征和分群最值得关注？",
        "异常样本应该如何复核？",
    ],
)
