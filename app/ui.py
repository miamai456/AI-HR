import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from app.analysis_assistant import (
    answer_question,
    assistant_config_summary,
    assistant_configured,
    prepare_analysis_context,
    split_assistant_answer,
)
from app.api_client import ALL_OPTION, ApiError, get_filters
from app.assistant_session import (
    append_unique_question,
    clear_conversation,
    conversation_for_regeneration,
)

SOURCE_LABELS = {"ai": "AI 推荐", "human": "人工推荐"}
SOURCE_COLORS = {"ai": "#2563EB", "human": "#E76F51"}
SEVERITY_LABELS = {"low": "正常", "medium": "关注", "high": "高风险"}
SEVERITY_COLORS = {"low": "#2A9D8F", "medium": "#F4A261", "high": "#E76F51"}
FILTER_STATE_FILE = Path(".aihr_filter_state.json")

FILTER_DATE_KEY = "aihr_filter_date_range"
FILTER_SOURCE_KEY = "aihr_filter_source"
FILTER_JOB_KEY = "aihr_filter_job_category"
FILTER_REGION_KEY = "aihr_filter_region"
FILTER_MODEL_KEY = "aihr_filter_model_version"
FILTER_RECRUITER_KEY = "aihr_filter_recruiter_team"
FILTER_DATE_DRAFT_KEY = f"{FILTER_DATE_KEY}_draft"
FILTER_SOURCE_DRAFT_KEY = f"{FILTER_SOURCE_KEY}_draft"
FILTER_JOB_DRAFT_KEY = f"{FILTER_JOB_KEY}_draft"
FILTER_REGION_DRAFT_KEY = f"{FILTER_REGION_KEY}_draft"
FILTER_MODEL_DRAFT_KEY = f"{FILTER_MODEL_KEY}_draft"
FILTER_RECRUITER_DRAFT_KEY = f"{FILTER_RECRUITER_KEY}_draft"
FILTER_QUERY_NAMES = {
    FILTER_SOURCE_KEY: "source",
    FILTER_JOB_KEY: "job_category",
    FILTER_REGION_KEY: "region",
    FILTER_MODEL_KEY: "model_version",
    FILTER_RECRUITER_KEY: "recruiter_team",
}
FILTER_DRAFT_KEYS = {
    FILTER_DATE_KEY: FILTER_DATE_DRAFT_KEY,
    FILTER_SOURCE_KEY: FILTER_SOURCE_DRAFT_KEY,
    FILTER_JOB_KEY: FILTER_JOB_DRAFT_KEY,
    FILTER_REGION_KEY: FILTER_REGION_DRAFT_KEY,
    FILTER_MODEL_KEY: FILTER_MODEL_DRAFT_KEY,
    FILTER_RECRUITER_KEY: FILTER_RECRUITER_DRAFT_KEY,
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
        .aihr-callout {
            border-left: 4px solid #2563EB;
            background: #F8FAFC;
            padding: 0.75rem 0.9rem;
            margin: 0.8rem 0 1rem;
            color: #0F172A;
        }
        .aihr-callout strong {display: block; margin-bottom: 0.25rem;}
        .aihr-callout ul {margin: 0.2rem 0 0; padding-left: 1.2rem;}
        .aihr-callout li {margin: 0.2rem 0;}
        .aihr-assistant-title {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin: 1.6rem 0 0.35rem;
            color: #0F172A;
            font-size: 1.25rem;
            font-weight: 800;
        }
        .aihr-assistant-avatar {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 2rem;
            height: 2rem;
            border-radius: 999px;
            background: #00796B;
            color: #FFFFFF;
            font-size: 1.15rem;
        }
        .aihr-assistant-subtitle {
            color: #64748B;
            margin: 0 0 0.75rem;
            font-size: 0.92rem;
        }
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


def _filter_state_payload(
    date_range: list[date],
    source: str,
    job_category: str,
    region: str,
    model_version: str,
    recruiter_team: str,
) -> dict[str, str]:
    return {
        "start_date": date_range[0].isoformat() if len(date_range) == 2 else "",
        "end_date": date_range[-1].isoformat() if len(date_range) == 2 else "",
        "source": source,
        "job_category": job_category,
        "region": region,
        "model_version": model_version,
        "recruiter_team": recruiter_team,
    }


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
    st.session_state[FILTER_DATE_DRAFT_KEY] = (date_min, date_max)
    st.session_state[FILTER_SOURCE_DRAFT_KEY] = ALL_OPTION
    st.session_state[FILTER_JOB_DRAFT_KEY] = ALL_OPTION
    st.session_state[FILTER_REGION_DRAFT_KEY] = ALL_OPTION
    st.session_state[FILTER_MODEL_DRAFT_KEY] = ALL_OPTION
    st.session_state[FILTER_RECRUITER_DRAFT_KEY] = ALL_OPTION
    st.query_params.clear()
    st.query_params["start_date"] = date_min.isoformat()
    st.query_params["end_date"] = date_max.isoformat()
    _write_saved_filter_state(
        _filter_state_payload(
            [date_min, date_max],
            ALL_OPTION,
            ALL_OPTION,
            ALL_OPTION,
            ALL_OPTION,
            ALL_OPTION,
        )
    )


def _apply_filter_state(
    date_range: list[date],
    source: str,
    job_category: str,
    region: str,
    model_version: str,
    recruiter_team: str,
) -> None:
    st.session_state[FILTER_DATE_KEY] = tuple(date_range)
    st.session_state[FILTER_SOURCE_KEY] = source
    st.session_state[FILTER_JOB_KEY] = job_category
    st.session_state[FILTER_REGION_KEY] = region
    st.session_state[FILTER_MODEL_KEY] = model_version
    st.session_state[FILTER_RECRUITER_KEY] = recruiter_team
    _sync_filter_query_params(
        date_range,
        source,
        job_category,
        region,
        model_version,
        recruiter_team,
    )


def _ensure_select_value(key: str, choices: list[str]) -> None:
    if st.session_state.get(key) not in choices:
        st.session_state[key] = choices[0]


def _ensure_date_range(date_min: date, date_max: date) -> None:
    value = st.session_state.get(FILTER_DATE_KEY)
    if (
        not isinstance(value, tuple | list)
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


def _ensure_draft_date_range(date_min: date, date_max: date) -> None:
    value = st.session_state.get(FILTER_DATE_DRAFT_KEY)
    applied_value = st.session_state[FILTER_DATE_KEY]
    if (
        not isinstance(value, tuple | list)
        or len(value) != 2
        or value[0] < date_min
        or value[-1] > date_max
    ):
        st.session_state[FILTER_DATE_DRAFT_KEY] = tuple(applied_value)


def _initialize_draft_select_value(applied_key: str, choices: list[str]) -> None:
    draft_key = FILTER_DRAFT_KEYS[applied_key]
    if draft_key not in st.session_state:
        st.session_state[draft_key] = st.session_state[applied_key]
    if st.session_state.get(draft_key) not in choices:
        st.session_state[draft_key] = st.session_state[applied_key]


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
        _filter_state_payload(
            date_range,
            source,
            job_category,
            region,
            model_version,
            recruiter_team,
        )
    )


def _selected_date_range(value: date | tuple[date, ...] | list[date]) -> list[date]:
    if isinstance(value, date):
        return [value]
    return list(value)


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
    _ensure_draft_date_range(date_min, date_max)
    _initialize_draft_select_value(FILTER_SOURCE_KEY, source_choices)
    _initialize_draft_select_value(FILTER_JOB_KEY, job_choices)
    _initialize_draft_select_value(FILTER_REGION_KEY, region_choices)
    _initialize_draft_select_value(FILTER_MODEL_KEY, model_choices)
    _initialize_draft_select_value(FILTER_RECRUITER_KEY, recruiter_choices)

    st.sidebar.header("分析范围")
    if st.sidebar.button("重置分析范围", use_container_width=True):
        _reset_filter_state(date_min, date_max)
        st.rerun()

    with st.sidebar.form("aihr_filter_form"):
        date_range = st.date_input(
            "推荐日期",
            min_value=date_min,
            max_value=date_max,
            key=FILTER_DATE_DRAFT_KEY,
        )
        source = st.selectbox("推荐来源", source_choices, key=FILTER_SOURCE_DRAFT_KEY)
        job_category = st.selectbox("岗位", job_choices, key=FILTER_JOB_DRAFT_KEY)
        region = st.selectbox("地区", region_choices, key=FILTER_REGION_DRAFT_KEY)
        model_version = st.selectbox("模型版本", model_choices, key=FILTER_MODEL_DRAFT_KEY)
        recruiter_team = st.selectbox("顾问团队", recruiter_choices, key=FILTER_RECRUITER_DRAFT_KEY)
        submitted = st.form_submit_button(
            "确定分析范围",
            type="primary",
            use_container_width=True,
        )

    selected_date_range = _selected_date_range(date_range)
    if submitted:
        if len(selected_date_range) != 2:
            st.sidebar.warning("请选择完整的开始和结束日期。")
        else:
            _apply_filter_state(
                selected_date_range,
                source,
                job_category,
                region,
                model_version,
                recruiter_team,
            )
            st.rerun()

    applied_date_range = list(st.session_state[FILTER_DATE_KEY])
    st.sidebar.caption("当前公开演示使用固定种子的合成招聘事件。")
    st.sidebar.caption("修改筛选项后点击“确定分析范围”，再切换页面会保持同一套分析范围。")
    return (
        applied_date_range,
        st.session_state[FILTER_SOURCE_KEY],
        st.session_state[FILTER_JOB_KEY],
        st.session_state[FILTER_REGION_KEY],
        st.session_state[FILTER_MODEL_KEY],
        st.session_state[FILTER_RECRUITER_KEY],
    )


def format_percent(value: float) -> str:
    return f"{value:.1%}"


def format_pp(value: float) -> str:
    return f"{value * 100:+.1f} 个百分点"


def render_insight_box(title: str, insights: list[str]) -> None:
    if not insights:
        return
    items = "".join(f"<li>{item}</li>" for item in insights)
    st.markdown(
        f"""
        <div class="aihr-callout">
            <strong>{title}</strong>
            <ul>{items}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_assistant_message(content: str) -> None:
    summary, details, body = split_assistant_answer(content)
    if summary:
        with st.expander(f"分析依据｜{summary}", expanded=False):
            st.markdown(details)
    st.markdown(body)
    if summary:
        copy_content = f"{details}\n\n{body}".strip()
    else:
        copy_content = body
    with st.expander("复制回答"):
        st.code(copy_content, language=None, wrap_lines=True)


@st.fragment
def render_ai_assistant(
    page_key: str,
    page_title: str,
    context: dict,
    starter_questions: list[str] | None = None,
) -> None:
    applied_dates = st.session_state.get(FILTER_DATE_KEY) or []
    filter_values = {
        "source": st.session_state.get(FILTER_SOURCE_KEY),
        "job_category": st.session_state.get(FILTER_JOB_KEY),
        "region": st.session_state.get(FILTER_REGION_KEY),
        "model_version": st.session_state.get(FILTER_MODEL_KEY),
        "recruiter_team": st.session_state.get(FILTER_RECRUITER_KEY),
    }
    context = prepare_analysis_context(
        context,
        {
            "start_date": applied_dates[0].isoformat() if len(applied_dates) == 2 else None,
            "end_date": applied_dates[-1].isoformat() if len(applied_dates) == 2 else None,
            "filters": {
                key: value
                for key, value in filter_values.items()
                if value and value != ALL_OPTION
            },
        },
    )
    questions = starter_questions or [
        "请解释这页最重要的结论。",
        "有哪些异常或风险需要注意？",
        "业务使用者应该如何理解这页？",
    ]
    config = assistant_config_summary()
    st.markdown(
        f"""
        <div class="aihr-assistant-title">
            <span class="aihr-assistant-avatar">AI</span>
            <span>AI 分析助手 · {page_title}</span>
        </div>
        <div class="aihr-assistant-subtitle">
            基于当前筛选范围和本页图表数据进行解读、异常分析和追问答疑。
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        if assistant_configured():
            st.success(f"已连接 {config['provider']}：{config['model']}")
        else:
            st.info(
                "未配置大模型时使用本地规则分析；配置 DeepSeek 或兼容模型后，"
                "这里会基于当前页面数据进行智能问答。"
            )

        message_key = f"aihr_page_assistant_{page_key}"
        if message_key not in st.session_state:
            st.session_state[message_key] = []

        messages = st.session_state[message_key]
        action_columns = st.columns(3)
        if action_columns[0].button(
            "重新分析",
            icon=":material/refresh:",
            key=f"{message_key}_refresh",
        ):
            refresh_question = "请基于当前筛选条件重新分析，并说明可信度与结论限制。"
            messages.append({"role": "user", "content": refresh_question})
            regenerated = conversation_for_regeneration(messages)
            answer = answer_question(context, regenerated, force_refresh=True)
            st.session_state[message_key] = [
                *regenerated,
                {"role": "assistant", "content": answer},
            ]
            st.rerun()
        if action_columns[1].button(
            "重新生成",
            icon=":material/replay:",
            key=f"{message_key}_regenerate",
            disabled=not messages,
        ):
            regenerated = conversation_for_regeneration(messages)
            if regenerated:
                answer = answer_question(context, regenerated, force_refresh=True)
                st.session_state[message_key] = [
                    *regenerated,
                    {"role": "assistant", "content": answer},
                ]
                st.rerun()
        if action_columns[2].button(
            "清空",
            icon=":material/delete:",
            key=f"{message_key}_clear",
            disabled=not messages,
        ):
            clear_conversation(messages)
            st.rerun()

        if not st.session_state[message_key]:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(
                    f"你好，我是本页的 AI 分析助手。可以帮你解释“{page_title}”的图表结论、"
                    "异常风险、业务含义和下一步建议。你可以先点下面的快捷问题。"
                )

        columns = st.columns(len(questions))
        for index, question in enumerate(questions):
            if columns[index].button(question, key=f"{message_key}_q_{index}"):
                if append_unique_question(messages, question):
                    answer = answer_question(context, messages)
                    messages.append({"role": "assistant", "content": answer})
                    st.rerun()

        for message in st.session_state[message_key]:
            avatar = (
                "🤖"
                if message["role"] == "assistant"
                else "🧑"
            )
            with st.chat_message(message["role"], avatar=avatar):
                if message["role"] == "assistant":
                    render_assistant_message(message["content"])
                else:
                    st.markdown(message["content"])

        prompt = st.chat_input(
            f"继续追问{page_title}的数据结论",
            key=f"{message_key}_input",
        )
        if prompt:
            st.session_state[message_key].append({"role": "user", "content": prompt})
            with st.chat_message("user", avatar="🧑"):
                st.markdown(prompt)
            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("正在基于本页数据分析..."):
                    answer = answer_question(context, st.session_state[message_key])
                    render_assistant_message(answer)
            st.session_state[message_key].append({"role": "assistant", "content": answer})


def render_table(dataframe: pd.DataFrame, **_ignored) -> None:
    if dataframe.empty:
        st.info("当前筛选范围没有可展示的表格数据。")
        return
    st.markdown(
        f'<div class="aihr-table">{dataframe.to_html(index=False, escape=True)}</div>',
        unsafe_allow_html=True,
    )
