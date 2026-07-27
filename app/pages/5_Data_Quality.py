import pandas as pd
import streamlit as st

from app.api_client import ApiError, build_query, get_data_quality
from app.ui import configure_page, render_filters

configure_page("AIHR 数据质量")
st.title("AIHR 数据质量")

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
metric_columns = st.columns(4)
metric_columns[0].metric("检查项", f"{summary['total_checks']:,}")
metric_columns[1].metric("失败", f"{summary['failed_checks']:,}")
metric_columns[2].metric("预警", f"{summary['warning_checks']:,}")
metric_columns[3].metric("生成时间", summary["generated_at"].replace("T", " ")[:19])

st.subheader("各层记录数和更新时间")
layers = pd.DataFrame(result["layers"])
if not layers.empty:
    layer_display = layers.rename(
        columns={
            "layer_name": "层级/表",
            "layer_type": "层级类型",
            "record_count": "记录数",
            "last_updated_at": "最后更新时间",
        }
    )
    st.dataframe(layer_display, hide_index=True, width="stretch")

st.subheader("质量检查结果")
checks = pd.DataFrame(result["checks"])
if checks.empty:
    st.info("暂无数据质量检查结果。")
else:
    checks["details"] = checks["details"].apply(lambda value: str(value))
    check_display = checks.rename(
        columns={
            "check_type": "检查类型",
            "check_name": "检查项",
            "status": "状态",
            "severity": "严重程度",
            "evidence_metric": "证据指标",
            "affected_count": "影响数",
            "sample_size": "样本量",
            "period_start": "开始日期",
            "period_end": "结束日期",
            "details": "结构化详情",
        }
    )
    st.dataframe(check_display, hide_index=True, width="stretch")
