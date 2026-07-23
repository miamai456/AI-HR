from datetime import date
from typing import Any

import requests

from aihr.config import get_settings

API_URL = get_settings().api_url.rstrip("/")


class ApiError(RuntimeError):
    pass


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        response = requests.get(f"{API_URL}{path}", params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ApiError(f"无法连接分析 API：{exc}") from exc
    return response.json()


def get_filters() -> dict:
    return _get("/meta/filters")


def get_overview(params: dict[str, Any]) -> dict:
    return _get("/overview", params=params)


def get_funnel(params: dict[str, Any]) -> list[dict]:
    return _get("/funnel", params=params)


def get_monitoring() -> dict:
    return _get("/monitoring")


def get_effectiveness(params: dict[str, Any]) -> dict:
    return _get("/effectiveness/unadjusted", params=params)


def build_query(
    date_range: tuple[date, date] | list[date],
    source: str,
    job_category: str,
    region: str,
) -> dict[str, str]:
    params = {
        "start_date": date_range[0].isoformat(),
        "end_date": date_range[-1].isoformat(),
    }
    if source != "全部":
        params["source"] = source
    if job_category != "全部":
        params["job_category"] = job_category
    if region != "全部":
        params["region"] = region
    return params
