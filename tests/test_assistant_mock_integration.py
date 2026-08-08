from fastapi.testclient import TestClient

from aihr.api.main import app
from aihr.services.assistant import AssistantClient, AssistantService


def test_assistant_endpoint_integrates_with_mocked_deepseek_http(monkeypatch) -> None:
    captured = {}

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"conclusion":"Stable association","evidence":["n=120"],'
                                '"risks":["observational only"],'
                                '"recommendations":["monitor weekly"]}'
                            )
                        }
                    }
                ],
                "usage": {"total_tokens": 42},
            }

    def mocked_post(url, **kwargs):
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["payload"] = kwargs["json"]
        return MockResponse()

    service = AssistantService(
        AssistantClient(
            api_key="test-api-key",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            post=mocked_post,
            sleep=lambda _: None,
        )
    )
    monkeypatch.setattr(app.state, "assistant_service", service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/analyze",
            json={
                "context": {
                    "analysis_scope": {
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                        "filters": {"source": "ai"},
                    },
                    "overview": {"summary": {"recommended": 120}},
                    "data_quality": {
                        "summary": {"failed_checks": 0, "warning_checks": 0},
                        "layers": [],
                    },
                },
                "messages": [{"role": "user", "content": "Analyze"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["conclusion"] == "Stable association"
    assert response.json()["total_tokens"] == 42
    assert response.json()["trust"]["causal_claim"] is False
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-api-key"
    assert captured["payload"]["response_format"] == {"type": "json_object"}


def test_assistant_stream_endpoint_forwards_sse_events(monkeypatch) -> None:
    class MockResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter(
                [
                    ": keep-alive",
                    'data: {"choices":[{"delta":{"content":"## 结论\\n"}}]}',
                    'data: {"choices":[{"delta":{"content":"样本支持探索性判断"}}]}',
                    "data: [DONE]",
                ]
            )

    captured = {}

    def mocked_post(url, **kwargs):
        captured["payload"] = kwargs["json"]
        return MockResponse()

    service = AssistantService(
        AssistantClient(
            api_key="test-api-key",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            post=mocked_post,
            sleep=lambda _: None,
        )
    )
    monkeypatch.setattr(app.state, "assistant_service", service)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/analyze/stream",
            json={
                "context": {"overview": {"summary": {"recommended": 120}}},
                "messages": [{"role": "user", "content": "分析当前数据"}],
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: metadata" in response.text
    assert "event: delta" in response.text
    assert "样本支持探索性判断" in response.text
    assert "event: done" in response.text
    assert captured["payload"]["stream"] is True
