import pandas as pd
import plotly.express as px
import streamlit as st

from app.api_client import ApiError, build_query, get_data_quality
from app.ui import (
    configure_page,
    render_ai_assistant,
    render_filters,
    render_insight_box,
    render_table,
)


def status_label(value: str) -> str:
    return {"pass": "通过", "warning": "预警", "fail": "失败"}.get(value, value)


def severity_label(value: str) -> str:
    return {"low": "低", "medium": "中", "high": "高"}.get(value, value)


configure_page("AIHR 数据质量")
st.title("AIHR 数据质量")
st.caption("从数据层级、质量检查和受影响样本判断当前分析结论是否可信。")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

try:
    result = get_data_quality(
        build_query(date_range, source, job_category, region, model_version, recruiter_team)
    )
except ApiError as exc:
    st.error(str(exc))
    st.stop()

summary = result["summary"]
layers = pd.DataFrame(result["layers"])
checks = pd.DataFrame(result["checks"])

metric_columns = st.columns(4)
metric_columns[0].metric("检查项", f"{summary['total_checks']:,}")
metric_columns[1].metric("失败", f"{summary['failed_checks']:,}")
metric_columns[2].metric("预警", f"{summary['warning_checks']:,}")
metric_columns[3].metric("生成时间", summary["generated_at"].replace("T", " ")[:19])

trust_status = "可信"
if summary["failed_checks"]:
    trust_status = "需修复后再下结论"
elif summary["warning_checks"]:
    trust_status = "可分析但需标注限制"

affected_total = int(checks["affected_count"].sum()) if not checks.empty else 0
sample_total = int(checks["sample_size"].sum()) if not checks.empty else 0
insights = [
    f"当前数据可信度判断：{trust_status}。",
    f"质量检查共覆盖 {sample_total:,} 条检查样本，受影响记录合计 {affected_total:,} 条。",
    "如果失败项集中在核心事实表或推荐事件层，应优先修复后再解释模型效果。",
]
render_insight_box("数据质量结论", insights)

tab_layer, tab_check, tab_impact = st.tabs(["数据层级", "质量检查", "影响范围"])

with tab_layer:
    if layers.empty:
        st.info("当前范围没有层级记录。")
    else:
        layer_fig = px.bar(
            layers.sort_values("record_count"),
            x="record_count",
            y="layer_name",
            color="layer_type",
            orientation="h",
            labels={"record_count": "记录数", "layer_name": "层级/表", "layer_type": "层级类型"},
            hover_data=["last_updated_at"],
        )
        layer_fig.update_layout(height=430, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(layer_fig, width="stretch")

        layer_display = layers.rename(
            columns={
                "layer_name": "层级/表",
                "layer_type": "层级类型",
                "record_count": "记录数",
                "last_updated_at": "最后更新时间",
            }
        )
        render_table(layer_display, hide_index=True, width="stretch")

with tab_check:
    if checks.empty:
        st.info("暂无数据质量检查结果。")
    else:
        status_counts = checks.groupby(["status", "severity"], as_index=False).size()
        status_counts["状态"] = status_counts["status"].map(status_label)
        status_counts["严重度"] = status_counts["severity"].map(severity_label)
        status_fig = px.bar(
            status_counts,
            x="状态",
            y="size",
            color="严重度",
            labels={"size": "检查项数量"},
            color_discrete_map={"低": "#2A9D8F", "中": "#F4A261", "高": "#E76F51"},
        )
        status_fig.update_layout(height=330, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(status_fig, width="stretch")

        check_display = checks.copy()
        check_display["details"] = check_display["details"].apply(lambda value: str(value))
        check_display["status"] = check_display["status"].map(status_label)
        check_display["severity"] = check_display["severity"].map(severity_label)
        check_display = check_display.rename(
            columns={
                "check_type": "检查类型",
                "check_name": "检查项",
                "status": "状态",
                "severity": "严重度",
                "evidence_metric": "证据指标",
                "affected_count": "影响数",
                "sample_size": "样本量",
                "period_start": "开始日期",
                "period_end": "结束日期",
                "details": "结构化详情",
            }
        )
        render_table(check_display, hide_index=True, width="stretch")

with tab_impact:
    if checks.empty:
        st.info("暂无影响范围数据。")
    else:
        impact = checks.sort_values("affected_count", ascending=False).head(10)
        impact_fig = px.bar(
            impact,
            x="affected_count",
            y="check_name",
            color="severity",
            orientation="h",
            labels={"affected_count": "影响记录数", "check_name": "检查项", "severity": "严重度"},
            color_discrete_map={"low": "#2A9D8F", "medium": "#F4A261", "high": "#E76F51"},
            hover_data=["sample_size", "evidence_metric"],
        )
        impact_fig.update_layout(height=430, legend_title_text="", margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(impact_fig, width="stretch")

render_ai_assistant(
    "data_quality",
    "数据质量",
    {
        "page": "数据质量",
        "insights": insights,
        "metrics": {
            "total_checks": summary["total_checks"],
            "failed_checks": summary["failed_checks"],
            "warning_checks": summary["warning_checks"],
            "affected_total": affected_total,
            "sample_total": sample_total,
        },
        "data": {
            "data_quality": result,
            "layers": result["layers"],
            "checks": result["checks"],
        },
    },
    [
        "当前数据是否足够支撑分析结论？",
        "哪些质量问题最影响看板可信度？",
        "第一次看数据质量页应该怎么看？",
    ],
)
