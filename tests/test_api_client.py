from app import api_client


def test_analysis_get_requests_are_cached_for_repeated_streamlit_reruns(monkeypatch) -> None:
    calls = 0

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"summary": {"recommended": 120}}

    def fake_get(*args, **kwargs):
        nonlocal calls
        calls += 1
        return Response()

    api_client._get.clear()
    monkeypatch.setattr(api_client.HTTP_SESSION, "get", fake_get)

    first = api_client.get_overview({"source": "ai"})
    second = api_client.get_overview({"source": "ai"})

    assert first == second
    assert calls == 1


def test_assistant_context_uses_single_backend_request(monkeypatch) -> None:
    requested_urls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "analysis_scope": {"filters": {"source": "ai"}},
                "overview": {},
                "effectiveness": {},
                "monitoring": {},
                "data_quality": {},
                "prediction": {},
                "cached": False,
                "latency_ms": 10,
            }

    def fake_get(url, **kwargs):
        requested_urls.append(url)
        return Response()

    api_client._get.clear()
    monkeypatch.setattr(api_client.HTTP_SESSION, "get", fake_get)

    result = api_client.get_assistant_context({"source": "ai"})

    assert result["analysis_scope"]["filters"] == {"source": "ai"}
    assert requested_urls == [f"{api_client.API_URL}/assistant/context"]


def test_stream_assistant_parses_named_sse_events(monkeypatch) -> None:
    class Response:
        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter(
                [
                    "event: metadata",
                    'data: {"model":"deepseek-chat"}',
                    "",
                    "event: delta",
                    'data: {"content":"answer"}',
                ]
            )

    monkeypatch.setattr(api_client.HTTP_SESSION, "post", lambda *args, **kwargs: Response())

    events = list(
        api_client.stream_assistant({}, [{"role": "user", "content": "Analyze"}])
    )

    assert events == [
        {"event": "metadata", "model": "deepseek-chat"},
        {"event": "delta", "content": "answer"},
    ]
