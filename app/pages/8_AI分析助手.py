import streamlit as st

from app.analysis_assistant import (
    answer_question,
    assistant_config_summary,
    assistant_configured,
)
from app.api_client import (
    ApiError,
    build_query,
    get_data_quality,
    get_effectiveness,
    get_monitoring_with_filters,
    get_overview,
    get_prediction_insights,
)
from app.ui import configure_page, render_filters

QUICK_QUESTIONS = [
    "请总结当前筛选范围下的核心业务结论。",
    "有哪些异常、风险或结论限制需要优先关注？",
    "业务团队下一步应该优先处理哪些问题？",
]


def build_analysis_context(query: dict[str, str]) -> dict:
    return {
        "overview": get_overview(query),
        "effectiveness": get_effectiveness(query),
        "monitoring": get_monitoring_with_filters(query),
        "data_quality": get_data_quality(query),
        "prediction": get_prediction_insights(query),
    }


configure_page("AI 分析助手")
st.title("AI 分析助手")
st.caption("帮助看板使用者理解当前数据结论、异常风险、指标含义和下一步业务动作。")

date_range, source, job_category, region, model_version, recruiter_team = render_filters()
if len(date_range) != 2:
    st.warning("请选择完整的开始和结束日期。")
    st.stop()

query = build_query(date_range, source, job_category, region, model_version, recruiter_team)
try:
    context = build_analysis_context(query)
except ApiError as exc:
    st.error(str(exc))
    st.stop()

config = assistant_config_summary()
if assistant_configured():
    st.success(f"已连接 {config['provider']}：{config['model']}")
else:
    st.info(
        "当前未配置大模型 API Key，页面使用本地规则分析。配置 "
        "`AIHR_ASSISTANT_API_KEY`、`AIHR_ASSISTANT_BASE_URL`、"
        "`AIHR_ASSISTANT_MODEL` 后可接入 Kimi、DeepSeek 或其他兼容接口。"
    )

if "aihr_assistant_messages" not in st.session_state:
    st.session_state.aihr_assistant_messages = []

if not st.session_state.aihr_assistant_messages:
    with st.chat_message("assistant", avatar="🤖"):
        st.markdown(
            "你好，我是 AIHR 的数据分析助手。你可以问我当前看板里的核心结论、"
            "异常风险、指标含义、分群机会和下一步业务建议。"
        )

st.subheader("快捷问题")
columns = st.columns(3)
for index, question in enumerate(QUICK_QUESTIONS):
    if columns[index].button(question, use_container_width=True):
        st.session_state.aihr_assistant_messages.append(
            {"role": "user", "content": question}
        )
        answer = answer_question(context, st.session_state.aihr_assistant_messages)
        st.session_state.aihr_assistant_messages.append(
            {"role": "assistant", "content": answer}
        )
        st.rerun()

for message in st.session_state.aihr_assistant_messages:
    avatar = "🤖" if message["role"] == "assistant" else "🧑"
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

prompt = st.chat_input("继续追问当前看板的数据结论、异常风险或指标含义")
if prompt:
    st.session_state.aihr_assistant_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("正在分析当前看板上下文..."):
            answer = answer_question(context, st.session_state.aihr_assistant_messages)
            st.markdown(answer)
    st.session_state.aihr_assistant_messages.append(
        {"role": "assistant", "content": answer}
    )
