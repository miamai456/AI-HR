import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from app.api_client import ALL_OPTION, ApiError, get_filters

SOURCE_LABELS = {"ai": "AI 推荐", "human": "人工推荐"}
SOURCE_COLORS = {"ai": "#2563EB", "human": "#E76F51"}
FILTER_STATE_FILE = Path(".aihr_filter_state.json")

FILTER_DATE_KEY = "aihr_filter_date_range"
FILTER_SOURCE_KEY = "aihr_filter_source"
FILTER_JOB_KEY = "aihr_filter_job_category"
FILTER_REGION_KEY = "aihr_filter_region"
FILTER_MODEL_KEY = "aihr_filter_model_version"
FILTER_RECRUITER_KEY = "aihr_filter_recruiter_team"
FILTER_QUERY_NAMES = {
    FILTER_SOURCE_KEY: "source",
    FILTER_JOB_KEY: "job_category",
    FILTER_REGION_KEY: "region",
    FILTER_MODEL_KEY: "model_version",
    FILTER_RECRUITER_KEY: "recruiter_team",
}


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
        .aihr-table {overflow-x: auto; border: 1px solid #E5E7EB; border-radius: 6px;}
        .aihr-table table {border-collapse: collapse; width: 100%; font-size: 0.92rem;}
        .aihr-table th {background: #F8FAFC; color: #0F172A; font-weight: 700;}
        .aihr-table th, .aihr-table td {
            border-bottom: 1px solid #E5E7EB;
            padding: 0.55rem 0.7rem;
            text-align: left;
            white-space: nowrap;
        }
        .aihr-table tr:last-child td {border-bottom: 0;}
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=60)
def load_filter_options() -> dict:
    return get_filters()


def _read_saved_filter_state() -> dict[str, str]:
    if not FILTER_STATE_FILE.exists():
        return {}
    try:
        return json.loads(FILTER_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_saved_filter_state(values: dict[str, str]) -> None:
    FILTER_STATE_FILE.write_text(
        json.dumps(values, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _query_value(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _query_date(name: str, fallback: date, date_min: date, date_max: date) -> date:
    saved_state = _read_saved_filter_state()
    value = _query_value(name) or saved_state.get(name)
    if value:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return fallback
        return min(max(parsed, date_min), date_max)
    return fallback


def _query_choice(name: str, choices: list[str]) -> str:
    saved_state = _read_saved_filter_state()
    value = _query_value(name) or saved_state.get(name)
    return value if value in choices else choices[0]


def _reset_filter_state(date_min: date, date_max: date) -> None:
    st.session_state[FILTER_DATE_KEY] = (date_min, date_max)
    st.session_state[FILTER_SOURCE_KEY] = ALL_OPTION
    st.session_state[FILTER_JOB_KEY] = ALL_OPTION
    st.session_state[FILTER_REGION_KEY] = ALL_OPTION
    st.session_state[FILTER_MODEL_KEY] = ALL_OPTION
    st.session_state[FILTER_RECRUITER_KEY] = ALL_OPTION
    st.query_params.clear()
    st.query_params["start_date"] = date_min.isoformat()
    st.query_params["end_date"] = date_max.isoformat()
    _write_saved_filter_state(
        {
            "start_date": date_min.isoformat(),
            "end_date": date_max.isoformat(),
            "source": ALL_OPTION,
            "job_category": ALL_OPTION,
            "region": ALL_OPTION,
            "model_version": ALL_OPTION,
            "recruiter_team": ALL_OPTION,
        }
    )


def _ensure_select_value(key: str, choices: list[str]) -> None:
    if st.session_state.get(key) not in choices:
        st.session_state[key] = choices[0]


def _ensure_date_range(date_min: date, date_max: date) -> None:
    value = st.session_state.get(FILTER_DATE_KEY)
    if (
        not isinstance(value, (tuple, list))
        or len(value) != 2
        or value[0] < date_min
        or value[-1] > date_max
    ):
        start_date = _query_date("start_date", date_min, date_min, date_max)
        end_date = _query_date("end_date", date_max, date_min, date_max)
        st.session_state[FILTER_DATE_KEY] = (start_date, end_date)


def _initialize_select_value(key: str, choices: list[str]) -> None:
    if key not in st.session_state:
        st.session_state[key] = _query_choice(FILTER_QUERY_NAMES[key], choices)
    _ensure_select_value(key, choices)


def _sync_filter_query_params(
    date_range: list[date],
    source: str,
    job_category: str,
    region: str,
    model_version: str,
    recruiter_team: str,
) -> None:
    if len(date_range) == 2:
        st.query_params["start_date"] = date_range[0].isoformat()
        st.query_params["end_date"] = date_range[-1].isoformat()

    for name, value in {
        "source": source,
        "job_category": job_category,
        "region": region,
        "model_version": model_version,
        "recruiter_team": recruiter_team,
    }.items():
        if value == ALL_OPTION:
            st.query_params.pop(name, None)
        else:
            st.query_params[name] = value
    _write_saved_filter_state(
        {
            "start_date": date_range[0].isoformat() if len(date_range) == 2 else "",
            "end_date": date_range[-1].isoformat() if len(date_range) == 2 else "",
            "source": source,
            "job_category": job_category,
            "region": region,
            "model_version": model_version,
            "recruiter_team": recruiter_team,
        }
    )


def render_filters() -> tuple[list[date], str, str, str, str, str]:
    try:
        options = load_filter_options()
    except ApiError as exc:
        st.error(str(exc))
        st.stop()

    date_min = date.fromisoformat(options["date_min"])
    date_max = date.fromisoformat(options["date_max"])
    source_choices = [ALL_OPTION, *options["sources"]]
    job_choices = [ALL_OPTION, *options["job_categories"]]
    region_choices = [ALL_OPTION, *options["regions"]]
    model_choices = [ALL_OPTION, *options["model_versions"]]
    recruiter_choices = [ALL_OPTION, *options["recruiter_teams"]]

    _ensure_date_range(date_min, date_max)
    _initialize_select_value(FILTER_SOURCE_KEY, source_choices)
    _initialize_select_value(FILTER_JOB_KEY, job_choices)
    _initialize_select_value(FILTER_REGION_KEY, region_choices)
    _initialize_select_value(FILTER_MODEL_KEY, model_choices)
    _initialize_select_value(FILTER_RECRUITER_KEY, recruiter_choices)

    st.sidebar.header("分析范围")
    if st.sidebar.button("重置分析范围", use_container_width=True):
        _reset_filter_state(date_min, date_max)
        st.rerun()

    date_range = st.sidebar.date_input(
        "推荐日期",
        min_value=date_min,
        max_value=date_max,
        key=FILTER_DATE_KEY,
    )
    source = st.sidebar.selectbox("推荐来源", source_choices, key=FILTER_SOURCE_KEY)
    job_category = st.sidebar.selectbox("岗位", job_choices, key=FILTER_JOB_KEY)
    region = st.sidebar.selectbox("地区", region_choices, key=FILTER_REGION_KEY)
    model_version = st.sidebar.selectbox("模型版本", model_choices, key=FILTER_MODEL_KEY)
    recruiter_team = st.sidebar.selectbox("顾问团队", recruiter_choices, key=FILTER_RECRUITER_KEY)
    st.sidebar.caption("当前公开演示使用固定种子的合成招聘事件。")
    selected_date_range = list(date_range)
    _sync_filter_query_params(
        selected_date_range,
        source,
        job_category,
        region,
        model_version,
        recruiter_team,
    )
    return selected_date_range, source, job_category, region, model_version, recruiter_team


def format_percent(value: float) -> str:
    return f"{value:.1%}"


def render_table(dataframe: pd.DataFrame, **_ignored) -> None:
    if dataframe.empty:
        st.info("当前筛选范围没有可展示的表格数据。")
        return
    st.markdown(
        f'<div class="aihr-table">{dataframe.to_html(index=False, escape=True)}</div>',
        unsafe_allow_html=True,
    )
