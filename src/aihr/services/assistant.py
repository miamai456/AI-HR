import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from hashlib import sha256
from threading import Lock
from typing import Any

import requests

from aihr.services.cache import JsonCache

LOGGER = logging.getLogger(__name__)
SYSTEM_PROMPT = """
你是 AIHR 招聘分析助手。只能基于提供的 JSON 上下文回答。
必须区分事实、风险和建议，不得把相关性描述成因果关系。
如果样本不足、数据质量失败或模型漂移严重，必须明确说明结论限制。
只返回 JSON，不要 Markdown，字段必须为：
conclusion（字符串）、evidence（字符串数组）、risks（字符串数组）、
recommendations（字符串数组）。
结论先讲业务含义，证据引用具体指标，建议给出可执行的下一步。
""".strip()

STREAM_SYSTEM_PROMPT = """
You are the AIHR hiring analytics assistant. Answer only from the supplied JSON context.
Write in Chinese and use exactly these Markdown headings: 结论, 证据, 风险, 建议.
Keep the answer concise and practical. Separate observed association from causal claims.
If the sample is small or data quality is not pass, make only an exploratory judgment.
Do not invent metrics, dates, filters, teams, models, or facts absent from the context.
""".strip()


@dataclass
class AssistantAnswer:
    conclusion: str
    evidence: list[str]
    risks: list[str]
    recommendations: list[str]
    total_tokens: int | None = None


class AssistantServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AssistantClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        post: Callable[..., Any] = requests.post,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.post = post
        self.sleep = sleep
        self.max_attempts = max_attempts

    def _compact_context(self, context: dict[str, Any]) -> str:
        compact_context = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(compact_context) > 30_000:
            compact_context = compact_context[:30_000] + "\n...[context truncated]"
        return compact_context

    def analyze(
        self, context: dict[str, Any], messages: list[dict[str, str]]
    ) -> AssistantAnswer:
        compact_context = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        if len(compact_context) > 30_000:
            compact_context = compact_context[:30_000] + "\n...[上下文已截断]"
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "max_tokens": 1_200,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "system", "content": f"当前分析上下文 JSON：{compact_context}"},
                *messages[-8:],
            ],
        }

        for attempt in range(self.max_attempts):
            try:
                response = self.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=(5, 45),
                )
                response.raise_for_status()
                return self._parse_response(response.json())
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {408, 429, 500, 502, 503, 504}:
                    raise AssistantServiceError(
                        "DeepSeek 请求失败", status_code=status_code
                    ) from exc
                if attempt == self.max_attempts - 1:
                    raise AssistantServiceError(
                        "DeepSeek 暂时不可用，请稍后重试", status_code=status_code
                    ) from exc
                self.sleep(2**attempt)
            except requests.RequestException as exc:
                if attempt == self.max_attempts - 1:
                    raise AssistantServiceError("DeepSeek 网络请求失败") from exc
                self.sleep(2**attempt)

        raise AssistantServiceError("DeepSeek 请求失败")

    def stream_markdown(
        self, context: dict[str, Any], messages: list[dict[str, str]]
    ) -> Iterator[str]:
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "max_tokens": 1_200,
            "stream": True,
            "messages": [
                {"role": "system", "content": STREAM_SYSTEM_PROMPT},
                {
                    "role": "system",
                    "content": f"Analysis context JSON: {self._compact_context(context)}",
                },
                *messages[-8:],
            ],
        }
        for attempt in range(self.max_attempts):
            try:
                response = self.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=(5, 60),
                    stream=True,
                )
                response.raise_for_status()
                for line in response.iter_lines(decode_unicode=True):
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise AssistantServiceError("DeepSeek 流式响应无法解析") from exc
                    delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield str(content)
                return
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {408, 429, 500, 502, 503, 504}:
                    raise AssistantServiceError(
                        "DeepSeek 请求失败", status_code=status_code
                    ) from exc
                if attempt == self.max_attempts - 1:
                    raise AssistantServiceError(
                        "DeepSeek 暂时不可用，请稍后重试", status_code=status_code
                    ) from exc
                self.sleep(2**attempt)
            except requests.RequestException as exc:
                if attempt == self.max_attempts - 1:
                    raise AssistantServiceError("DeepSeek 网络请求失败") from exc
                self.sleep(2**attempt)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> AssistantAnswer:
        try:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return AssistantAnswer(
                conclusion=str(parsed["conclusion"]),
                evidence=[str(item) for item in parsed.get("evidence", [])],
                risks=[str(item) for item in parsed.get("risks", [])],
                recommendations=[str(item) for item in parsed.get("recommendations", [])],
                total_tokens=(data.get("usage") or {}).get("total_tokens"),
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AssistantServiceError("DeepSeek 返回了无法解析的结构化结果") from exc


class AssistantService:
    def __init__(
        self,
        client: AssistantClient,
        *,
        ttl_seconds: int = 60,
        max_entries: int = 128,
        cache_backend: JsonCache | None = None,
    ):
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.cache_backend = cache_backend
        self._cache: dict[str, tuple[float, AssistantAnswer]] = {}
        self._lock = Lock()

    def analyze(
        self,
        context: dict[str, Any],
        messages: list[dict[str, str]],
        *,
        force_refresh: bool = False,
    ) -> tuple[AssistantAnswer, bool, int]:
        cache_key = sha256(
            json.dumps(
                {"context": context, "messages": messages[-8:]},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        now = time.monotonic()
        if not force_refresh:
            if self.cache_backend is not None:
                persisted = self.cache_backend.get(f"assistant-answer:{cache_key}")
                if persisted is not None:
                    return AssistantAnswer(**persisted), True, 0
            with self._lock:
                cached = self._cache.get(cache_key)
                if cached and now - cached[0] < self.ttl_seconds:
                    return cached[1], True, 0

        started = time.perf_counter()
        answer = self.client.analyze(context, messages)
        latency_ms = round((time.perf_counter() - started) * 1000)
        with self._lock:
            self._cache[cache_key] = (time.monotonic(), answer)
            if len(self._cache) > self.max_entries:
                oldest_key = min(self._cache, key=lambda key: self._cache[key][0])
                self._cache.pop(oldest_key, None)
        if self.cache_backend is not None:
            self.cache_backend.set(
                f"assistant-answer:{cache_key}",
                asdict(answer),
                ttl_seconds=self.ttl_seconds,
            )
        LOGGER.info(
            "assistant_request model=%s latency_ms=%s total_tokens=%s cached=false",
            self.client.model,
            latency_ms,
            answer.total_tokens,
        )
        return answer, False, latency_ms

    def stream_markdown(
        self, context: dict[str, Any], messages: list[dict[str, str]]
    ) -> Iterator[str]:
        return self.client.stream_markdown(context, messages)
