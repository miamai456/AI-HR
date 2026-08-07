import requests

from aihr.services.assistant import AssistantClient, AssistantService, AssistantServiceError


def test_assistant_client_returns_structured_answer() -> None:
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"conclusion":"面试率下降","evidence":["样本量为100"],'
                                '"risks":["不能推断因果"],"recommendations":["检查数据质量"]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32},
            }

    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    client = AssistantClient(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        post=fake_post,
        sleep=lambda _: None,
    )

    result = client.analyze({"page_name": "效果评估"}, [{"role": "user", "content": "分析"}])

    assert result.conclusion == "面试率下降"
    assert result.evidence == ["样本量为100"]
    assert result.risks == ["不能推断因果"]
    assert result.recommendations == ["检查数据质量"]
    assert result.total_tokens == 32
    assert calls[0][0] == "https://api.deepseek.com/chat/completions"
    assert calls[0][1]["json"]["response_format"] == {"type": "json_object"}


def test_assistant_client_retries_rate_limit_and_then_succeeds(monkeypatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"conclusion":"ok","evidence":[],"risks":[],"recommendations":[]}'
                            )
                        }
                    }
                ]
            }

    class RateLimitResponse:
        status_code = 429

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

    responses = iter([RateLimitResponse(), Response()])
    client = AssistantClient(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        post=lambda *args, **kwargs: next(responses),
        sleep=lambda _: None,
    )

    result = client.analyze({}, [{"role": "user", "content": "分析"}])

    assert result.conclusion == "ok"


def test_assistant_client_exposes_unauthorized_error() -> None:
    class UnauthorizedResponse:
        status_code = 401

        def raise_for_status(self):
            raise requests.HTTPError(response=self)

    client = AssistantClient(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        post=lambda *args, **kwargs: UnauthorizedResponse(),
        sleep=lambda _: None,
    )

    try:
        client.analyze({}, [{"role": "user", "content": "分析"}])
    except AssistantServiceError as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected AssistantServiceError")


def test_assistant_service_force_refresh_bypasses_cached_answer() -> None:
    class Client:
        model = "deepseek-chat"

        def __init__(self):
            self.calls = 0

        def analyze(self, context, messages):
            self.calls += 1
            return type(
                "Answer",
                (),
                {
                    "conclusion": f"answer-{self.calls}",
                    "evidence": [],
                    "risks": [],
                    "recommendations": [],
                    "total_tokens": 1,
                },
            )()

    client = Client()
    service = AssistantService(client)

    first, first_cached, _ = service.analyze({}, [{"role": "user", "content": "Q"}])
    second, second_cached, _ = service.analyze({}, [{"role": "user", "content": "Q"}])
    refreshed, refreshed_cached, _ = service.analyze(
        {}, [{"role": "user", "content": "Q"}], force_refresh=True
    )

    assert first.conclusion == "answer-1"
    assert second.conclusion == "answer-1"
    assert refreshed.conclusion == "answer-2"
    assert first_cached is False
    assert second_cached is True
    assert refreshed_cached is False
