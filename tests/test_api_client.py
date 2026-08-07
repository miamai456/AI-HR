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
    monkeypatch.setattr(api_client.requests, "get", fake_get)

    first = api_client.get_overview({"source": "ai"})
    second = api_client.get_overview({"source": "ai"})

    assert first == second
    assert calls == 1
