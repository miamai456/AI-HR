from datetime import date

import streamlit as st

from app.api_client import ApiError, get_filters

SOURCE_LABELS = {"ai": "AI 推荐", "human": "人工推荐"}
SOURCE_COLORS = {"ai": "#2563EB", "human": "#E76F51"}
ALL_OPTION = "全部"


def configure_page(title: str) -> None:
    st.set_page_config(
        page_title=f"{title} | AIHR",
        page_icon=":material/analytics:",
        layout="wide",
    )
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 2rem; max-width: 1440px;}
        [data-testid="stMetric"] {border-top: 2px solid #D1D5DB; padding-top: 0.75rem;}
        [data-testid="stSidebar"] {border-right: 1px solid #E5E7EB;}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60)
def load_filter_options() -> dict:
    return get_filters()


def render_filters() -> tuple[list[date], str, str, str, str, str]:
    try:
        options = load_filter_options()
    except ApiError as exc:
        st.error(str(exc))
        st.stop()

    st.sidebar.header("分析范围")
    date_range = st.sidebar.date_input(
        "推荐日期",
        value=(date.fromisoformat(options["date_min"]), date.fromisoformat(options["date_max"])),
        min_value=date.fromisoformat(options["date_min"]),
        max_value=date.fromisoformat(options["date_max"]),
    )
    source = st.sidebar.selectbox("推荐来源", [ALL_OPTION, *options["sources"]])
    job_category = st.sidebar.selectbox("岗位", [ALL_OPTION, *options["job_categories"]])
    region = st.sidebar.selectbox("地区", [ALL_OPTION, *options["regions"]])
    model_version = st.sidebar.selectbox("模型版本", [ALL_OPTION, *options["model_versions"]])
    recruiter_team = st.sidebar.selectbox("顾问团队", [ALL_OPTION, *options["recruiter_teams"]])
    st.sidebar.caption("当前公开演示使用固定种子的合成招聘事件。")
    return list(date_range), source, job_category, region, model_version, recruiter_team


def format_percent(value: float) -> str:
    return f"{value:.1%}"
