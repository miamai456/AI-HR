from datetime import date
from typing import Any

import requests
import streamlit as st

from aihr.config import get_settings

API_URL = get_settings().api_url.rstrip("/")
ALL_OPTION = "全部"
REQUEST_TIMEOUT_SECONDS = 60


class ApiError(RuntimeError):
    pass


@st.cache_data(ttl=60, max_entries=128, show_spinner=False)
def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        response = requests.get(
            f"{API_URL}{path}",
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ApiError(f"无法连接分析 API：{exc}") from exc
    return response.json()


def _post(path: str, payload: dict[str, Any]) -> Any:
    try:
        response = requests.post(
            f"{API_URL}{path}",
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = ""
        if exc.response is not None:
            try:
                detail = f": {exc.response.json().get('detail', '')}"
            except ValueError:
                detail = ""
        raise ApiError(f"无法调用分析 API{detail or f': {exc}'}") from exc
    return response.json()


def get_filters() -> dict:
    return _get("/meta/filters")


def get_overview(params: dict[str, Any]) -> dict:
    return _get("/overview", params=params)


def get_funnel(params: dict[str, Any]) -> list[dict]:
    return _get("/funnel", params=params)


def get_monitoring() -> dict:
    return _get("/monitoring")


def get_monitoring_with_filters(params: dict[str, Any]) -> dict:
    return _get("/monitoring", params=params)


def get_effectiveness(params: dict[str, Any]) -> dict:
    return _get("/effectiveness/unadjusted", params=params)


def get_data_quality(params: dict[str, Any] | None = None) -> dict:
    return _get("/data-quality", params=params)


def get_prediction_insights(params: dict[str, Any] | None = None) -> dict:
    return _get("/prediction-insights", params=params)


def get_assistant_status() -> dict:
    return _get("/assistant/status")


def analyze_assistant(
    context: dict,
    messages: list[dict[str, str]],
    force_refresh: bool = False,
) -> dict:
    return _post(
        "/assistant/analyze",
        {"context": context, "messages": messages, "force_refresh": force_refresh},
    )


def build_query(
    date_range: tuple[date, date] | list[date],
    source: str,
    job_category: str,
    region: str,
    model_version: str = ALL_OPTION,
    recruiter_team: str = ALL_OPTION,
) -> dict[str, str]:
    params = {
        "start_date": date_range[0].isoformat(),
        "end_date": date_range[-1].isoformat(),
    }
    if source != ALL_OPTION:
        params["source"] = source
    if job_category != ALL_OPTION:
        params["job_category"] = job_category
    if region != ALL_OPTION:
        params["region"] = region
    if model_version != ALL_OPTION:
        params["model_version"] = model_version
    if recruiter_team != ALL_OPTION:
        params["recruiter_team"] = recruiter_team
    return params
