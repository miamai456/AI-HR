from fastapi.testclient import TestClient

from aihr.api.main import app
from aihr.services.assistant import AssistantAnswer


class FakeAssistantService:
    def __init__(self):
        self.calls = 0

    def analyze(self, context, messages, *, force_refresh=False):
        self.calls += 1
        return (
            AssistantAnswer(
                conclusion="Model conclusion",
                evidence=["Model evidence"],
                risks=["Model risk"],
                recommendations=["Model recommendation"],
                total_tokens=10,
            ),
            self.calls > 1,
            25,
        )


def test_assistant_api_returns_structured_answer_status_and_trust(monkeypatch) -> None:
    service = FakeAssistantService()
    monkeypatch.setattr(app.state, "assistant_service", service)

    with TestClient(app) as client:
        status = client.get("/api/v1/assistant/status")
        response = client.post(
            "/api/v1/assistant/analyze",
            json={
                "context": {
                    "page_name": "overview",
                    "analysis_scope": {
                        "start_date": "2026-01-01",
                        "end_date": "2026-06-30",
                        "filters": {"source": "ai"},
                    },
                    "overview": {"summary": {"recommended": 500}},
                    "effectiveness": {
                        "analysis_type": "observational_adjusted_association",
                        "causal_claim": False,
                    },
                    "data_quality": {
                        "summary": {
                            "failed_checks": 0,
                            "warning_checks": 0,
                            "generated_at": "2026-07-01T10:00:00",
                        },
                        "layers": [{"last_updated_at": "2026-06-30T23:00:00"}],
                    },
                },
                "messages": [{"role": "user", "content": "Analyze the current page"}],
            },
        )

    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert response.status_code == 200
    assert response.json()["conclusion"] == "Model conclusion"
    assert response.json()["total_tokens"] == 10
    assert response.json()["trust"] == {
        "sample_size": 500,
        "period_start": "2026-01-01",
        "period_end": "2026-06-30",
        "data_updated_at": "2026-06-30T23:00:00",
        "data_quality_status": "pass",
        "confidence": "high",
        "confidence_note": "样本量和数据质量支持较稳定的观察性结论。",
        "analysis_type": "observational_adjusted_association",
        "causal_claim": False,
        "filters": {"source": "ai"},
    }


def test_assistant_api_downgrades_small_sample_conclusion(monkeypatch) -> None:
    monkeypatch.setattr(app.state, "assistant_service", FakeAssistantService())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/assistant/analyze",
            json={
                "context": {
                    "analysis_scope": {
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "filters": {},
                    },
                    "overview": {"summary": {"recommended": 12}},
                    "data_quality": {
                        "summary": {
                            "failed_checks": 0,
                            "warning_checks": 0,
                            "generated_at": "2026-07-01T10:00:00",
                        },
                        "layers": [],
                    },
                },
                "messages": [{"role": "user", "content": "Summarize"}],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trust"]["confidence"] == "low"
    assert payload["trust"]["causal_claim"] is False
    assert payload["conclusion"].startswith("探索性判断：")
    assert any("样本量" in risk for risk in payload["risks"])
